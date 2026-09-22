import React, { useEffect, useRef } from 'react';
import { debounce } from 'lodash';
import './Graphvisualizer.css';

const GraphVisualizer = ({ selectedRun, sliderValue }) => {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  // Downsampling function
  const downsample = (data, threshold) => {
    if (data.length <= threshold) return data;

    const sampled = [];
    const step = Math.ceil(data.length / threshold);

    for (let i = 0; i < data.length; i += step) {
      sampled.push(data[i]);
    }

    return sampled;
  };

  useEffect(() => {
    if (!selectedRun) return;

    const chartData = {
      labels: [],
      datasets: []
    };

    const formatTime = (timeInSeconds) => {
      const ms = Math.floor(timeInSeconds * 1000);
      const hours = Math.floor(ms / 3600000);
      const minutes = Math.floor((ms % 3600000) / 60000);
      const seconds = Math.floor((ms % 60000) / 1000);
      const milliseconds = ms % 1000;

      const formatUnit = (unit) => String(unit).padStart(2, '0');
      return `${formatUnit(hours)}:${formatUnit(minutes)}:${formatUnit(seconds)}:${String(milliseconds).padStart(3, '0')}`;
    };

    const ChartColors = {
      blue:        'rgb(33, 150, 243)',
      deepOrange:  'rgb(255, 87, 34)',
      green:       'rgb(76, 175, 80)',
      pink:        'rgb(233, 30, 99)',
      amber:       'rgb(255, 152, 0)',
      purple:      'rgb(156, 39, 176)',
      cyan:        'rgb(0, 188, 212)',
      red:         'rgb(244, 67, 54)',
      teal:        'rgb(0, 150, 136)',
      yellow:      'rgb(255, 193, 7)',
      indigo:      'rgb(63, 81, 181)',
      limeGreen:   'rgb(139, 195, 74)',
      hotPink:     'rgb(255, 64, 129)',
      darkCyan:    'rgb(0, 172, 193)',
      darkPurple:  'rgb(123, 31, 162)',
      orangeAccent:'rgb(255, 109, 0)',
      coral:       'rgb(255, 112, 67)',
      mint:        'rgb(29, 233, 182)',
      violet:      'rgb(124, 77, 255)',
      rose:        'rgb(240, 98, 146)',
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

      chartData.labels = sensors.readings.map(item => formatTime(item.timestamp));

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

              let minValue = Number.POSITIVE_INFINITY;
              let maxValue = Number.NEGATIVE_INFINITY;

              ci.data.datasets.forEach(dataset => {
                if (!ci.isDatasetVisible(dataset.index)) return;

                dataset.data.forEach(value => {
                  if (value < minValue) minValue = value;
                  if (value > maxValue) maxValue = value;
                });
              });

              if (minValue !== Number.POSITIVE_INFINITY && maxValue !== Number.NEGATIVE_INFINITY) {
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
      const updateChart = () => {
        chartRef.current.options.plugins.annotation.annotations.verticalLine.xMin = Number(sliderValue);
        chartRef.current.options.plugins.annotation.annotations.verticalLine.xMax = Number(sliderValue);
        chartRef.current.update();
      };

      requestAnimationFrame(updateChart);
    }
  }, [sliderValue]);

  const handleResetZoom = debounce(() => {
    if (chartRef.current) {
      chartRef.current.resetZoom();
    }
  }, 300);

  return (
    <>
      <button className="btn-reset-zoom" onClick={handleResetZoom}>Reset Zoom</button>
      <div className="graph-container">
        <canvas ref={canvasRef}></canvas>
      </div>
    </>
  );
};

export default GraphVisualizer;
