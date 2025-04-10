import { useState, useEffect, useMemo } from 'react'
import Plot from 'react-plotly.js'

const PlotlyGraphVisualizer = ({ selectedRun, sliderValue, removeFunction }) => {
    const [useFilteredData, setUseFilteredData] = useState(false) 

    const UIREVISION_VALUE = "keep"

    const [graphLayout, setGraphLayout] = useState({
        autosize: true,
        dragmode: 'pan',
        margin: { l: 0, r: 10, t: 30, b: 0 },
        xaxis: { title: 'Timestamp', showticklabels: false },
        yaxis: { title: 'Sensor Reading' },
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
          }
        ],
        annotations: [] 
    })

    const formatTime = (timeInSeconds) => {
        const ms = Math.floor(timeInSeconds * 1000)
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
        const accelerometer = run.data.find(d => d._id === "accelerometer")
        if (!accelerometer || !accelerometer.readings) return []
        const readings = accelerometer.readings
        const timestamps = readings.map(r => formatTime(r.timestamp))
        const xValues = readings.map(r => r.data[0])
        const yValues = readings.map(r => r.data[1])
        const zValues = readings.map(r => r.data[2])

        return [
            { x: timestamps, y: xValues, type: 'scattergl', mode: 'lines+markers', name: 'X-axis' },
            { x: timestamps, y: yValues, type: 'scattergl', mode: 'lines+markers', name: 'Y-axis' },
            { x: timestamps, y: zValues, type: 'scattergl', mode: 'lines+markers', name: 'Z-axis' }
        ]
    }, [run])

    useEffect(() => {
        if (run && run.data && run.data.length > 0) {
            const accelerometer = run.data.find(d => d._id === "accelerometer")
            if (accelerometer && accelerometer.readings && accelerometer.readings.length > sliderValue) {
                const reading = accelerometer.readings[sliderValue]
                const ts = formatTime(reading.timestamp)
                setGraphLayout(prev => ({
                    ...prev,
                    shapes: [
                        {
                            ...prev.shapes[0],
                            x0: ts,
                            x1: ts
                        }
                    ],
                    annotations: [
                        {
                            x: ts,
                            y: 1,               
                            xref: 'x',
                            yref: 'paper',      
                            yanchor: 'bottom', 
                            align: 'left',
                            text: `Time: ${ts} X: ${reading.data[0]} Y: ${reading.data[1]} Z: ${reading.data[2]}`,
                            bordercolor: "black",
                            borderwidth: 1,
                            borderpad: 4,
                            bgcolor: 'white',
                            showarrow: false,
                            xanchor: 'left'
                        }
                    ]
                }))
            }
        }
    }, [sliderValue, run])

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