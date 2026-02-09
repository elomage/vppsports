import { useState, useEffect, useMemo } from 'react'
import Plot from 'react-plotly.js'

const PlotlyGraphVisualizer = ({ selectedRun, sliderValue, removeFunction }) => {
    const [useFilteredData, setUseFilteredData] = useState(false) 

    const UIREVISION_VALUE = "keep"

    const [graphLayout, setGraphLayout] = useState({
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
        shapes: [
            {
                type: 'line',
                x0: '',
                x1: '',
                y0: 0,
                y1: 1,
                xref: 'x',
                yref: 'paper',
                line: {
                    color: 'red',
                    width: 2,
                    dash: 'dashdot'
                }
            },
        ],
        annotations: [] 
    })

    // const formatTime = (timeInSeconds) => {
    //     const ms = Math.floor(timeInSeconds * 1000)
    //     const hours = Math.floor(ms / 3600000)
    //     const minutes = Math.floor((ms % 3600000) / 60000)
    //     const seconds = Math.floor((ms % 60000) / 1000)
    //     const milliseconds = ms % 1000
    //     const formatUnit = (unit) => String(unit).padStart(2, '0')
    //     return `${formatUnit(hours)}:${formatUnit(minutes)}:${formatUnit(seconds)}:${String(milliseconds).padStart(3, '0')}`
    // };
    
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

    const run = useFilteredData ? selectedRun.filteredRunData : selectedRun

    const plotData = useMemo(() => {
        if (!run || !run.data || run.data.length === 0) return []

        const sensorTraces = []

        const processSensor = (sensorId, sensorName) => {
            const sensor = run.data.find(d => d._id === sensorId);
            if (!sensor || !sensor.readings) return;

            const readings = sensor.readings;
            const timestamps = run.totalTimestamps.map(t => formatTime(t));

            const xValues = readings.map(r => r.data[0]);
            const yValues = readings.map(r => r.data[1]);
            const zValues = readings.map(r => r.data[2]);

            sensorTraces.push(
            { 
                x: timestamps, 
                y: xValues, 
                type: 'scattergl',
                mode: 'lines', 
                name: `${sensorName} X-axis`, 
                visible: 'legendonly', 
                yaxis: 'y',
                line: { width: 3 }
            },
            { 
                x: timestamps, 
                y: yValues, 
                type: 'scattergl', 
                mode: 'lines', 
                name: `${sensorName} Y-axis`, 
                visible: 'legendonly', 
                yaxis: 'y',
                line: { width: 3 }
            },
            { 
                x: timestamps, 
                y: zValues, 
                type: 'scattergl', 
                mode: 'lines', 
                name: `${sensorName} Z-axis`, 
                visible: 'legendonly', 
                yaxis: 'y',
                line: { width: 3 }
            }
            )
        }
        
        processSensor("accelerometer", "Accelerometer")
        processSensor("magnetometer", "Magnetometer")
        processSensor("gyroscope", "Gyroscope")
        processSensor("fault", "Fault")
        processSensor("faultGyro", "Fault Gyroscope")
        
        return sensorTraces
    }, [run])

    useEffect(() => {
        const updateGraphLayout = async () => {
            if (run && run.data && plotData.length > 0) {
                const sensorList = [
                    { id: "accelerometer", label: "Accelerometer", color: "red" },
                    { id: "magnetometer", label: "Magnetometer", color: "blue" },
                    { id: "gyroscope", label: "Gyroscope", color: "green" },
                    { id: "fault", label: "Fault", color: "orange" }
                ];

                const newShapes = [];
                const newAnnotations = [];

                sensorList.forEach(sensorInfo => {
                    const sensor = run.data.find(d => d._id === sensorInfo.id);
                    if (sensor && sensor.readings && sensor.readings.length > sliderValue) {
                        const tracesForSensor = plotData.filter(trace =>
                            trace.name && trace.name.includes(sensorInfo.label)
                        );
                        const isVisible = tracesForSensor.some(trace => trace.visible !== 'legendonly');

                        if (isVisible) {
                            const reading = sensor.readings[sliderValue];
                            const ts = formatTime(reading.timestamp);

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

                            newAnnotations.push({
                                x: ts,
                                y: 1,
                                xref: 'x',
                                yref: 'paper',
                                yanchor: 'bottom',
                                align: 'left',
                                text: `${sensorInfo.label} - Time: ${ts} X: ${reading.data[0]} Y: ${reading.data[1]} Z: ${reading.data[2]}`,
                                bordercolor: "black",
                                borderwidth: 1,
                                borderpad: 4,
                                bgcolor: 'white',
                                showarrow: false,
                                xanchor: 'left'
                            });
                        }
                    }
                });

                setGraphLayout(prev => ({
                    ...prev,
                    shapes: newShapes,
                    annotations: newAnnotations
                }));
            }
        };

        updateGraphLayout();
    }, [sliderValue, run, plotData]);

    // LUGE HIGHLIGHTS
    useEffect(() => {
        console.log('🚀 LUGE HIGHLIGHTS useEffect triggered');
        console.log('📊 Dependencies:', { run: !!run, sliderValue });
        
        const updateHighlightSections = () => {
            console.log('🔄 updateHighlightSections called');
            
            if (!run) {
                console.log('❌ No run data available');
                return;
            }
            
            if (!run.data) {
                console.log('❌ run.data is not available');
                console.log('🔍 Run structure:', Object.keys(run));
                return;
            }
            
            if (!run.data.length) {
                console.log('❌ run.data is empty');
                return;
            }
            
            console.log('✅ Run data available, length:', run.data.length);
            console.log('🔍 Run data structure:', run.data.map(d => ({ id: d._id, sensorId: d.sensorId, hasReadings: !!d.readings, hasData: !!d.data })));
            
            // Try both possible data structures
            let accelerometer = run.data.find(d => d.sensorId === 1);
            if (!accelerometer) {
                accelerometer = run.data.find(d => d._id === "accelerometer");
            }
            
            console.log('🎯 Accelerometer found:', !!accelerometer);
            
            if (!accelerometer) {
                console.log('❌ No accelerometer data found');
                return;
            }
            
            console.log('📋 Accelerometer structure:', Object.keys(accelerometer));
            
            // Check which data property exists
            const sensorData = accelerometer.readings || accelerometer.data;
            if (!sensorData) {
                console.log('❌ No sensor data found in accelerometer (neither readings nor data)');
                return;
            }
            
            console.log('✅ Sensor data found, length:', sensorData.length);
            console.log('📊 First few data points:', sensorData.slice(0, 3));
            
            const highlightSections = [];
            let isInSection = false;
            let sectionStart = null;
            let sectionEnd = null;
            let sectionsFound = 0;

            sensorData.forEach((reading, idx) => {
                const zValue = reading.data[2];
                
                if (idx < 5) { // Log first few iterations for debugging
                    console.log(`📊 Reading ${idx}: z=${zValue}`);
                }

                if (zValue > 1.25 && !isInSection) {
                    isInSection = true;
                    sectionStart = idx;
                    console.log(`🟢 Section start at index ${idx}, z=${zValue}`);
                } else if (zValue < 1 && isInSection) {
                    isInSection = false;
                    sectionEnd = idx;
                    sectionsFound++;
                    console.log(`🔴 Section end at index ${idx}, z=${zValue}`);

                    if (sectionStart !== null && sectionEnd !== null) {
                        const yValues = sensorData
                            .slice(sectionStart, sectionEnd + 1)
                            .map(r => r.data[1]);

                        console.log(`📈 Y values for section ${sectionsFound}:`, yValues.slice(0, 5), '...', yValues.length, 'total');

                        // Find the first local extreme in Y values
                        let firstExtreme = null;
                        for (let i = 1; i < yValues.length - 1; i++) {
                            if ((yValues[i] > yValues[i - 1] && yValues[i] > yValues[i + 1]) ||
                                (yValues[i] < yValues[i - 1] && yValues[i] < yValues[i + 1])) {
                                firstExtreme = yValues[i];
                                console.log(`🎯 First extreme found: ${firstExtreme} at position ${i}`);
                                break;
                            }
                        }

                        // Determine the color based on the sign of the first extreme
                        const color = firstExtreme > 0
                            ? 'rgba(0, 255, 0, 0.54)' // Positive extreme, green
                            : 'rgba(255, 0, 0, 0.54)'; // Negative extreme, red

                        console.log(`🎨 Section color: ${color} (extreme: ${firstExtreme})`);

                        highlightSections.push({
                            x0: formatTime(sensorData[sectionStart].timestamp),
                            x1: formatTime(sensorData[sectionEnd].timestamp),
                            color
                        });
                    }
                }
            });

            console.log(`🏁 Total sections found: ${sectionsFound}`);
            console.log(`📋 Highlight sections:`, highlightSections);

            const sectionShapes = highlightSections.map(({ x0, x1, color }) => ({
                type: 'rect',
                x0,
                x1,
                y0: 0,
                y1: 1,
                xref: 'x',
                yref: 'paper',
                fillcolor: color,
                opacity: 0.2,
                line: {
                    width: 0
                }
            }));

            console.log(`🎨 Created ${sectionShapes.length} shapes`);

            setGraphLayout(prev => {
                const newShapes = [
                    ...prev.shapes.filter(shape => shape.type !== 'rect'), // Preserve non-rect shapes (e.g., lines)
                    ...sectionShapes
                ];
                console.log(`📊 Updating graph layout with ${newShapes.length} total shapes`);
                return {
                    ...prev,
                    shapes: newShapes
                };
            });
        };

        updateHighlightSections();
    }, [run, sliderValue]);

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
            <button 
                onClick={() => setUseFilteredData(prev => !prev)}
                style={{ padding: '10px 20px', fontSize: '16px' }}
            >
                Data filter {useFilteredData ? '(On)' : '(Off)'}
            </button>
            {run && (
                <Plot
                    data={plotData}
                    layout={graphLayout}
                    style={{ width: '100%', height: '100%' }}
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
                                click: (gd) => {
                                    removeFunction();
                                }
                            }
                        ]
                    }}
                />
            )}
        </>
    )
}

export default PlotlyGraphVisualizer