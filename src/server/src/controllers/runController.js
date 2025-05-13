const KalmanFilter = require("kalmanjs");
const runService = require("../services/runService");
const sensorService = require("../services/sensorService");
const { toRadians } = require("../utils/units");

const sensitivity = 19.5;

const convertToG = (raw_reading, sensitivity) => {
  return (raw_reading * sensitivity) / 1000000.0;
};

const convertSensorData = (sensorData, conversionFunction) => {
  sensorData.forEach((sensorData) => {
    if (sensorData.readings) {
      sensorData.readings.forEach((reading) => {
        if (reading.data && Array.isArray(reading.data)) {
          reading.data = reading.data.map((rawReading) => {
            return conversionFunction(rawReading, sensitivity);
          });

          //FIXME
          reading.data[2] = reading.data[2] * -1;
        }
      });
    }
  });
  return sensorData;
};

const getAllRuns = async () => {
  try {
    const runs = await runService.getAllRuns();
    runs.forEach((run) => {
      if (run.date) {
        run.date = run.date.toGMTString();
      } else {
      }
    });
    return runs;
  } catch (error) {
    throw new Error(error.message);
  }
};

const getSingleRun = async (runid) => {
  try {
    const run = await runService.getSingleRun(runid);

    convertSensorData(run.data, convertToG);

    return run;
  } catch (error) {
    throw new Error(error.message);
  }
};

const getSingleRunKalmanFilter = async (runid) => {
  try {
    const run = await runService.getSingleRun(runid);

    if (!run || !run.data || !run.data[0]?.readings) {
      throw new Error("Invalid run data structure");
    }

    convertSensorData(run.data, convertToG);

    // Apply Kalman filter to accelerometer data

    run.data.forEach((sensorData) => {
      if (sensorData._id === "accelerometer" && sensorData.readings) {
        const kfX = new KalmanFilter({ R: 0.01, Q: 1 });
        const kfY = new KalmanFilter({ R: 0.01, Q: 1 });
        const kfZ = new KalmanFilter({ R: 0.01, Q: 1 });

        // const kfX = new KalmanFilter({ R: 0.0001, Q: 1 });
        // const kfY = new KalmanFilter({ R: 0.0001, Q: 1 });
        // const kfZ = new KalmanFilter({ R: 0.0001, Q: 1 });

        sensorData.readings.forEach((reading) => {
          if (reading.data && Array.isArray(reading.data)) {
            // Apply Kalman filter
            let filteredX = kfX.filter(reading.data[0]);
            let filteredY = kfY.filter(reading.data[1]);
            let filteredZ = kfZ.filter(reading.data[2]);

            // Update reading data with filtered values
            reading.data[0] = filteredX;
            reading.data[1] = filteredY;
            reading.data[2] = filteredZ;
          }
        });
      }
    });

    return run;
  } catch (error) {
    throw new Error(error.message);
  }
};

const movingAverage = (data, windowSize) => {
  return data.map((_, i, arr) => {
    const start = Math.max(i - windowSize + 1, 0);
    const subset = arr.slice(start, i + 1);
    const avg = subset.reduce((a, b) => a + b, 0) / subset.length;
    return avg;
  });
};

const getSingleRunMovingAverage = async (runid) => {
  try {
    const run = await runService.getSingleRun(runid);

    if (!run || !run.data || !run.data[0]?.readings) {
      throw new Error("Invalid run data structure");
    }

    convertSensorData(run.data, convertToG);

    // Apply moving average to accelerometer data
    run.data.forEach((sensorData) => {
      if (sensorData._id === "accelerometer" && sensorData.readings) {
        const windowSize = 40; // adjust this value if needed

        // Extract axis time series arrays
        const xValues = sensorData.readings.map((r) => r.data[0]);
        const yValues = sensorData.readings.map((r) => r.data[1]);
        const zValues = sensorData.readings.map((r) => r.data[2]);

        // Calculate moving averages for each axis
        const smoothX = movingAverage(xValues, windowSize);
        const smoothY = movingAverage(yValues, windowSize);
        const smoothZ = movingAverage(zValues, windowSize);

        // Update each reading with the smoothed values
        sensorData.readings.forEach((reading, idx) => {
          if (reading.data && Array.isArray(reading.data)) {
            reading.data[0] = smoothX[idx];
            reading.data[1] = smoothY[idx];
            reading.data[2] = smoothZ[idx];
          }
        });
      }
    });

    return run;
  } catch (error) {
    throw new Error(error.message);
  }
};

const filterRunsByDate = async (dateFrom, dateTo) => {
  try {
    if (dateTo === undefined || dateTo === "") {
      dateTo = new Date();
    }
    if (dateFrom === undefined || dateFrom === "") {
      dateFrom = new Date(0);
    }
    var includeDateTo = new Date(dateTo);
    includeDateTo.setDate(includeDateTo.getDate() + 1);
    const runs = await runService.filterRunsByDate(dateFrom, includeDateTo);
    runs.forEach((run) => {
      run.date = run.date.toGMTString();
    });
    return runs;
  } catch (error) {
    throw new Error(error.message);
  }
};

const createRun = async (run) => {
  try {
    const newRun = await runService.createRun(run);
    return newRun;
  } catch (error) {
    throw new Error(error.message);
  }
};

module.exports = {
  getAllRuns,
  getSingleRun,
  filterRunsByDate,
  createRun,
  getSingleRunKalmanFilter,
  getSingleRunMovingAverage,
};
