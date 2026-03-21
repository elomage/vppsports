import { useState, useEffect, useMemo, useRef } from 'react'
import Plot from 'react-plotly.js'
import './PlotlyGraphvisualizer2.css'

const SERVER_URL = import.meta.env.VITE_SERVER_URL;
const ACCESS_TOKEN_STORAGE_KEY = "vppsports_access_token";

const getAuthHeaders = () => {
    const token = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
};

const fetchSensorData = async (runid, sensorid) => {
    try {
        // console.log('fetching data for run:', runid, 'sensor:', sensorid);
        const response = await fetch(`${SERVER_URL}/run/${runid}/sensor/${sensorid}/data`, {
            headers: getAuthHeaders(),
            credentials: 'include',
        });
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching data:', error);
    }
};

const fetchFilteredSensorData = async (runid, sensorid, filters) => {
  try{
    // filters should be a comma-separated string, e.g. "kalman,movingaverage"
    const response = await fetch(`${SERVER_URL}/run/${runid}/sensor/${sensorid}/data?filters=${encodeURIComponent(filters)}`, {
      headers: getAuthHeaders(),
      credentials: 'include',
    })
    if (!response.ok) throw new Error('Network response was not ok');
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching filter data:', error);
  } 
};

const fetchRunSensors = async (runid) => {
    try {
        const response = await fetch(`${SERVER_URL}/run/${runid}/sensor`, {
            headers: getAuthHeaders(),
            credentials: 'include',
        });
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error fetching data:', error);
    }
};

// Estimate typical step to decide how far we're willing to snap
const estimateStep = (ts) => {
  if (!ts || ts.length < 2) return Number.POSITIVE_INFINITY;
  const diffs = [];
  for (let i = 1; i < ts.length; i++) diffs.push(ts[i] - ts[i - 1]);
  diffs.sort((a,b)=>a-b);
  const mid = Math.floor(diffs.length / 2);
  return diffs.length % 2 ? diffs[mid] : (diffs[mid - 1] + diffs[mid]) / 2;
};

const getAxisCount = (readings) => {
  if (!Array.isArray(readings) || readings.length === 0) return 0;
  return readings.reduce((maxAxisCount, reading) => {
    const axisCount = Array.isArray(reading?.data) ? reading.data.length : 0;
    return Math.max(maxAxisCount, axisCount);
  }, 0);
};

const getAxisLabel = (axisIndex, axisCount) => {
  if (axisCount === 3) {
    return ["X", "Y", "Z"][axisIndex] || `Axis ${axisIndex + 1}`;
  }
  return `raw_value${axisIndex + 1}`;
};

// Align sensor readings to a base timeline using nearest neighbor with tolerance
const alignReadingsToTimeline = (baseTs, readings) => {
  const axisCount = getAxisCount(readings);
  const aligned = {
    x: baseTs.slice(),
    axes: Array.from({ length: axisCount }, () =>
      new Array(baseTs.length).fill(null)
    ),
  };
  if (!Array.isArray(readings) || readings.length === 0) return aligned;

  const rs = readings; // assume already sorted ascending
  const tol = estimateStep(rs.map(r => r.timestamp)) * 1.5; // tolerance

  let j = 0;
  for (let i = 0; i < baseTs.length; i++) {
    const t = baseTs[i];

    // advance j while next reading is closer
    while (
      j + 1 < rs.length &&
      Math.abs(rs[j + 1].timestamp - t) <= Math.abs(rs[j].timestamp - t)
    ) {
      j++;
    }

    const closest = rs[j];
    const dt = Math.abs(closest.timestamp - t);

    // only snap if within tolerance, else leave null (gap)
    if (dt <= tol) {
      for (let axisIndex = 0; axisIndex < axisCount; axisIndex++) {
        aligned.axes[axisIndex][i] = closest.data?.[axisIndex] ?? null;
      }
    }
  }
  return aligned;
};

const PlotlyGraphVisualizer = ({ selectedRun, sliderValue, removeFunction }) => {
  const [useFilteredData, setUseFilteredData] = useState(false);
  const [selectedFilters, setSelectedFilters] = useState([]);
  const [pendingFilters, setPendingFilters] = useState([]); // New: track pending filter changes
  
  // New state for sensor selection
  const [availableSensors, setAvailableSensors] = useState([]);
  const [selectedSensors, setSelectedSensors] = useState([]);

  // Cache for sensor data to prevent redundant fetches
  const [sensorDataCache, setSensorDataCache] = useState({
    raw: {}, // { sensorId: data }
    filtered: {} // { 'sensorId:filterString': data }
  });

  // Drag state for filter ordering
  const [draggedFilter, setDraggedFilter] = useState(null);

  // Available filters
  const availableFilters = [
    { id: 'kalman', label: 'Kalman' },
    { id: 'movingaverage', label: 'MovAvg' },
    { id: 'savitzkygolay', label: 'SavGol' }
  ];

  // Helper to toggle checkboxes (update pending filters)
  const toggleFilter = (name) => {
    setPendingFilters(prev =>
      prev.includes(name) ? prev.filter(f => f !== name) : [...prev, name]
    );
  };

  // Drag handlers for filter ordering
  const handleDragStart = (e, filterId) => {
    setDraggedFilter(filterId);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e, targetFilterId) => {
    e.preventDefault();
    if (draggedFilter === targetFilterId) return;

    setPendingFilters(prev => {
      const newFilters = [...prev];
      const draggedIndex = newFilters.indexOf(draggedFilter);
      const targetIndex = newFilters.indexOf(targetFilterId);

      if (draggedIndex === -1 || targetIndex === -1) return prev;

      // Remove dragged item and insert at target position
      newFilters.splice(draggedIndex, 1);
      newFilters.splice(targetIndex, 0, draggedFilter);

      return newFilters;
    });
    setDraggedFilter(null);
  };

  const handleDragEnd = () => {
    setDraggedFilter(null);
  };

  // Apply pending filters when toggle is pressed
  const applyFilters = () => {
    setSelectedFilters(pendingFilters);
    setUseFilteredData(true);
  };

  // Turn off filtered mode
  const disableFilters = () => {
    setUseFilteredData(false);
    setPendingFilters(selectedFilters); // Reset pending to current
  };

  const UIREVISION_VALUE = "keep"
  const plotRef = useRef(null);
  const graphLayout = useMemo(() => ({
      autosize: true,
      dragmode: 'pan',
      margin: { l: 0, r: 10, t: 30, b: 0 },
      xaxis: { title: 'Timestamp', showticklabels: false, fixedrange: false },
      yaxis: { title: 'Sensor Reading', fixedrange: true },
      legend: {
          font: {
              size: 16
          }
      },
      uirevision: UIREVISION_VALUE,
      shapes: [],
      annotations: [] 
  }), [])

  const formatTime = (timeInNanoseconds) => {
      // Convert nanoseconds to milliseconds
      const ms = Math.floor(timeInNanoseconds / 1e6)
      const hours = Math.floor(ms / 3600000)
      const minutes = Math.floor((ms % 3600000) / 60000)
      const seconds = Math.floor((ms % 60000) / 1000)
      const milliseconds = ms % 1000
      const formatUnit = (unit) => String(unit).padStart(2, '0')
      return `${formatUnit(hours)}:${formatUnit(minutes)}:${formatUnit(seconds)}:${String(milliseconds).padStart(3, '0')}`
  };

  // const run = useFilteredData ? selectedRun.filteredRunData : selectedRun

  const run = selectedRun

  const [sensorReadings, setSensorReadings] = useState([]);
  const [sensorSpecificData, setSensorSpecificData] = useState({});
  const [sensorAlignedData, setSensorAlignedData] = useState({});

  // Clear cache when run changes
  useEffect(() => {
    setSensorDataCache({
      raw: {},
      filtered: {}
    });
  }, [selectedRun?._id]);

  // Fetch available sensors on mount
  useEffect(() => {
    const loadAvailableSensors = async () => {
      if (!selectedRun?._id) return;
      
      try {
        const sensors = await fetchRunSensors(selectedRun._id);
        setAvailableSensors(sensors);
        // By default, no sensors are selected
        setSelectedSensors([]);
      } catch (error) {
        console.error('Error loading available sensors:', error);
      }
    };
    
    loadAvailableSensors();
  }, [selectedRun?._id]);

  // Toggle sensor selection
  const toggleSensor = (sensorId) => {
    setSelectedSensors(prev =>
      prev.includes(sensorId) 
        ? prev.filter(id => id !== sensorId)
        : [...prev, sensorId]
    );
  };

  // Choose fetcher based on toggle
  const DEFAULT_FILTERS = ['kalman'];

  useEffect(() => {
    const fetchData = async () => {
      if (!selectedRun?._id || selectedSensors.length === 0) {
        setSensorReadings([]);
        setSensorSpecificData({});
        setSensorAlignedData({});
        return;
      }

      try {
        const filterKey = (useFilteredData && selectedFilters.length > 0) 
          ? selectedFilters.sort().join(',') 
          : null;

        // Fetch sensor data with caching
        const sensorDataPromises = selectedSensors.map(async (sensorId) => {
          if (filterKey) {
            // Check filtered cache
            const cacheKey = `${sensorId}:${filterKey}`;
            if (sensorDataCache.filtered[cacheKey]) {
              return sensorDataCache.filtered[cacheKey];
            }
            
            // Fetch and cache filtered data
            const data = await fetchFilteredSensorData(selectedRun._id, sensorId, filterKey);
            setSensorDataCache(prev => ({
              ...prev,
              filtered: { ...prev.filtered, [cacheKey]: data }
            }));
            return data;
          } else {
            // Check raw cache
            if (sensorDataCache.raw[sensorId]) {
              return sensorDataCache.raw[sensorId];
            }
            
            // Fetch and cache raw data
            const data = await fetchSensorData(selectedRun._id, sensorId);
            setSensorDataCache(prev => ({
              ...prev,
              raw: { ...prev.raw, [sensorId]: data }
            }));
            return data;
          }
        });

        const results = await Promise.all(sensorDataPromises);
        setSensorReadings(results);

        // Build sensor-specific data map (already cached from above)
        const sensorDataMap = Object.fromEntries(
          selectedSensors.map((id, idx) => [id, results[idx]])
        );
        setSensorSpecificData(sensorDataMap);

        // Align to unified timeline
        const baseTs = selectedRun.totalTimestamps || [];
        const alignedMap = {};
        for (const [id, data] of Object.entries(sensorDataMap)) {
          alignedMap[id] = alignReadingsToTimeline(baseTs, data);
        }
        setSensorAlignedData(alignedMap);
      } catch (error) {
        console.error('Error fetching data:', error);
      }
    };

    fetchData();
  }, [selectedRun?._id, useFilteredData, selectedFilters, selectedSensors, sensorDataCache.raw, sensorDataCache.filtered]); // Added sensorDataCache dependency

  // Recompute traces when toggle changes
  const plotData = useMemo(() => {
    if (!selectedRun || !Array.isArray(selectedRun.totalTimestamps)) return [];
    if (!selectedSensors.length || Object.keys(sensorAlignedData).length === 0) return [];

    const sensorTraces = [];

    selectedSensors.forEach((sensorId) => {
      const aligned = sensorAlignedData[sensorId];
      if (!aligned) return;
      const axisCount = Array.isArray(aligned.axes) ? aligned.axes.length : 0;
      for (let axisIndex = 0; axisIndex < axisCount; axisIndex++) {
        sensorTraces.push({
          x: aligned.x,
          y: aligned.axes[axisIndex],
          type: 'scattergl',
          mode: 'lines',
          name: `Sensor ${sensorId} ${getAxisLabel(axisIndex, axisCount)}${useFilteredData ? ' (filtered)' : ''}`,
          visible: 'legendonly',
          yaxis: 'y',
          line: { width: 2 }
        });
      }
    });

    return sensorTraces;
  }, [selectedRun, sensorAlignedData, useFilteredData, selectedSensors])

  const highlightSectionShapes = useMemo(() => {
    if (!selectedSensors.length) return [];

    // Use the exact series loaded for the graph from /run/:id/sensor/:sensorId/data(+filters).
    const sensorId = selectedSensors[0];
    const readings = sensorSpecificData[sensorId];

    if (!Array.isArray(readings) || readings.length === 0) return [];

    const highlightSections = [];
    let isInSection = false;
    let sectionStart = null;

    readings.forEach((reading, idx) => {
      const zValue = reading?.data?.[2];
      if (typeof zValue !== 'number') return;

      if (zValue > 1.2 && !isInSection) {
        isInSection = true;
        sectionStart = idx;
      } else if (zValue < 1.1 && isInSection) {
        isInSection = false;
        const sectionEnd = idx;

        if (sectionStart !== null && sectionEnd !== null) {
          // Extract X values to check max X threshold
          const xValues = readings
            .slice(sectionStart, sectionEnd + 1)
            .map(r => r?.data?.[0])
            .filter(v => typeof v === 'number');
          
          const maxX = Math.max(...xValues);
          
          // Skip this segment if max X is not greater than 0.2
          if (maxX <= 0.2) {
            return;
          }

          // Extract Z values to find max
          const zValues = readings
            .slice(sectionStart, sectionEnd + 1)
            .map(r => r?.data?.[2])
            .filter(v => typeof v === 'number');
          
          const maxZ = Math.max(...zValues);
          
          // Dynamic window size based on max Z value
          // Adjust these thresholds and window sizes to fit your data
          let windowSize;
          if (maxZ > 3.0) {
            windowSize = 100;  // Very large Z, use big window
          } else if (maxZ > 2.1) {
            windowSize = 150;   // Large Z, use medium-large window
          } else if (maxZ > 1.5) {
            windowSize = 50;   // Medium Z, use medium window
          } else {
            windowSize = 10;   // Small Z, use smaller window
          }

          const yValues = readings
            .slice(sectionStart, sectionEnd + 1)
            .map(r => r?.data?.[1])
            .filter(v => typeof v === 'number');

          let firstExtreme = null;
          for (let i = windowSize; i < yValues.length - windowSize; i++) {
            // Check if current value is a maximum in the window
            const isMaximum = yValues.slice(i - windowSize, i + windowSize + 1).every((v, idx) => idx === windowSize || yValues[i] >= v);
            // Check if current value is a minimum in the window
            const isMinimum = yValues.slice(i - windowSize, i + windowSize + 1).every((v, idx) => idx === windowSize || yValues[i] <= v);
            
            if (isMaximum || isMinimum) {
              firstExtreme = yValues[i];
              break;
            }
          }

          // Skip this segment if no extreme was found
          if (firstExtreme === null) {
            return;
          }

          // Determine color: green if very close to zero, otherwise based on sign
          let color;
          if (Math.abs(firstExtreme) < 0.1) {
            color = 'rgba(0, 255, 0, 0.54)'; // Green for values close to zero
          } else {
            color = firstExtreme > 0 ? 'rgba(0, 255, 0, 0.54)' : 'rgba(255, 0, 0, 0.54)';
          }
          const x0 = readings[sectionStart]?.timestamp;
          const x1 = readings[sectionEnd]?.timestamp;

          if (typeof x0 === 'number' && typeof x1 === 'number') {
            highlightSections.push({ x0, x1, color });
          }
        }
      }
    });

    return highlightSections.map(({ x0, x1, color }) => ({
      type: 'rect',
      x0,
      x1,
      y0: 0,
      y1: 1,
      xref: 'x',
      yref: 'paper',
      fillcolor: color,
      opacity: 0.2,
      line: { width: 0 }
    }));
  }, [selectedSensors, sensorSpecificData]);

  // Modify the layout update effect to use aligned sensor data
  useEffect(() => {
    if (!run || !plotData.length || Object.keys(sensorAlignedData).length === 0) return;
    if (!Array.isArray(run.totalTimestamps) || run.totalTimestamps.length === 0) return;
    if (sliderValue < 0 || sliderValue >= run.totalTimestamps.length) return;

    const sensorColors = ['blue', 'red', 'green', 'orange', 'purple', 'teal'];
    const sensorList = selectedSensors.map((id, index) => ({
      id,
      label: id,
      color: sensorColors[index % sensorColors.length]
    }));

    const ts = run.totalTimestamps[sliderValue];
    const newShapes = [];
    const newAnnotations = [];

    sensorList.forEach(sensorInfo => {
        const aligned = sensorAlignedData[sensorInfo.id];
        if (!aligned) return;

        const axisCount = Array.isArray(aligned.axes) ? aligned.axes.length : 0;
        const axisValues = aligned.axes.map((axisSeries) => axisSeries[sliderValue]);
        const [vx, vy, vz] = axisValues;

        // Skip if no aligned value at this timeline index
        if (axisValues.every((value) => value == null)) return;

        // Check if any of the sensor's traces are visible in the legend
        const isTraceVisible = plotData.some(trace => 
            trace.name?.includes(`Sensor ${sensorInfo.label}`) && trace.visible !== "legendonly"
        );

        // Skip if all traces for this sensor are hidden
        if (!isTraceVisible) return;

        newShapes.push({
            type: 'line',
            x0: ts,
            x1: ts,
            y0: 0,
            y1: 1,
            xref: 'x',
            yref: 'paper',
            line: {
                color: sensorInfo.color,
                width: 2,
                dash: 'dashdot'
            }
        });

        const yOffset = newAnnotations.length * 0.1;
        // Check which axes are visible for this sensor
        const isXVisible = plotData.some(trace => 
            trace.name === `Sensor ${sensorInfo.label} X-axis` && trace.visible !== "legendonly"
        );
        const isYVisible = plotData.some(trace => 
            trace.name === `Sensor ${sensorInfo.label} Y-axis` && trace.visible !== "legendonly"
        );
        const isZVisible = plotData.some(trace => 
            trace.name === `Sensor ${sensorInfo.label} Z-axis` && trace.visible !== "legendonly"
        );

        // Build the text string based on visible axes
        let text = `${sensorInfo.label} - Time: ${ts}`;
        if (isXVisible) text += ` X: ${vx ?? '—'}`;
        if (isYVisible) text += ` Y: ${vy ?? '—'}`;
        if (isZVisible) text += ` Z: ${vz ?? '—'}`;

        newAnnotations.push({
            x: ts,
            y: 1 - yOffset,
            xref: 'x',
            yref: 'paper',
            yanchor: 'bottom',
            align: 'left',
            text: text,
            bordercolor: "black",
            borderwidth: 1,
            borderpad: 4,
            bgcolor: 'white',
            showarrow: false,
            xanchor: 'left'
        });
    });

    if (plotRef.current) {
      window.Plotly?.relayout(plotRef.current, {
        shapes: [...highlightSectionShapes, ...newShapes],
        annotations: newAnnotations
      });
    }
  }, [sliderValue, run, plotData, sensorAlignedData, highlightSectionShapes, selectedSensors]);

  // LUGE HIGHLIGHTS

  // useEffect(() => {
  //     const updateHighlightSections = () => {
  //         if (run && run.data && run.data.length > 0) {
  //             const accelerometer = run.data.find(d => d._id === "accelerometer");
  //             if (accelerometer && accelerometer.readings) {
  //                 const highlightSections = [];
  //                 let isInSection = false;
  //                 let sectionStart = null;
  //                 let sectionEnd = null;

  //                 accelerometer.readings.forEach((reading, idx) => {
  //                     const timestamp = formatTime(reading.timestamp);
  //                     const zValue = reading.data[2];

  //                     if (zValue > 1.25 && !isInSection) {
  //                         isInSection = true;
  //                         sectionStart = idx;
  //                     } else if (zValue < 1 && isInSection) {
  //                         isInSection = false;
  //                         sectionEnd = idx;

  //                         if (sectionStart !== null && sectionEnd !== null) {
  //                             const yValues = accelerometer.readings
  //                                 .slice(sectionStart, sectionEnd + 1)
  //                                 .map(r => r.data[1]);

  //                             // Find the first local extreme in Y values
  //                             let firstExtreme = null;
  //                             for (let i = 1; i < yValues.length - 1; i++) {
  //                                 if ((yValues[i] > yValues[i - 1] && yValues[i] > yValues[i + 1]) ||
  //                                     (yValues[i] < yValues[i - 1] && yValues[i] < yValues[i + 1])) {
  //                                     firstExtreme = yValues[i];
  //                                     break;
  //                                 }
  //                             }

  //                             // Determine the color based on the sign of the first extreme
  //                             const color = firstExtreme > 0
  //                                 ? 'rgba(0, 255, 0, 0.54)' // Positive extreme, green
  //                                 : 'rgba(255, 0, 0, 0.54)'; // Negative extreme, red

  //                             highlightSections.push({
  //                                 x0: formatTime(accelerometer.readings[sectionStart].timestamp),
  //                                 x1: formatTime(accelerometer.readings[sectionEnd].timestamp),
  //                                 color
  //                             });
  //                         }
  //                     }
  //                 });

  //                 const sectionShapes = highlightSections.map(({ x0, x1, color }) => ({
  //                     type: 'rect',
  //                     x0,
  //                     x1,
  //                     y0: 0,
  //                     y1: 1,
  //                     xref: 'x',
  //                     yref: 'paper',
  //                     fillcolor: color,
  //                     opacity: 0.2,
  //                     line: {
  //                         width: 0
  //                     }
  //                 }));

  //                 setGraphLayout(prev => ({
  //                     ...prev,
  //                     shapes: [
  //                         ...prev.shapes.filter(shape => shape.type !== 'rect'), // Preserve non-rect shapes (e.g., lines)
  //                         ...sectionShapes
  //                     ]
  //                 }));
  //             }
  //         }
  //     };

  //     updateHighlightSections();
  // }, [run, sliderValue]);

  //VIOLIN HIGHLIGHTS

  // useEffect(() => {
  //     const updateHighlightSections = () => {
  //         if (run && run.data && run.data.length > 0) {
  //             const accelerometer = run.data.find(d => d._id === "accelerometer");
  //             if (accelerometer && accelerometer.readings) {
  //                 // Check if accelerometer data is visible in the legend
  //                 const isAccelerometerVisible = plotData.some(
  //                     trace => trace.name?.includes("Accelerometer") && trace.visible !== "legendonly"
  //                 );

  //                 if (!isAccelerometerVisible) {
  //                     // If not visible, clear highlight sections
  //                     setGraphLayout(prev => ({
  //                         ...prev,
  //                         shapes: prev.shapes.filter(shape => shape.type !== "rect")
  //                     }));
  //                     return;
  //                 }

  //                 const highlightSections = [];
  //                 let isInSection = false;
  //                 let sectionStart = null;
  //                 let sectionEnd = null;

  //                 accelerometer.readings.forEach((reading, idx) => {
  //                     const timestamp = formatTime(reading.timestamp);
  //                     const zValue = reading.data[0];

  //                     if (zValue < 0 && !isInSection) {
  //                         isInSection = true;
  //                         sectionStart = idx;
  //                     } else if (zValue > 0 && isInSection) {
  //                         isInSection = false;
  //                         sectionEnd = idx;

  //                         if (sectionStart !== null && sectionEnd !== null) {
  //                             const color = "rgba(0, 255, 0, 0.54)"; // Highlight color

  //                             highlightSections.push({
  //                                 x0: formatTime(accelerometer.readings[sectionStart].timestamp),
  //                                 x1: formatTime(accelerometer.readings[sectionEnd].timestamp),
  //                                 color
  //                             });
  //                         }
  //                     }
  //                 });

  //                 const sectionShapes = highlightSections.map(({ x0, x1, color }) => ({
  //                     type: "rect",
  //                     x0,
  //                     x1,
  //                     y0: 0,
  //                     y1: 1,
  //                     xref: "x",
  //                     yref: "paper",
  //                     fillcolor: color,
  //                     opacity: 0.2,
  //                     line: {
  //                         width: 0
  //                     }
  //                 }));

  //                 setGraphLayout(prev => ({
  //                     ...prev,
  //                     shapes: [
  //                         ...prev.shapes.filter(shape => shape.type !== "rect"), // Preserve non-rect shapes
  //                         ...sectionShapes
  //                     ]
  //                 }));
  //             }
  //         }
  //     };

  //     updateHighlightSections();
  // }, [run, sliderValue, plotData]);

    

    return (
        <>
            {/* Show message based on sensor selection state */}
            {selectedSensors.length === 0 && availableSensors.length > 0 && (
              <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                Please select sensor data to display
              </div>
            )}

            {selectedSensors.length > 0 && !plotData.length && (
              <div style={{ textAlign: 'center', padding: '20px' }}>
                Loading sensor data...
              </div>
            )}

            {/* Sensor Selection */}
            <details className="card mb-3 sensors-collapsible">
              <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: 'none', cursor: 'pointer' }}>
                <strong>Sensors</strong>
                <span className="badge bg-secondary">
                  {selectedSensors.length} / {availableSensors.length}
                </span>
              </summary>

              <div className="card-body">
                <div className="list-group">
                  {availableSensors.length === 0 && (
                    <div className="text-muted small">No sensors available</div>
                  )}

                  {availableSensors.map(sensorId => (
                    <label
                      key={sensorId}
                      className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center ${selectedSensors.includes(sensorId) ? 'active' : ''}`}
                      role="button"
                    >
                      <div className="form-check d-flex align-items-center m-0">
                        <input
                          id={`sensor-${sensorId}`}
                          className="form-check-input me-2"
                          type="checkbox"
                          checked={selectedSensors.includes(sensorId)}
                          onChange={() => toggleSensor(sensorId)}
                        />
                        <span className="form-check-label">Sensor {sensorId}</span>
                      </div>

                      <div className="text-end">
                        <small className="text-muted">ID: {sensorId}</small>
                      </div>
                    </label>
                  ))}
                </div>

                <div className="d-flex mt-3">
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-primary me-2 flex-fill"
                    onClick={() => setSelectedSensors([...availableSensors])}
                    disabled={availableSensors.length === 0}
                  >
                    Select All
                  </button>

                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary flex-fill"
                    onClick={() => setSelectedSensors([])}
                    disabled={availableSensors.length === 0}
                  >
                    Clear All
                  </button>
                </div>
              </div>
            </details>

            {/* Filter Selection */}
            <details className="card mb-3 filters-collapsible">
  <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: 'none', cursor: 'pointer' }}>
    <strong>Filters</strong>
    <span className={`badge ${useFilteredData ? 'bg-success' : 'bg-secondary'}`}>
      {useFilteredData ? 'Active' : 'Inactive'} ({pendingFilters.length} selected)
    </span>
  </summary>

  <div className="card-body">
    {/* Display selected filters in order at the top */}
    {pendingFilters.length > 0 && (
      <>
        <div className="mb-3">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <small className="text-muted"><strong>Filter Pipeline (Top → Bottom):</strong></small>
            <small className="text-muted">Drag to reorder</small>
          </div>
          <div className="list-group">
            {pendingFilters.map((filterId, index) => {
              const filter = availableFilters.find(f => f.id === filterId);
              return (
                <div
                  key={filterId}
                  className="list-group-item list-group-item-action d-flex justify-content-between align-items-center active"
                  draggable={true}
                  onDragStart={(e) => handleDragStart(e, filterId)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, filterId)}
                  onDragEnd={handleDragEnd}
                  style={{ 
                    cursor: 'move',
                    opacity: draggedFilter === filterId ? 0.5 : 1
                  }}
                >
                  <div className="d-flex align-items-center">
                    <span className="badge bg-light text-dark me-2" style={{ fontSize: '0.8rem' }}>
                      ☰
                    </span>
                    <span className="badge bg-primary me-2">{index + 1}</span>
                    <span>{filter?.label}</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm btn-close"
                    aria-label="Remove"
                    onClick={(e) => {
                      e.preventDefault();
                      toggleFilter(filterId);
                    }}
                  />
                </div>
              );
            })}
          </div>
        </div>
        <hr />
      </>
    )}

    {/* Available filters to select */}
    <div className="mb-2">
      <small className="text-muted"><strong>Available Filters:</strong></small>
    </div>
    <div className="list-group">
      {availableFilters
        .filter(filter => !pendingFilters.includes(filter.id))
        .map(filter => (
          <label
            key={filter.id}
            className="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
            role="button"
          >
            <div className="form-check d-flex align-items-center m-0">
              <input
                id={`filter-${filter.id}`}
                className="form-check-input me-2"
                type="checkbox"
                checked={false}
                onChange={() => toggleFilter(filter.id)}
              />
              <span className="form-check-label">{filter.label}</span>
            </div>
          </label>
        ))}
      
      {availableFilters.filter(f => !pendingFilters.includes(f.id)).length === 0 && (
        <div className="text-muted small">All filters selected</div>
      )}
    </div>

    <div className="d-flex mt-3 gap-2">
      {useFilteredData ? (
        <button
          type="button"
          className="btn btn-sm btn-outline-danger flex-fill"
          onClick={disableFilters}
        >
          Disable Filters
        </button>
      ) : (
        <button
          type="button"
          className="btn btn-sm btn-outline-primary flex-fill"
          onClick={applyFilters}
          disabled={pendingFilters.length === 0}
          title={pendingFilters.length === 0 ? 'Select at least one filter' : `Apply filters in order: ${pendingFilters.join(' → ')}`}
        >
          Apply Filters
        </button>
      )}
    </div>

    {useFilteredData && selectedFilters.length > 0 && (
      <div className="alert alert-success mt-3 mb-0 py-2 px-3" style={{ fontSize: '0.85rem' }}>
        <strong>Active filters:</strong> {selectedFilters.map((f, i) => (
          <span key={f}>
            {availableFilters.find(af => af.id === f)?.label}
            {i < selectedFilters.length - 1 && ' → '}
          </span>
        ))}
      </div>
    )}
  </div>
</details>

            {run && plotData.length > 0 && (
                <Plot
                    data={plotData}
                    layout={graphLayout}
                    style={{ width: '100%', height: '100%' }}
                    onInitialized={(_, graphDiv) => { plotRef.current = graphDiv; }}
                    onUpdate={(_, graphDiv) => { plotRef.current = graphDiv; }}
                    config={{       
                        responsive: true,
                        scrollZoom: true,
                        displayModeBar: true,
                        displaylogo: false,
                        modeBarButtonsToRemove: [
                            'zoom2d',
                            'pan2d',
                            'toImage',
                            'lasso2d',
                            'select2d',
                            'autoscale2d',
                            'sendDataToCloud'
                        ],
                        modeBarButtonsToAdd: [
                            {
                                name: 'Remove Graph',
                                icon: Plotly.Icons['selectbox'],
                                click: () => removeFunction()
                            }
                        ]
                    }}
                />
            )}
        </>
    )
}

export default PlotlyGraphVisualizer
