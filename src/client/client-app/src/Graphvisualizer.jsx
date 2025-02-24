import React, { useEffect, useRef } from 'react';
import './Graphvisualizer.css';

const GraphVisualizer = ({ selectedRun, sliderValue }) => {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!selectedRun) return;

    const chartData = {
      labels: [],
      datasets: []
    };

    function convertNanosecondsToTime(nanoseconds) {
      const msInNano = 1e6;
      const ms = Math.floor(nanoseconds / msInNano);

      const hours = Math.floor(ms / 3600000);
      const minutes = Math.floor((ms % 3600000) / 60000);
      const seconds = Math.floor((ms % 60000) / 1000);
      const milliseconds = ms % 1000;

      const formatTime = (unit) => String(unit).padStart(2, '0');
      return `${formatTime(hours)}:${formatTime(minutes)}:${formatTime(seconds)}:${String(milliseconds).padStart(3, '0')}`;
    }

    const ChartColors = {
      red: 'rgb(255, 99, 132)',
      orange: 'rgb(255, 159, 64)',
      yellow: 'rgb(255, 205, 86)',
      green: 'rgb(75, 192, 192)',
      blue: 'rgb(54, 162, 235)',
      purple: 'rgb(153, 102, 255)',
      black: 'rgb(0, 0, 0)',
      pink: 'rgb(255, 105, 180)',
      brown: 'rgb(165, 42, 42)',
      cyan: 'rgb(0, 255, 255)',
      magenta: 'rgb(255, 0, 255)',
      lime: 'rgb(0, 255, 0)',
      navy: 'rgb(0, 0, 128)',
      teal: 'rgb(0, 128, 128)',
      olive: 'rgb(128, 128, 0)',
      maroon: 'rgb(128, 0, 0)',
      coral: 'rgb(255, 127, 80)',
      gold: 'rgb(255, 215, 0)',
      lavender: 'rgb(230, 230, 250)',
      indigo: 'rgb(75, 0, 130)'
    };

    let colorCounter = 0;

    selectedRun.data.forEach(sensors => {
      if (colorCounter > Object.values(ChartColors).length - 1) {
        colorCounter = 0;
      }

      let sensorsId1 = sensors._id + 'X';
      let sensorsId2 = sensors._id + 'Y';
      let sensorsId3 = sensors._id + 'Z';

      var dataArrayX = [];
      var dataArrayY = [];
      var dataArrayZ = [];

      chartData.labels = sensors.readings.map(item => convertNanosecondsToTime(item.timestamp).toString());

      sensors.readings.forEach((item, index) => {
        dataArrayX.push(item.data[0]);
        dataArrayY.push(item.data[1]);
        dataArrayZ.push(item.data[2]);
      });

      if (dataArrayX.length > 0) {
        chartData.datasets.push({
          label: sensorsId1,
          data: dataArrayX,
          borderColor: Object.values(ChartColors)[colorCounter],
          fill: false,
          hidden: true,
          pointRadius: window.pointRadius,
          pointBackgroundColor: Object.values(ChartColors)[colorCounter]
        });

        colorCounter++;
      }
      if (dataArrayY.length > 0) {
        chartData.datasets.push({
          label: sensorsId2,
          data: dataArrayY,
          borderColor: Object.values(ChartColors)[colorCounter],
          fill: false,
          hidden: true,
          pointRadius: window.pointRadius,
          pointBackgroundColor: Object.values(ChartColors)[colorCounter]
        });

        colorCounter++;
      }
      if (dataArrayZ.length > 0) {
        chartData.datasets.push({
          label: sensorsId3,
          data: dataArrayZ,
          borderColor: Object.values(ChartColors)[colorCounter],
          fill: false,
          hidden: true,
          pointRadius: window.pointRadius,
          pointBackgroundColor: Object.values(ChartColors)[colorCounter]
        });

        colorCounter++;
      }
    });

    const imuData = chartData;

    const initalChartRadius = 2;

    window.initalChartRadius = initalChartRadius;

    window.pointRadius = imuData.labels.map(() => window.initalChartRadius);
    window.pointBackgroundColor = imuData.labels.map(() => 'rgb(255, 99, 132)');

    chartData.datasets.forEach((dataset, index) => {
      dataset.pointRadius = window.pointRadius;
    });

    const ctx = canvasRef.current.getContext('2d');

    if (chartRef.current) {
      chartRef.current.destroy();
    }

    const imuChart = new Chart(ctx, {
      type: 'line',
      data: chartData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 0
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'Time'
            }
          },
          y: {
            ticks: {
              callback: function (value, index, values) {
                return value.toFixed(2);
              }
            },
            title: {
              display: true,
              text: 'Value'
            }
          }
        },
        plugins: {
          zoom: {                     
            zoom: {
                wheel: {
                    enabled: true,
                },
                pinch: {
                    enabled: true
                },
                mode: 'x',
            },
            pan: {
              enabled: true,
            },
          },
          legend: {
            display: true,
            position: 'right',
            labels: {
              usePointStyle: true,
              pointStyle: 'circle',
              boxWidth: 20,
              padding: 10
            },
            onClick: function (e, legendItem) {
              const index = legendItem.datasetIndex;
              const ci = this.chart;
              const meta = ci.getDatasetMeta(index);

              meta.hidden = meta.hidden === null ? !ci.data.datasets[index].hidden : null;

              ci.update();

              // Recalculate min and max values based on visible datasets
              let minValue = Number.POSITIVE_INFINITY;
              let maxValue = Number.NEGATIVE_INFINITY;

              ci.data.datasets.forEach(dataset => {
                if (!ci.isDatasetVisible(dataset.index)) return;

                dataset.data.forEach(value => {
                  if (value < minValue) minValue = value;
                  if (value > maxValue) maxValue = value;
                });
              });

              console.log(minValue, maxValue);

              if(minValue !== Number.POSITIVE_INFINITY && maxValue !== Number.NEGATIVE_INFINITY) {
                ci.options.scales.y.min = minValue;
                ci.options.scales.y.max = maxValue;
              }

              ci.update();
            }
          },
          annotation: {
            annotations: {
              verticalLine: {
                type: 'line',
                xMin: 0,
                xMax: 0,
                borderColor: 'red',
                borderWidth: 2,
                label: {
                  enabled: true,
                  position: 'top'
                }
              }
            }
          }
        }
      }
    });

    chartRef.current = imuChart;

  }, [selectedRun]);

  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.options.plugins.annotation.annotations.verticalLine.xMin = Number(sliderValue);
      chartRef.current.options.plugins.annotation.annotations.verticalLine.xMax = Number(sliderValue);
      chartRef.current.update();
    }
  }, [sliderValue]);

  const handleResetZoom = () => {
    if (chartRef.current) {
      chartRef.current.resetZoom();
    }
  };

  return (
    <>
      <h1>Graph Visualizer</h1>
      <button onClick={handleResetZoom}>Reset Zoom</button>
      <div className="graph-container">
        <canvas ref={canvasRef}></canvas>
      </div>
    </>
  );
};

export default GraphVisualizer;