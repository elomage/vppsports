import { useEffect, useMemo, useRef, useState } from "react";
import Plot from "react-plotly.js";
import "./PlotlyGraphvisualizer2.css";

const SERVER_URL = import.meta.env.VITE_SERVER_URL;
const ACCESS_TOKEN_STORAGE_KEY = "vppsports_access_token";
const DEFAULT_PLOT_RESOLUTION = 1400;
const UIREVISION_VALUE = "keep";

const getAuthHeaders = () => {
  const token = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const buildSensorDataUrl = (runId, sensorId, options = {}) => {
  const params = new URLSearchParams();
  if (options.filters) params.set("filters", options.filters);
  if (options.mode) params.set("mode", options.mode);
  if (Number.isFinite(options.start)) params.set("start", String(options.start));
  if (Number.isFinite(options.end)) params.set("end", String(options.end));
  if (Number.isFinite(options.resolution)) {
    params.set("resolution", String(options.resolution));
  }

  const query = params.toString();
  return `${SERVER_URL}/run/${runId}/sensor/${sensorId}/data${query ? `?${query}` : ""}`;
};

const fetchJson = async (url) => {
  const response = await fetch(url, {
    headers: getAuthHeaders(),
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Network response was not ok");
  }

  return response.json();
};

const fetchSensorData = async (runId, sensorId, options = {}) => {
  return fetchJson(buildSensorDataUrl(runId, sensorId, options));
};

const fetchRunSensors = async (runId) => {
  return fetchJson(`${SERVER_URL}/run/${runId}/sensor`);
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
    return ["X-axis", "Y-axis", "Z-axis"][axisIndex] || `Axis ${axisIndex + 1}`;
  }
  return `raw_value${axisIndex + 1}`;
};

const normalizeSeriesPayload = (payload) => {
  if (Array.isArray(payload)) {
    return { readings: payload, sampleCountRaw: payload.length, sampleCountReturned: payload.length };
  }

  return {
    readings: Array.isArray(payload?.readings) ? payload.readings : [],
    sampleCountRaw: payload?.sampleCountRaw ?? 0,
    sampleCountReturned: payload?.sampleCountReturned ?? 0,
  };
};

const getInitialRange = (run) => {
  const timestamps = run?.totalTimestamps;
  if (!Array.isArray(timestamps) || timestamps.length === 0) {
    return { start: null, end: null };
  }

  return {
    start: timestamps[0],
    end: timestamps[timestamps.length - 1],
  };
};

const getNearestReading = (readings, timestamp) => {
  if (!Array.isArray(readings) || readings.length === 0 || !Number.isFinite(timestamp)) {
    return null;
  }

  let lo = 0;
  let hi = readings.length - 1;

  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (readings[mid].timestamp < timestamp) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }

  if (lo === 0) return readings[0];
  const current = readings[lo];
  const previous = readings[lo - 1];
  if (!current) return previous ?? null;
  return Math.abs(current.timestamp - timestamp) < Math.abs(previous.timestamp - timestamp)
    ? current
    : previous;
};

const getPlotResolution = () => {
  if (typeof window === "undefined") return DEFAULT_PLOT_RESOLUTION;
  const width = window.innerWidth || DEFAULT_PLOT_RESOLUTION;
  return Math.max(400, Math.min(Math.floor(width * 1.5), 2400));
};

const getCacheKey = (runId, sensorId, options = {}) => {
  const normalized = {
    mode: options.mode || "raw",
    start: Number.isFinite(options.start) ? options.start : "",
    end: Number.isFinite(options.end) ? options.end : "",
    filters: options.filters || "",
    resolution: Number.isFinite(options.resolution) ? options.resolution : "",
  };
  return `${runId}:${sensorId}:${normalized.mode}:${normalized.start}:${normalized.end}:${normalized.filters}:${normalized.resolution}`;
};

const filterKeyFromSelection = (useFilteredData, selectedFilters) => {
  if (!useFilteredData || selectedFilters.length === 0) return "";
  return selectedFilters.join(",");
};

const getSensorOffset = (offsetsBySensor, sensorId) => {
  const offset = offsetsBySensor[sensorId];
  return Number.isFinite(offset) ? offset : 0;
};

const PlotlyGraphVisualizer = ({ selectedRun, sliderValue, removeFunction }) => {
  const [useFilteredData, setUseFilteredData] = useState(false);
  const [selectedFilters, setSelectedFilters] = useState([]);
  const [pendingFilters, setPendingFilters] = useState([]);
  const [availableSensors, setAvailableSensors] = useState([]);
  const [selectedSensors, setSelectedSensors] = useState([]);
  const [sensorSyncOffsets, setSensorSyncOffsets] = useState({});
  const [draggedFilter, setDraggedFilter] = useState(null);
  const [plotSeriesBySensor, setPlotSeriesBySensor] = useState({});
  const [rawSeriesBySensor, setRawSeriesBySensor] = useState({});
  const [visibleRange, setVisibleRange] = useState(() => getInitialRange(selectedRun));
  const [plotResolution, setPlotResolution] = useState(getPlotResolution);
  const [traceVisibility, setTraceVisibility] = useState({});
  const [isPlotLoading, setIsPlotLoading] = useState(false);
  const [isRawLoading, setIsRawLoading] = useState(false);
  const [sliderReadout, setSliderReadout] = useState([]);

  const cacheRef = useRef({
    plot: new Map(),
    raw: new Map(),
  });
  const plotRef = useRef(null);
  const plotRequestIdRef = useRef(0);
  const rawRequestIdRef = useRef(0);

  const availableFilters = [
    { id: "kalman", label: "Kalman" },
    { id: "movingaverage", label: "MovAvg" },
    { id: "savitzkygolay", label: "SavGol" },
  ];

  const run = selectedRun;
  const filterKey = filterKeyFromSelection(useFilteredData, selectedFilters);

  const graphLayout = useMemo(
    () => ({
      autosize: true,
      dragmode: "pan",
      margin: { l: 0, r: 10, t: 30, b: 0 },
      xaxis: { title: "Timestamp", showticklabels: false, fixedrange: false },
      yaxis: { title: "Sensor Reading", fixedrange: true },
      legend: { font: { size: 16 } },
      uirevision: UIREVISION_VALUE,
      shapes: [],
      annotations: [],
    }),
    []
  );

  useEffect(() => {
    const handleResize = () => setPlotResolution(getPlotResolution());
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    cacheRef.current = {
      plot: new Map(),
      raw: new Map(),
    };
    setPlotSeriesBySensor({});
    setRawSeriesBySensor({});
    setVisibleRange(getInitialRange(selectedRun));
    setTraceVisibility({});
    setSensorSyncOffsets({});
    setSliderReadout([]);
    setIsPlotLoading(false);
    setIsRawLoading(false);
    plotRequestIdRef.current += 1;
    rawRequestIdRef.current += 1;
  }, [selectedRun?._id]);

  useEffect(() => {
    const loadAvailableSensors = async () => {
      if (!selectedRun?._id) return;

      try {
        const sensors = await fetchRunSensors(selectedRun._id);
        setAvailableSensors(sensors);
        setSelectedSensors([]);
      } catch (error) {
        console.error("Error loading available sensors:", error);
      }
    };

    loadAvailableSensors();
  }, [selectedRun?._id]);

  const toggleSensor = (sensorId) => {
    setSelectedSensors((prev) =>
      prev.includes(sensorId) ? prev.filter((id) => id !== sensorId) : [...prev, sensorId]
    );
  };

  const toggleFilter = (name) => {
    setPendingFilters((prev) =>
      prev.includes(name) ? prev.filter((f) => f !== name) : [...prev, name]
    );
  };

  const handleDragStart = (event, filterId) => {
    setDraggedFilter(filterId);
    event.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };

  const handleDrop = (event, targetFilterId) => {
    event.preventDefault();
    if (draggedFilter === targetFilterId) return;

    setPendingFilters((prev) => {
      const next = [...prev];
      const draggedIndex = next.indexOf(draggedFilter);
      const targetIndex = next.indexOf(targetFilterId);
      if (draggedIndex === -1 || targetIndex === -1) return prev;

      next.splice(draggedIndex, 1);
      next.splice(targetIndex, 0, draggedFilter);
      return next;
    });
    setDraggedFilter(null);
  };

  const handleDragEnd = () => {
    setDraggedFilter(null);
  };

  const applyFilters = () => {
    setSelectedFilters(pendingFilters);
    setUseFilteredData(true);
  };

  const disableFilters = () => {
    setUseFilteredData(false);
    setPendingFilters(selectedFilters);
  };

  useEffect(() => {
    setSensorSyncOffsets((prev) => {
      const next = {};
      let changed = false;

      selectedSensors.forEach((sensorId) => {
        if (Number.isFinite(prev[sensorId])) {
          next[sensorId] = prev[sensorId];
        } else {
          next[sensorId] = 0;
          changed = true;
        }
      });

      if (Object.keys(prev).length !== selectedSensors.length) {
        changed = true;
      }

      return changed ? next : prev;
    });
  }, [selectedSensors]);

  useEffect(() => {
    const requestId = ++plotRequestIdRef.current;

    const loadPlotSeries = async () => {
      if (!selectedRun?._id || selectedSensors.length === 0) {
        if (requestId !== plotRequestIdRef.current) return;
        setPlotSeriesBySensor({});
        setIsPlotLoading(false);
        return;
      }

      setIsPlotLoading(true);

      const nextPlotSeriesEntries = await Promise.all(
        selectedSensors.map(async (sensorId) => {
          const cacheKey = getCacheKey(selectedRun._id, sensorId, {
            mode: "plot",
            start: visibleRange.start,
            end: visibleRange.end,
            filters: filterKey,
            resolution: plotResolution,
          });

          let cached = cacheRef.current.plot.get(cacheKey);
          if (!cached) {
            cached = fetchSensorData(selectedRun._id, sensorId, {
              mode: "plot",
              start: visibleRange.start,
              end: visibleRange.end,
              filters: filterKey || undefined,
              resolution: plotResolution,
            }).then(normalizeSeriesPayload);
            cacheRef.current.plot.set(cacheKey, cached);
          }

          const payload = await cached;
          return [sensorId, payload];
        })
      );

      if (requestId !== plotRequestIdRef.current) return;
      setPlotSeriesBySensor(Object.fromEntries(nextPlotSeriesEntries));
      setIsPlotLoading(false);
    };

    loadPlotSeries().catch((error) => {
      if (requestId === plotRequestIdRef.current) {
        setIsPlotLoading(false);
      }
      console.error("Error loading plot series:", error);
    });

    return () => {
      plotRequestIdRef.current += 1;
    };
  }, [
    selectedRun?._id,
    selectedSensors,
    visibleRange.start,
    visibleRange.end,
    filterKey,
    plotResolution,
  ]);

  useEffect(() => {
    const requestId = ++rawRequestIdRef.current;

    const loadRawSeries = async () => {
      if (!selectedRun?._id || selectedSensors.length === 0) {
        if (requestId !== rawRequestIdRef.current) return;
        setRawSeriesBySensor({});
        setIsRawLoading(false);
        return;
      }

      setIsRawLoading(true);

      const nextRawSeriesEntries = await Promise.all(
        selectedSensors.map(async (sensorId) => {
          const cacheKey = getCacheKey(selectedRun._id, sensorId, {
            mode: "raw",
            filters: filterKey,
          });

          let cached = cacheRef.current.raw.get(cacheKey);
          if (!cached) {
            cached = fetchSensorData(selectedRun._id, sensorId, {
              mode: "raw",
              filters: filterKey || undefined,
            });
            cacheRef.current.raw.set(cacheKey, cached);
          }

          const readings = await cached;
          return [sensorId, Array.isArray(readings) ? readings : []];
        })
      );

      if (requestId !== rawRequestIdRef.current) return;
      setRawSeriesBySensor(Object.fromEntries(nextRawSeriesEntries));
      setIsRawLoading(false);
    };

    loadRawSeries().catch((error) => {
      if (requestId === rawRequestIdRef.current) {
        setIsRawLoading(false);
      }
      console.error("Error loading raw series:", error);
    });

    return () => {
      rawRequestIdRef.current += 1;
    };
  }, [selectedRun?._id, selectedSensors, filterKey]);

  const plotData = useMemo(() => {
    if (!selectedSensors.length) return [];

    const traces = [];

    selectedSensors.forEach((sensorId) => {
      const payload = plotSeriesBySensor[sensorId];
      const readings = payload?.readings;
      if (!Array.isArray(readings) || readings.length === 0) return;

      const axisCount = getAxisCount(readings);
      const syncOffset = getSensorOffset(sensorSyncOffsets, sensorId);
      const timestamps = readings.map((reading) => reading.timestamp + syncOffset);

      for (let axisIndex = 0; axisIndex < axisCount; axisIndex++) {
        const traceName = `Sensor ${sensorId} ${getAxisLabel(axisIndex, axisCount)}${useFilteredData ? " (filtered)" : ""}`;
        traces.push({
          x: timestamps,
          y: readings.map((reading) => reading.data?.[axisIndex] ?? null),
          type: "scattergl",
          mode: "lines",
          name: traceName,
          visible: traceVisibility[traceName] ?? "legendonly",
          yaxis: "y",
          line: { width: 2 },
        });
      }
    });

    return traces;
  }, [plotSeriesBySensor, selectedSensors, sensorSyncOffsets, traceVisibility, useFilteredData]);

  const highlightSectionShapes = useMemo(() => {
    if (!selectedSensors.length) return [];

    const sensorId = selectedSensors[0];
    const readings = rawSeriesBySensor[sensorId];
    if (!Array.isArray(readings) || readings.length === 0) return [];
    const syncOffset = getSensorOffset(sensorSyncOffsets, sensorId);

    const highlightSections = [];
    let isInSection = false;
    let sectionStart = null;

    readings.forEach((reading, index) => {
      const zValue = reading?.data?.[2];
      if (typeof zValue !== "number") return;

      if (zValue > 1.2 && !isInSection) {
        isInSection = true;
        sectionStart = index;
      } else if (zValue < 1.1 && isInSection) {
        isInSection = false;
        const sectionEnd = index;

        if (sectionStart === null) return;

        const sectionReadings = readings.slice(sectionStart, sectionEnd + 1);
        const xValues = sectionReadings
          .map((entry) => entry?.data?.[0])
          .filter((value) => typeof value === "number");

        const maxX = xValues.length ? Math.max(...xValues) : Number.NEGATIVE_INFINITY;
        if (!(maxX > 0.2)) return;

        const zValues = sectionReadings
          .map((entry) => entry?.data?.[2])
          .filter((value) => typeof value === "number");
        const maxZ = zValues.length ? Math.max(...zValues) : 0;

        let windowSize = 10;
        if (maxZ > 3.0) windowSize = 100;
        else if (maxZ > 2.1) windowSize = 150;
        else if (maxZ > 1.5) windowSize = 50;

        const yValues = sectionReadings
          .map((entry) => entry?.data?.[1])
          .filter((value) => typeof value === "number");

        let firstExtreme = null;
        for (let i = windowSize; i < yValues.length - windowSize; i++) {
          const current = yValues[i];
          const windowValues = yValues.slice(i - windowSize, i + windowSize + 1);
          const isMaximum = windowValues.every((value, idx) => idx === windowSize || current >= value);
          const isMinimum = windowValues.every((value, idx) => idx === windowSize || current <= value);

          if (isMaximum || isMinimum) {
            firstExtreme = current;
            break;
          }
        }

        if (firstExtreme === null) return;

        const color =
          Math.abs(firstExtreme) < 0.1 || firstExtreme > 0
            ? "rgba(0, 255, 0, 0.54)"
            : "rgba(255, 0, 0, 0.54)";

        const x0 = readings[sectionStart]?.timestamp + syncOffset;
        const x1 = readings[sectionEnd]?.timestamp + syncOffset;
        if (typeof x0 !== "number" || typeof x1 !== "number") return;

        highlightSections.push({
          type: "rect",
          x0,
          x1,
          y0: 0,
          y1: 1,
          xref: "x",
          yref: "paper",
          fillcolor: color,
          opacity: 0.2,
          line: { width: 0 },
        });
      }
    });

    return highlightSections;
  }, [rawSeriesBySensor, selectedSensors, sensorSyncOffsets]);

  useEffect(() => {
    if (!run || !plotData.length || !Array.isArray(run.totalTimestamps)) return;
    if (sliderValue < 0 || sliderValue >= run.totalTimestamps.length) return;
    if (!plotRef.current || !window.Plotly) return;

    const currentTraces = plotRef.current.data || plotData;
    const ts = run.totalTimestamps[sliderValue];
    const visibleTraceNames = new Set(
      currentTraces
        .filter((trace) => trace?.visible !== "legendonly")
        .map((trace) => trace.name)
    );
    const readoutEntries = [];

    selectedSensors.forEach((sensorId) => {
      const readings = rawSeriesBySensor[sensorId];
      const syncOffset = getSensorOffset(sensorSyncOffsets, sensorId);
      const nearest = getNearestReading(readings, ts - syncOffset);
      if (!nearest) return;

      const isTraceVisible = currentTraces.some(
        (trace) => trace.name?.includes(`Sensor ${sensorId}`) && trace.visible !== "legendonly"
      );
      if (!isTraceVisible) return;

      const axisCount = Array.isArray(nearest.data) ? nearest.data.length : 0;
      const axes = [];

      for (let axisIndex = 0; axisIndex < axisCount; axisIndex++) {
        const axisName = getAxisLabel(axisIndex, axisCount);
        const fullName = `Sensor ${sensorId} ${axisName}${useFilteredData ? " (filtered)" : ""}`;
        const axisVisible = visibleTraceNames.has(fullName);
        if (axisVisible) {
          axes.push({
            name: axisName.replace("-axis", ""),
            value: nearest.data?.[axisIndex] ?? "-",
          });
        }
      }

      readoutEntries.push({
        sensorId,
        timelineTimestamp: ts,
        sensorTimestamp: nearest.timestamp,
        shift: syncOffset,
        axes,
      });
    });

    setSliderReadout((prev) => {
      if (JSON.stringify(prev) === JSON.stringify(readoutEntries)) {
        return prev;
      }
      return readoutEntries;
    });

    window.Plotly.relayout(plotRef.current, {
      shapes: [
        ...highlightSectionShapes,
        {
          type: "line",
          x0: ts,
          x1: ts,
          y0: 0,
          y1: 1,
          xref: "x",
          yref: "paper",
          line: {
            color: "#1f77b4",
            width: 2,
            dash: "dashdot",
          },
        },
      ],
      annotations: [],
    });
  }, [
    sliderValue,
    run,
    plotData,
    rawSeriesBySensor,
    highlightSectionShapes,
    selectedSensors,
    sensorSyncOffsets,
    useFilteredData,
  ]);

  const handleSyncOffsetChange = (sensorId, value) => {
    if (value === "" || value === "-" || value === "." || value === "-.") {
      setSensorSyncOffsets((prev) => ({ ...prev, [sensorId]: 0 }));
      return;
    }

    const parsedValue = Number(value);
    if (!Number.isFinite(parsedValue)) return;

    setSensorSyncOffsets((prev) => {
      if (prev[sensorId] === parsedValue) return prev;
      return { ...prev, [sensorId]: parsedValue };
    });
  };

  const nudgeSyncOffset = (sensorId, delta) => {
    setSensorSyncOffsets((prev) => ({
      ...prev,
      [sensorId]: getSensorOffset(prev, sensorId) + delta,
    }));
  };

  const resetAllSyncOffsets = () => {
    setSensorSyncOffsets(
      Object.fromEntries(selectedSensors.map((sensorId) => [sensorId, 0]))
    );
  };

  const handleRelayout = (eventData) => {
    if (!selectedRun) return;

    if (eventData["xaxis.autorange"]) {
      setVisibleRange(getInitialRange(selectedRun));
      return;
    }

    const start = Number(eventData["xaxis.range[0]"]);
    const end = Number(eventData["xaxis.range[1]"]);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;

    setVisibleRange((prev) => {
      if (prev.start === start && prev.end === end) return prev;
      return { start, end };
    });
  };

  const syncTraceVisibility = (graphDiv) => {
    const traces = graphDiv?.data;
    if (!Array.isArray(traces)) return;

    setTraceVisibility((prev) => {
      const next = { ...prev };
      let changed = false;

      traces.forEach((trace) => {
        if (!trace?.name) return;
        const visibleValue = trace.visible ?? true;
        if (next[trace.name] !== visibleValue) {
          next[trace.name] = visibleValue;
          changed = true;
        }
      });

      return changed ? next : prev;
    });
  };

  return (
    <>
      {(isPlotLoading || isRawLoading) && selectedSensors.length > 0 && (
        <div
          className="alert alert-info py-2 px-3 mb-3"
          style={{ fontSize: "0.9rem" }}
        >
          {isPlotLoading ? "Updating plot data..." : "Syncing sensor data..."}
        </div>
      )}

      {selectedSensors.length === 0 && availableSensors.length > 0 && (
        <div style={{ textAlign: "center", padding: "20px", color: "#666" }}>
          Please select sensor data to display
        </div>
      )}

      {selectedSensors.length > 0 && !plotData.length && isPlotLoading && (
        <div style={{ textAlign: "center", padding: "20px" }}>
          Loading sensor data...
        </div>
      )}

      <details className="card mb-3 sensors-collapsible">
        <summary
          className="card-header d-flex justify-content-between align-items-center"
          style={{ listStyle: "none", cursor: "pointer" }}
        >
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

            {availableSensors.map((sensorId) => (
              <label
                key={sensorId}
                className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center ${selectedSensors.includes(sensorId) ? "active" : ""}`}
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

      <details className="card mb-3 sync-collapsible">
        <summary
          className="card-header d-flex justify-content-between align-items-center"
          style={{ listStyle: "none", cursor: "pointer" }}
        >
          <strong>Synchronization</strong>
          <span className="badge bg-secondary">
            {selectedSensors.filter((sensorId) => getSensorOffset(sensorSyncOffsets, sensorId) !== 0).length} shifted
          </span>
        </summary>

        <div className="card-body">
          <p className="text-muted small mb-3">
            Use the main time slider to inspect alignment, then adjust each sensor offset so every trace follows the same timeline.
          </p>

          {selectedSensors.length === 0 && (
            <div className="text-muted small">Select at least one sensor to sync.</div>
          )}

          {selectedSensors.length > 0 && (
            <>
              <div className="sync-offset-list">
                {selectedSensors.map((sensorId) => {
                  const offset = getSensorOffset(sensorSyncOffsets, sensorId);
                  return (
                    <div key={sensorId} className="sync-offset-row">
                      <div>
                        <strong>Sensor {sensorId}</strong>
                      </div>
                      <div className="sync-offset-controls">
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          onClick={() => nudgeSyncOffset(sensorId, -1)}
                        >
                          -1
                        </button>
                        <input
                          type="number"
                          step="any"
                          className="form-control form-control-sm sync-offset-input"
                          value={offset}
                          onChange={(event) => handleSyncOffsetChange(sensorId, event.target.value)}
                        />
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          onClick={() => nudgeSyncOffset(sensorId, 1)}
                        >
                          +1
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-danger"
                          onClick={() => handleSyncOffsetChange(sensorId, "0")}
                        >
                          Reset
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="d-flex justify-content-end mt-3">
                <button
                  type="button"
                  className="btn btn-sm btn-outline-danger"
                  onClick={resetAllSyncOffsets}
                >
                  Reset All Offsets
                </button>
              </div>
            </>
          )}
        </div>
      </details>

      <details className="card mb-3 filters-collapsible">
        <summary
          className="card-header d-flex justify-content-between align-items-center"
          style={{ listStyle: "none", cursor: "pointer" }}
        >
          <strong>Filters</strong>
          <span className={`badge ${useFilteredData ? "bg-success" : "bg-secondary"}`}>
            {useFilteredData ? "Active" : "Inactive"} ({pendingFilters.length} selected)
          </span>
        </summary>

        <div className="card-body">
          {pendingFilters.length > 0 && (
            <>
              <div className="mb-3">
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <small className="text-muted">
                    <strong>Filter Pipeline (Top -&gt; Bottom):</strong>
                  </small>
                  <small className="text-muted">Drag to reorder</small>
                </div>
                <div className="list-group">
                  {pendingFilters.map((filterId, index) => {
                    const filter = availableFilters.find((item) => item.id === filterId);
                    return (
                      <div
                        key={filterId}
                        className="list-group-item list-group-item-action d-flex justify-content-between align-items-center active"
                        draggable
                        onDragStart={(event) => handleDragStart(event, filterId)}
                        onDragOver={handleDragOver}
                        onDrop={(event) => handleDrop(event, filterId)}
                        onDragEnd={handleDragEnd}
                        style={{
                          cursor: "move",
                          opacity: draggedFilter === filterId ? 0.5 : 1,
                        }}
                      >
                        <div className="d-flex align-items-center">
                          <span className="badge bg-light text-dark me-2" style={{ fontSize: "0.8rem" }}>
                            ===
                          </span>
                          <span className="badge bg-primary me-2">{index + 1}</span>
                          <span>{filter?.label}</span>
                        </div>
                        <button
                          type="button"
                          className="btn btn-sm btn-close"
                          aria-label="Remove"
                          onClick={(event) => {
                            event.preventDefault();
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

          <div className="mb-2">
            <small className="text-muted">
              <strong>Available Filters:</strong>
            </small>
          </div>
          <div className="list-group">
            {availableFilters
              .filter((filter) => !pendingFilters.includes(filter.id))
              .map((filter) => (
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

            {availableFilters.filter((filter) => !pendingFilters.includes(filter.id)).length === 0 && (
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
                title={
                  pendingFilters.length === 0
                    ? "Select at least one filter"
                    : `Apply filters in order: ${pendingFilters.join(" -> ")}`
                }
              >
                Apply Filters
              </button>
            )}
          </div>

          {useFilteredData && selectedFilters.length > 0 && (
            <div className="alert alert-success mt-3 mb-0 py-2 px-3" style={{ fontSize: "0.85rem" }}>
              <strong>Active filters:</strong>{" "}
              {selectedFilters.map((filter, index) => (
                <span key={filter}>
                  {availableFilters.find((item) => item.id === filter)?.label}
                  {index < selectedFilters.length - 1 && " -> "}
                </span>
              ))}
            </div>
          )}
        </div>
      </details>

      {run && plotData.length > 0 && (
        <>
          {sliderReadout.length > 0 && (
            <div className="plot-readout">
              {sliderReadout.map((entry) => (
                <div key={entry.sensorId} className="plot-readout__item">
                  <strong>Sensor {entry.sensorId}</strong>
                  <span>Timeline: {entry.timelineTimestamp}</span>
                  <span>Sensor: {entry.sensorTimestamp}</span>
                  {entry.shift !== 0 && (
                    <span>Shift: {entry.shift >= 0 ? "+" : ""}{entry.shift}</span>
                  )}
                  {entry.axes.map((axis) => (
                    <span key={`${entry.sensorId}-${axis.name}`}>
                      {axis.name}: {axis.value}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          )}
          <Plot
            data={plotData}
            layout={graphLayout}
            style={{ width: "100%", height: "100%" }}
            onInitialized={(_, graphDiv) => {
              plotRef.current = graphDiv;
              syncTraceVisibility(graphDiv);
            }}
            onUpdate={(_, graphDiv) => {
              plotRef.current = graphDiv;
              syncTraceVisibility(graphDiv);
            }}
            onRelayout={handleRelayout}
            onRestyle={(_, graphDiv) => {
              plotRef.current = graphDiv;
              syncTraceVisibility(graphDiv);
            }}
            config={{
              responsive: true,
              scrollZoom: true,
              displayModeBar: true,
              displaylogo: false,
              modeBarButtonsToRemove: [
                "zoom2d",
                "pan2d",
                "toImage",
                "lasso2d",
                "select2d",
                "autoscale2d",
                "sendDataToCloud",
              ],
              modeBarButtonsToAdd: [
                {
                  name: "Remove Graph",
                  icon: Plotly.Icons.selectbox,
                  click: () => removeFunction(),
                },
              ],
            }}
          />
        </>
      )}
    </>
  );
};

export default PlotlyGraphVisualizer;
