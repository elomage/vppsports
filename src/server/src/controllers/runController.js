const KalmanFilter = require("kalmanjs");
const runService = require("../services/runService");
const sensorService = require("../services/sensorService");
const { toRadians } = require("../utils/units");
const savitzkyGolay = require("ml-savitzky-golay").default;

const sensitivity = 19.5;

const ensureRunName = (run) => {
  if (!run) return run;
  const fallbackId = run._id ? String(run._id) : "Unknown";
  run.name =
    run.name && String(run.name).trim()
      ? String(run.name).trim()
      : `Run ${fallbackId}`;
  return run;
};

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
    // const runs = await runService.getAllRuns();
    const runs = await runService.getAllRunsDB();
    runs.forEach((run) => {
      ensureRunName(run);
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
    // const run = await runService.getSingleRunDB(runid);

    convertSensorData(run.data, convertToG);

    const accelerometerData = run.data.find((d) => d._id === "accelerometer");
    const gyroscopeData = run.data.find((d) => d._id === "gyroscope");
    const magnetometerData = run.data.find((d) => d._id === "magnetometer");

    totalTimestamps = [];

    if (accelerometerData) {
      accelerometerData.readings.forEach((r) =>
        totalTimestamps.push(r.timestamp)
      );
    }
    if (gyroscopeData) {
      gyroscopeData.readings.forEach((r) => totalTimestamps.push(r.timestamp));
    }
    if (magnetometerData) {
      magnetometerData.readings.forEach((r) =>
        totalTimestamps.push(r.timestamp)
      );
    }

    run.totalTimestamps = new Set(totalTimestamps);

    if (
      accelerometerData &&
      accelerometerData.readings &&
      gyroscopeData &&
      gyroscopeData.readings &&
      magnetometerData &&
      magnetometerData.readings
    ) {
      calculateOrientationData(run);
    }

    return run;
  } catch (error) {
    throw new Error(error.message);
  }
};

const getSingleRunDB = async (runid) => {
  try {
    let run = await runService.getSingleRunDB(runid);
    run = ensureRunName(run);

    const sensorData = await runService.getRunSensorReadingsAll(runid);

    // run.orientationData = [];

    // run.totalTimestamps = [];

    // var pitch = 0;
    // var roll = 0;
    // var yaw = 0;

    // const gyroItem = sensorData.find((item) => item._id === "gyroscope");
    // if (gyroItem && gyroItem.readings && gyroItem.readings.length > 0) {
    //   gyroItem.readings.forEach((element) => {
    //     pitch += element.data[1] / 6;
    //     roll += element.data[0] / 6;
    //     yaw += element.data[2] / 6;

    //     run.orientationData.push([element.timestamp, roll, yaw, pitch]);
    //   });
    // }

    // const orientationData = await runService.getRunOrientationData(runid, 1);

    // const orientationData = await getRunSensorOrientationData(runid, 1, 2, 3);
    const orientationData = [];

    const totalTimestamps = await runService.getTotalTimestamps(runid);

    // run.totalTimestamps = totalTimestamps;

    // run.totalTimestamps.push(
    //   ...sensorData
    //     // .find((item) => item._id === "accelerometer")
    //     .find((item) => item.sensorId === 3)
    //     .readings.map((r) => r.timestamp)
    // );

    // run.totalTimestamps.push(
    //   ...sensorData
    //     // .find((item) => item._id === "gyroscope")
    //     .find((item) => item.sensorId === 2)
    //     .readings.map((r) => r.timestamp)
    // );
    // run.totalTimestamps.push(
    //   ...sensorData
    //     // .find((item) => item._id === "magnetometer")
    //     .find((item) => item.sensorId === 1)
    //     .readings.map((r) => r.timestamp)
    // )

    const runObject =
      run && typeof run.toObject === "function" ? run.toObject() : run;

    const response = {
      ...runObject,
      data: sensorData,
      orientationData: orientationData,
      totalTimestamps: totalTimestamps,
    };

    return response;
  } catch (error) {
    throw new Error(error.message);
  }
};

// const downsampleToMatch = (highRateData, lowRateTimestamps) => {
//   const downsampledData = [];

//   lowRateTimestamps.forEach((timestamp) => {
//     // Find the closest high-rate data point to the current low-rate timestamp
//     let closest = highRateData.reduce((prev, curr) => {
//       return Math.abs(curr.timestamp - timestamp) <
//         Math.abs(prev.timestamp - timestamp)
//         ? curr
//         : prev;
//     });

//     downsampledData.push(closest);
//   });

//   return downsampledData;
// };
const downsampleToMatch = (highRateData, lowRateTimestamps) => {
  if (
    !Array.isArray(highRateData) ||
    !Array.isArray(lowRateTimestamps) ||
    highRateData.length === 0 ||
    lowRateTimestamps.length === 0
  ) {
    return [];
  }

  // Sort high-rate data once (shallow copy to avoid mutating input)
  const sortedHigh = highRateData
    .slice()
    .sort((a, b) => a.timestamp - b.timestamp);
  const highTs = sortedHigh.map((r) => r.timestamp);

  const findClosestIndex = (ts) => {
    // lower_bound search
    let lo = 0,
      hi = highTs.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (highTs[mid] < ts) lo = mid + 1;
      else hi = mid;
    }
    if (lo === 0) return 0;
    if (lo === highTs.length) return highTs.length - 1;
    return ts - highTs[lo - 1] <= highTs[lo] - ts ? lo - 1 : lo;
  };

  const result = new Array(lowRateTimestamps.length);
  for (let i = 0; i < lowRateTimestamps.length; i++) {
    const idx = findClosestIndex(lowRateTimestamps[i]);
    result[i] = sortedHigh[idx];
  }
  return result;
};

const calculateOrientationData = async (sensorData) => {
  try {
    sensorData.orientationData = [];

    const accelerometerData = sensorData.data.find(
      (d) => d._id === "accelerometer"
    ).readings;
    const gyroscopeData = sensorData.data.find(
      (d) => d._id === "gyroscope"
    ).readings;
    const magnetometerData = sensorData.data.find(
      (d) => d._id === "magnetometer"
    ).readings;

    if (!accelerometerData || !gyroscopeData || !magnetometerData) {
      throw new Error("Missing sensor data for orientation calculation");
    }

    // Extract timestamps from magnetometer data
    const magnetometerTimestamps = magnetometerData.map(
      (reading) => reading.timestamp
    );

    // Downsample accelerometer and gyroscope data to match magnetometer timestamps
    const downsampledAccelerometer = downsampleToMatch(
      accelerometerData,
      magnetometerTimestamps
    );
    const downsampledGyroscope = downsampleToMatch(
      gyroscopeData,
      magnetometerTimestamps
    );

    // Calculate orientation using downsampled data
    downsampledAccelerometer.forEach((accel, index) => {
      const gyro = downsampledGyroscope[index];
      const mag = magnetometerData[index];

      const deltaTime = 0.01; // Example deltaTime, replace with actual calculation if available

      const orientation = calculateOrientation(
        { x: accel.data[0], y: accel.data[1], z: accel.data[2] },
        { x: gyro.data[0], y: gyro.data[1], z: gyro.data[2] },
        { x: mag.data[0], y: mag.data[1], z: mag.data[2] },
        deltaTime
      );

      sensorData.orientationData.push({
        timestamp: magnetometerTimestamps[index],
        ...orientation,
      });
    });

    return sensorData;
  } catch (err) {
    throw new Error(err.message);
  }
};

const calculateOrientation = (
  accelerometer,
  gyroscope,
  magnetometer,
  deltaTime
) => {
  let pitch, roll, yaw;

  // Normalize accelerometer data (in G)
  const accNorm = Math.sqrt(
    accelerometer.x ** 2 + accelerometer.y ** 2 + accelerometer.z ** 2
  );
  const ax = accelerometer.x / accNorm;
  const ay = accelerometer.y / accNorm;
  const az = accelerometer.z / accNorm;

  // Calculate pitch and roll from accelerometer
  // pitch = Math.atan2(-ax, Math.sqrt(ay ** 2 + az ** 2));

  pitch = Math.atan2(-ax, Math.sqrt(ay ** 2 + az ** 2));

  // pitch = Math.atan2(ay, az) + Math.PI;

  roll = Math.atan2(ay, az);

  // roll = Math.atan2(ax, az) + Math.PI;
  // roll = Math.atan2(ax, az) + Math.PI;

  // Normalize magnetometer data (in T)
  const magNorm = Math.sqrt(
    magnetometer.x ** 2 + magnetometer.y ** 2 + magnetometer.z ** 2
  );
  const mx = magnetometer.x / magNorm;
  const my = magnetometer.y / magNorm;
  const mz = magnetometer.z / magNorm;

  // Adjust magnetometer readings for pitch and roll
  const magX = mx * Math.cos(pitch) + mz * Math.sin(pitch);
  const magY =
    mx * Math.sin(roll) * Math.sin(pitch) +
    my * Math.cos(roll) -
    mz * Math.sin(roll) * Math.cos(pitch);

  // Calculate yaw from magnetometer
  const magYaw = Math.atan2(-magY, magX);

  // Convert gyroscope data (in degrees/s) to radians/s
  const gx = (gyroscope.x * Math.PI) / 180;
  const gy = (gyroscope.y * Math.PI) / 180;
  const gz = (gyroscope.z * Math.PI) / 180;

  // Integrate gyroscope data for yaw
  yaw = magYaw + gz * deltaTime;

  // Use complementary filter to combine gyroscope and magnetometer yaw
  const alpha = 0.98; // Complementary filter coefficient
  yaw = alpha * yaw + (1 - alpha) * magYaw;

  return { pitch, roll, yaw };
};

const getSingleRunKalmanFilter = async (runid) => {
  try {
    const run = await runService.getSingleRun(runid);

    if (!run || !run.data || !run.data[0]?.readings) {
      throw new Error("Invalid run data structure");
    }

    convertSensorData(run.data, convertToG);

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
    // const run = await runService.getSingleRun(runid);

    const run = await runService.getSingleRunDB(runid);
    const sensorData = await runService.getRunSensorReadings(runid);
    run.orientationData = [];

    run.totalTimestamps = [];

    var pitch = 0;
    var roll = 0;
    var yaw = 0;

    sensorData
      .find((item) => item._id === "gyroscope")
      .readings.forEach((element) => {
        pitch += element.data[1] / 6;
        roll += element.data[0] / 6;
        yaw += element.data[2] / 6;

        run.orientationData.push([element.timestamp, roll, yaw, pitch]);
      });
    run.data = sensorData;

    run.totalTimestamps.push(
      ...sensorData
        .find((item) => item._id === "accelerometer")
        .readings.map((r) => r.timestamp)
    );

    run.totalTimestamps.push(
      ...sensorData
        .find((item) => item._id === "gyroscope")
        .readings.map((r) => r.timestamp)
    );
    run.totalTimestamps.push(
      ...sensorData
        .find((item) => item._id === "magnetometer")
        .readings.map((r) => r.timestamp)
    );

    if (!run || !run.data || !run.data[0]?.readings) {
      throw new Error("Invalid run data structure");
    }

    // convertSensorData(run.data, convertToG);

    // Apply moving average to accelerometer data
    run.data.forEach((sensorData) => {
      if (
        [
          "accelerometer",
          "gyroscope",
          "magnetometer",
          // "fault",
          // "faultGyro",
        ].includes(sensorData._id) &&
        sensorData.readings
      ) {
        // const windowSize = 20; // adjust this value if needed
        const windowSize = 200; // adjust this value if needed

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

    const accelerometerData = run.data.find((d) => d._id === "accelerometer");
    const gyroscopeData = run.data.find((d) => d._id === "gyroscope");
    const magnetometerData = run.data.find((d) => d._id === "magnetometer");

    run.totalTimestamps = [];
    if (accelerometerData) {
      accelerometerData.readings.forEach((r) =>
        run.totalTimestamps.push(r.timestamp)
      );
    }
    if (gyroscopeData) {
      gyroscopeData.readings.forEach((r) =>
        run.totalTimestamps.push(r.timestamp)
      );
    }
    if (magnetometerData) {
      magnetometerData.readings.forEach((r) =>
        run.totalTimestamps.push(r.timestamp)
      );
    }

    if (
      accelerometerData &&
      accelerometerData.readings &&
      gyroscopeData &&
      gyroscopeData.readings &&
      magnetometerData &&
      magnetometerData.readings
    ) {
      calculateOrientationData(run);
    }

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
      ensureRunName(run);
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

const getSingleRunSavitzkyGolayFilter = async (runid) => {
  try {
    const run = await runService.getSingleRun(runid);

    if (!run || !run.data || !run.data[0]?.readings) {
      throw new Error("Invalid run data structure");
    }

    // Apply Savitzky-Golay filter to accelerometer, gyroscope, and magnetometer data
    run.data.forEach((sensorData) => {
      if (
        ["accelerometer", "gyroscope", "magnetometer"].includes(
          sensorData._id
        ) &&
        sensorData.readings
      ) {
        const options = { windowSize: 401, polynomial: 3, derivative: 0 };

        // Extract axis time series arrays
        const xValues = sensorData.readings.map((r) => r.data[0]);
        const yValues = sensorData.readings.map((r) => r.data[1]);
        const zValues = sensorData.readings.map((r) => r.data[2]);

        // Apply Savitzky-Golay smoothing
        const smoothX = savitzkyGolay(xValues, 1, options);
        const smoothY = savitzkyGolay(yValues, 1, options);
        const smoothZ = savitzkyGolay(zValues, 1, options);

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
    //FIXME: handle error where orientation calculation is not possible due to lack of sensors...
    calculateOrientationData(run);

    return run;
  } catch (error) {
    throw new Error(error.message);
  }
};

const getRunSensorData = async (runid, sensorid) => {
  try {
    const sensorData = await runService.getRunSensorReadings(runid, sensorid);
    return sensorData;
  } catch (error) {
    throw new Error(error.message);
  }
};

const getRunSensors = async (runid) => {
  try {
    const sensors = await runService.getRunSensors(runid);
    return sensors;
  } catch (err) {
    throw new Error(err.message);
  }
};

const getRunSensorOrientationData = async (
  runid,
  accelerometerid,
  gyroscopeid,
  magnetometerid
) => {
  try {
    // const sensorData = await runService.getRunSensorReadings(runid, sensorid);

    const accelerometerData = await runService.getRunSensorReadings(
      runid,
      accelerometerid
    );

    const gyroscopeData = await runService.getRunSensorReadings(
      runid,
      gyroscopeid
    );
    const magnetometerData = await runService.getRunSensorReadings(
      runid,
      magnetometerid
    );
    // const accelerometerData = sensorData.find(
    //   (d) => d.type === "accelerometer"
    // ).data;
    // const gyroscopeData = sensorData.find((d) => d.type === "gyroscope").data;
    // const magnetometerData = sensorData.find(
    //   (d) => d.type === "magnetometer"
    // ).data;

    if (
      !accelerometerData ||
      !Array.isArray(accelerometerData) ||
      accelerometerData.length === 0
    ) {
      throw new Error(
        `Missing accelerometer data for sensor ${accelerometerid}`
      );
    }
    if (
      !gyroscopeData ||
      !Array.isArray(gyroscopeData) ||
      gyroscopeData.length === 0
    ) {
      throw new Error(`Missing gyroscope data for sensor ${gyroscopeid}`);
    }
    if (
      !magnetometerData ||
      !Array.isArray(magnetometerData) ||
      magnetometerData.length === 0
    ) {
      throw new Error(`Missing magnetometer data for sensor ${magnetometerid}`);
    }

    // Extract timestamps from magnetometer data
    const magnetometerTimestamps = magnetometerData.map(
      (reading) => reading.timestamp
    );

    // Downsample accelerometer and gyroscope data to match magnetometer timestamps
    const downsampledAccelerometer = downsampleToMatch(
      accelerometerData,
      magnetometerTimestamps
    );
    const downsampledGyroscope = downsampleToMatch(
      gyroscopeData,
      magnetometerTimestamps
    );

    var orientationData = [];

    // Calculate orientation using downsampled data
    downsampledAccelerometer.forEach((accel, index) => {
      const gyro = downsampledGyroscope[index];
      const mag = magnetometerData[index];

      const deltaTime = 0.01; // Example deltaTime, replace with actual calculation if available

      const orientation = calculateOrientation(
        { x: accel.data[0], y: accel.data[1], z: accel.data[2] },
        { x: gyro.data[0], y: gyro.data[1], z: gyro.data[2] },
        { x: mag.data[0], y: mag.data[1], z: mag.data[2] },
        deltaTime
      );

      orientationData.push({
        timestamp: magnetometerTimestamps[index],
        ...orientation,
      });
    });

    return orientationData;
  } catch (err) {
    throw new Error(err.message);
  }
};

const applyKalmanFilter = (sensorData) => {
  const kfX = new KalmanFilter({ R: 0.01, Q: 1 });
  const kfY = new KalmanFilter({ R: 0.01, Q: 1 });
  const kfZ = new KalmanFilter({ R: 0.01, Q: 1 });

  // const kfX = new KalmanFilter({ R: 0.0001, Q: 1 });
  // const kfY = new KalmanFilter({ R: 0.0001, Q: 1 });
  // const kfZ = new KalmanFilter({ R: 0.0001, Q: 1 });

  sensorData.forEach((reading) => {
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
};

const filterSensorData = (sensorData, filters) => {
  if (!sensorData || !filters) return sensorData;
  const filtersList = filters.split(",").map((f) => f.trim());
  filtersList.forEach((filter) => {
    switch (filter.toLowerCase()) {
      case "kalman":
        applyKalmanFilter(sensorData);
        break;
      case "movingaverage":
        const windowSize = 200;
        const xValues = sensorData.map((r) => r.data[0]);
        const yValues = sensorData.map((r) => r.data[1]);
        const zValues = sensorData.map((r) => r.data[2]);

        const smoothX = movingAverage(xValues, windowSize);
        const smoothY = movingAverage(yValues, windowSize);
        const smoothZ = movingAverage(zValues, windowSize);

        sensorData.forEach((reading, idx) => {
          if (reading.data && Array.isArray(reading.data)) {
            reading.data[0] = smoothX[idx];
            reading.data[1] = smoothY[idx];
            reading.data[2] = smoothZ[idx];
          }
        });
        break;
      case "savitzkygolay":
        const options = { windowSize: 401, polynomial: 3, derivative: 0 };
        const sgXValues = sensorData.map((r) => r.data[0]);
        const sgYValues = sensorData.map((r) => r.data[1]);
        const sgZValues = sensorData.map((r) => r.data[2]);

        const sgSmoothX = savitzkyGolay(sgXValues, 1, options);
        const sgSmoothY = savitzkyGolay(sgYValues, 1, options);
        const sgSmoothZ = savitzkyGolay(sgZValues, 1, options);

        sensorData.forEach((reading, idx) => {
          if (reading.data && Array.isArray(reading.data)) {
            reading.data[0] = sgSmoothX[idx];
            reading.data[1] = sgSmoothY[idx];
            reading.data[2] = sgSmoothZ[idx];
          }
        });
        break;
    }
  });

  return sensorData;
};

module.exports = {
  getAllRuns,
  getSingleRun,
  getSingleRunDB,
  filterRunsByDate,
  createRun,
  getSingleRunKalmanFilter,
  getSingleRunMovingAverage,
  getSingleRunSavitzkyGolayFilter,
  getRunSensorData,
  getRunSensors,
  getRunSensorOrientationData,
  filterSensorData,
};
