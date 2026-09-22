const runService = require("../services/runService");

const ensureRunName = (run) => {
  if (!run) return run;
  const fallbackId = run._id ? String(run._id) : "Unknown";
  run.name =
    run.name && String(run.name).trim()
      ? String(run.name).trim()
      : `Run ${fallbackId}`;
  return run;
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

const getSingleRunDB = async (runid) => {
  try {
    let run = await runService.getSingleRunDB(runid);
    run = ensureRunName(run);

    const trims = await runService.getRunTrims(runid);
    const totalTimestamps = await runService.getTotalTimestamps(runid, trims);

    const runObject =
      run && typeof run.toObject === "function" ? run.toObject() : run;

    const response = {
      ...runObject,
      totalTimestamps: totalTimestamps,
      trims: trims,
    };

    return response;
  } catch (error) {
    throw new Error(error.message);
  }
};

const downsampleToMatch = (highRateData, lowRateTimestamps) => {
  if (
    !Array.isArray(highRateData) ||
    !Array.isArray(lowRateTimestamps) ||
    highRateData.length === 0 ||
    lowRateTimestamps.length === 0
  ) {
    return [];
  }

  const sortedHigh = highRateData
    .slice()
    .sort((a, b) => a.timestamp - b.timestamp);
  const highTs = sortedHigh.map((r) => r.timestamp);

  const findClosestIndex = (ts) => {
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

const calculateOrientation = (
  accelerometer,
  gyroscope,
  magnetometer,
  deltaTime
) => {
  let pitch, roll, yaw;

  const accNorm = Math.sqrt(
    accelerometer.x ** 2 + accelerometer.y ** 2 + accelerometer.z ** 2
  );
  const ax = accelerometer.x / accNorm;
  const ay = accelerometer.y / accNorm;
  const az = accelerometer.z / accNorm;

  pitch = Math.atan2(-ax, Math.sqrt(ay ** 2 + az ** 2));
  roll = Math.atan2(ay, az);

  const magNorm = Math.sqrt(
    magnetometer.x ** 2 + magnetometer.y ** 2 + magnetometer.z ** 2
  );
  const mx = magnetometer.x / magNorm;
  const my = magnetometer.y / magNorm;
  const mz = magnetometer.z / magNorm;

  const magX = mx * Math.cos(pitch) + mz * Math.sin(pitch);
  const magY =
    mx * Math.sin(roll) * Math.sin(pitch) +
    my * Math.cos(roll) -
    mz * Math.sin(roll) * Math.cos(pitch);

  const magYaw = Math.atan2(-magY, magX);

  const gz = (gyroscope.z * Math.PI) / 180;

  yaw = magYaw + gz * deltaTime;

  const alpha = 0.98;
  yaw = alpha * yaw + (1 - alpha) * magYaw;

  return { pitch, roll, yaw };
};

const parseFiniteNumber = (value) => {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const normalizeResolution = (value, fallback = 1200) => {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return Math.max(50, Math.min(parsed, 5000));
};

const decimateSensorData = (sensorData, targetPoints) => {
  if (!Array.isArray(sensorData) || sensorData.length <= targetPoints) {
    return sensorData;
  }

  const safeTargetPoints = Math.max(50, targetPoints);
  const bucketCount = Math.max(1, Math.floor(safeTargetPoints / 4));
  const bucketSize = Math.max(1, Math.ceil(sensorData.length / bucketCount));
  const axisCount = sensorData.reduce((maxAxisCount, reading) => {
    const readingAxisCount = Array.isArray(reading?.data) ? reading.data.length : 0;
    return Math.max(maxAxisCount, readingAxisCount);
  }, 0);
  const selectedIndices = new Set([0, sensorData.length - 1]);

  for (
    let bucketStart = 0;
    bucketStart < sensorData.length;
    bucketStart += bucketSize
  ) {
    const bucketEnd = Math.min(sensorData.length, bucketStart + bucketSize);
    if (bucketEnd <= bucketStart) continue;

    selectedIndices.add(bucketStart);
    selectedIndices.add(bucketEnd - 1);

    for (let axisIndex = 0; axisIndex < axisCount; axisIndex++) {
      let minIndex = bucketStart;
      let maxIndex = bucketStart;
      let minValue = sensorData[bucketStart]?.data?.[axisIndex];
      let maxValue = sensorData[bucketStart]?.data?.[axisIndex];

      for (let index = bucketStart + 1; index < bucketEnd; index++) {
        const value = sensorData[index]?.data?.[axisIndex];
        if (typeof value !== "number") continue;

        if (typeof minValue !== "number" || value < minValue) {
          minValue = value;
          minIndex = index;
        }
        if (typeof maxValue !== "number" || value > maxValue) {
          maxValue = value;
          maxIndex = index;
        }
      }

      selectedIndices.add(minIndex);
      selectedIndices.add(maxIndex);
    }
  }

  return [...selectedIndices]
    .sort((a, b) => a - b)
    .map((index) => sensorData[index]);
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

const getRunSensorData = async (runid, sensorid, options = {}) => {
  try {
    const trimRanges = await runService.getRunTrims(runid);
    const rawData = await runService.getRunSensorReadings(runid, sensorid, {
      start: parseFiniteNumber(options.start),
      end: parseFiniteNumber(options.end),
      trimRanges,
    });
    const filteredData = filterSensorData(rawData, options.filters);

    const wantResidual = options.residual === true || options.residual === "true";
    const outputData = wantResidual ? computeResidualReadings(rawData, filteredData) : filteredData;

    if (String(options.mode || "raw").toLowerCase() !== "plot") {
      return {
        mode: "raw",
        sampleCountRaw: outputData.length,
        sampleCountReturned: outputData.length,
        readings: outputData,
      };
    }

    const resolution = normalizeResolution(options.resolution);
    const decimated = decimateSensorData(outputData, resolution);

    return {
      mode: "plot",
      range: {
        start: parseFiniteNumber(options.start),
        end: parseFiniteNumber(options.end),
      },
      resolution,
      sampleCountRaw: outputData.length,
      sampleCountReturned: decimated.length,
      readings: decimated,
    };
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

    const magnetometerTimestamps = magnetometerData.map(
      (reading) => reading.timestamp
    );

    const downsampledAccelerometer = downsampleToMatch(
      accelerometerData,
      magnetometerTimestamps
    );
    const downsampledGyroscope = downsampleToMatch(
      gyroscopeData,
      magnetometerTimestamps
    );

    const orientationData = [];

    downsampledAccelerometer.forEach((accel, index) => {
      const gyro = downsampledGyroscope[index];
      const mag = magnetometerData[index];

      const deltaTime = 0.01;

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

const filterRegistry = require("../filters/registry");

// New format: JSON array of {type, params} objects.
// Legacy format: comma-separated type names (backward compat).
const parseFiltersPipeline = (filtersParam) => {
  if (!filtersParam) return [];
  try {
    const parsed = JSON.parse(filtersParam);
    if (Array.isArray(parsed)) return parsed;
  } catch (_) {
    // fall through to legacy
  }
  return filtersParam.split(",").map((f) => ({ type: f.trim(), params: {} }));
};

const computeResidualReadings = (rawReadings, filteredReadings) =>
  rawReadings.map((raw, i) => {
    const filtered = filteredReadings[i];
    if (!filtered || !Array.isArray(raw.data) || !Array.isArray(filtered.data)) {
      return raw;
    }
    return {
      ...raw,
      data: raw.data.map((v, j) =>
        Number.isFinite(v) && Number.isFinite(filtered.data[j]) ? v - filtered.data[j] : null,
      ),
    };
  });

const filterSensorData = (sensorData, filtersParam) => {
  if (!sensorData || !filtersParam) return sensorData;
  const pipeline = parseFiltersPipeline(filtersParam);
  let current = sensorData;
  for (const { type, params = {} } of pipeline) {
    const filter = filterRegistry.getFilter((type || "").toLowerCase());
    if (!filter) continue;
    try {
      current = filter.apply(current, params);
    } catch (err) {
      console.error(`[filters] Error applying filter '${type}': ${err.message}`);
    }
  }
  return current;
};

module.exports = {
  getAllRuns,
  getSingleRunDB,
  filterRunsByDate,
  getRunSensorData,
  getRunSensors,
  getRunSensorOrientationData,
  filterSensorData,
  decimateSensorData,
};
