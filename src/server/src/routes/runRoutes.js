const express = require("express");
const runRouter = express.Router();
const sensorRouter = express.Router({ mergeParams: true });
const sensorDataRouter = express.Router({ mergeParams: true });

const runController = require("../controllers/runController");
const trackController = require("../controllers/trackController");
const driverController = require("../controllers/driverController");
const { parseApiDataObject } = require("../controllers/sensorDataController");
const { connectDB, getCollection } = require("../config/db");
const { ObjectId } = require("mongodb");

const DEFAULT_SENSITIVITY = 19.5;
const SENSOR_TYPE_TO_ID = Object.freeze({
  accelerometer: 3,
  strainGauge: 5,
  gps: 6,
});
const SENSOR_TYPE_CONFIG = Object.freeze({
  accelerometer: {
    recordSizeBytes: 16,
    dataAxis: 3,
  },
  strainGauge: {
    recordSizeBytes: 36,
    dataAxis: 8,
  },
  gps: {
    recordSizeBytes: 16,
    dataAxis: 3,
  },
});
const DEFAULT_SENSOR_TYPE = "accelerometer";

const parseNumber = (value, fallback) => {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const parseInteger = (value, fallback) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const normalizeSensorType = (value) => {
  if (!value) return DEFAULT_SENSOR_TYPE;
  const normalized = String(value).trim().toLowerCase();
  if (normalized === "accelerometer") return "accelerometer";
  if (
    normalized === "straingauge" ||
    normalized === "strain_gauge" ||
    normalized === "strain-gauge"
  ) {
    return "strainGauge";
  }
  if (normalized === "gps") return "gps";
  return null;
};

runRouter.use("/:runid/sensor", sensorRouter);
sensorRouter.use("/:sensorid", sensorDataRouter);

runRouter.get("/", async (req, res) => {
  try {
    const { dateFrom: dateFrom, dateTo: dateTo } = req.query;
    if (dateFrom || dateTo) {
      const runs = await runController.filterRunsByDate(dateFrom, dateTo);
      res.json(runs);
    } else {
      const runs = await runController.getAllRuns();
      // const runs = await runController.getAllRunsDB();
      res.json(runs);
    }
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching drivers", error: error.message });
  }
});

runRouter.get("/:runid", async (req, res) => {
  try {
    // const { dateFrom, dateTo } = req.query;

    // const { filterData } = req.query;
    const runid = req.params.runid;
    // var runs = null;
    // if (dateFrom && dateTo) {
    //   runs = await runController.filterRunsByDate(dateFrom, dateTo);
    // } else {
    //   runs = await runController.getAllRuns();
    // }

    let selectedRun = null;
    // if (filterData == "true") {
    //   // selectedRun = await runController.getSingleRunKalmanFilter(runid);
    //   selectedRun = await runController.getSingleRunMovingAverage(runid);
    //   // selectedRun = await runController.getSingleRunSavitzkyGolayFilter(runid);
    // } else {
    //   selectedRun = await runController.getSingleRunDB(runid);
    // }

    selectedRun = await runController.getSingleRunDB(runid);

    // const selectedRun = await runController.getSingleRun(runid);
    // const runTrack = await trackController.getSingleTrack(selectedRun.trackid);
    // const runDriver = await driverController.getSingleDriver(
    //   selectedRun.driverid
    // );

    // selectedRun.Track = runTrack;
    // selectedRun.Driver = runDriver;

    res.json(selectedRun);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching run", error: error.message });
  }
});

runRouter.delete("/:runid", async (req, res) => {
  try {
    const runid = req.params.runid;
    let runObjectId;

    try {
      runObjectId = new ObjectId(runid);
    } catch (err) {
      return res.status(400).json({ message: "Invalid run id." });
    }

    const db = await connectDB();
    const runsColl = await getCollection(db, "runs");
    const sensorReadingsColl = await getCollection(db, "sensor_readings");

    const existingRun = await runsColl.findOne({ _id: runObjectId });
    if (!existingRun) {
      return res.status(404).json({ message: "Run not found." });
    }

    const sensorDeleteResult = await sensorReadingsColl.deleteMany({
      runId: runObjectId,
    });
    const runDeleteResult = await runsColl.deleteOne({ _id: runObjectId });

    if (runDeleteResult.deletedCount !== 1) {
      return res.status(500).json({
        message: "Failed to delete run record.",
      });
    }

    return res.status(200).json({
      message: "Run and related sensor readings deleted successfully.",
      runId: runid,
      deletedRuns: runDeleteResult.deletedCount,
      deletedSensorReadings: sensorDeleteResult.deletedCount,
    });
  } catch (error) {
    return res.status(500).json({
      message: "Error deleting run.",
      error: error.message,
    });
  }
});

runRouter.post("/upload", async (req, res) => {
  try {
    if (!Buffer.isBuffer(req.body) || req.body.length === 0) {
      return res.status(400).json({
        message: "Upload requires application/octet-stream body with .BIN data.",
      });
    }

    const {
      runId,
      name,
      runName,
      driverName,
      driverAge,
      licenseNumber,
      trackName,
      trackLocation,
      trackLength,
      driverId,
      trackId,
      runDate,
      runTime,
      sensorType,
      sensorId,
      sensX,
      sensY,
      sensZ,
    } = req.query;

    const resolvedSensorType = normalizeSensorType(sensorType);
    if (!resolvedSensorType) {
      return res.status(400).json({
        message:
          "Invalid sensorType. Supported values: accelerometer, strainGauge, gps.",
      });
    }

    const sensorConfig = SENSOR_TYPE_CONFIG[resolvedSensorType];

    if (req.body.length % sensorConfig.recordSizeBytes !== 0) {
      return res.status(400).json({
        message: `Invalid .BIN length (${req.body.length}). Expected multiple of ${sensorConfig.recordSizeBytes} for sensorType ${resolvedSensorType}.`,
      });
    }

    const db = await connectDB();
    const runsColl = await getCollection(db, "runs");
    const driversColl = await getCollection(db, "drivers");
    const tracksColl = await getCollection(db, "tracks");
    const sensorReadingsColl = await getCollection(db, "sensor_readings");

    let resolvedRunId = null;
    let runCreated = false;
    let timeOverride = runTime !== undefined ? parseInteger(runTime, 0) : null;
    let resolvedRunName = String(name || runName || "").trim();

    if (runId) {
      try {
        resolvedRunId = new ObjectId(runId);
      } catch (err) {
        return res.status(400).json({ message: "Invalid runId." });
      }

      const existingRun = await runsColl.findOne({ _id: resolvedRunId });
      if (!existingRun) {
        return res.status(404).json({ message: "runId not found." });
      }

      resolvedRunName =
        resolvedRunName ||
        (existingRun.name && String(existingRun.name).trim()) ||
        `Run ${resolvedRunId.toString()}`;
    } else {
      let resolvedDriverId = null;
      if (driverId) {
        try {
          resolvedDriverId = new ObjectId(driverId);
        } catch (err) {
          return res.status(400).json({ message: "Invalid driverId." });
        }
        const existingDriver = await driversColl.findOne({
          _id: resolvedDriverId,
        });
        if (!existingDriver) {
          return res.status(400).json({ message: "driverId not found." });
        }
      } else {
        const resolvedLicense =
          (licenseNumber && String(licenseNumber).trim()) || "UNKNOWN";
        let driver = await driversColl.findOne({
          licenseNumber: resolvedLicense,
        });
        if (!driver) {
          const driverResult = await driversColl.insertOne({
            name: (driverName && String(driverName).trim()) || "Unknown Driver",
            age: parseInteger(driverAge, 0),
            licenseNumber: resolvedLicense,
          });
          driver = { _id: driverResult.insertedId };
        }
        resolvedDriverId = driver._id;
      }

      let resolvedTrackId = null;
      if (trackId) {
        try {
          resolvedTrackId = new ObjectId(trackId);
        } catch (err) {
          return res.status(400).json({ message: "Invalid trackId." });
        }
        const existingTrack = await tracksColl.findOne({
          _id: resolvedTrackId,
        });
        if (!existingTrack) {
          return res.status(400).json({ message: "trackId not found." });
        }
      } else {
        const resolvedTrackName =
          (trackName && String(trackName).trim()) || "Unknown Track";
        let track = await tracksColl.findOne({ name: resolvedTrackName });
        if (!track) {
          const trackResult = await tracksColl.insertOne({
            name: resolvedTrackName,
            length: parseInteger(trackLength, 0),
            location:
              (trackLocation && String(trackLocation).trim()) || "Unknown",
          });
          track = { _id: trackResult.insertedId };
        }
        resolvedTrackId = track._id;
      }

      const parsedRunDate = runDate ? new Date(runDate) : new Date();
      if (Number.isNaN(parsedRunDate.getTime())) {
        return res.status(400).json({ message: "Invalid runDate." });
      }

      resolvedRunId = new ObjectId();
      await runsColl.insertOne({
        _id: resolvedRunId,
        name: resolvedRunName || `Run ${resolvedRunId.toString()}`,
        date: parsedRunDate,
        driverId: resolvedDriverId,
        trackId: resolvedTrackId,
        time: timeOverride ?? 0,
      });
      runCreated = true;
    }

    const defaultSensorId = SENSOR_TYPE_TO_ID[resolvedSensorType];
    const resolvedSensorId = parseInteger(sensorId, defaultSensorId);

    const sensorsColl = await getCollection(db, "sensors");
    await sensorsColl.updateOne(
      { id: resolvedSensorId },
      {
        $set: {
          type: resolvedSensorType,
          dataAxis: sensorConfig.dataAxis,
          location: "uploaded",
        },
        $setOnInsert: {
          id: resolvedSensorId,
        },
      },
      { upsert: true }
    );

    const sensitivityX =
      resolvedSensorType === "accelerometer"
        ? parseNumber(sensX, DEFAULT_SENSITIVITY)
        : 1;
    const sensitivityY =
      resolvedSensorType === "accelerometer"
        ? parseNumber(sensY, DEFAULT_SENSITIVITY)
        : 1;
    const sensitivityZ =
      resolvedSensorType === "accelerometer"
        ? parseNumber(sensZ, DEFAULT_SENSITIVITY)
        : 1;

    let firstTimestamp = null;
    let lastTimestamp = null;
    const batch = [];
    const batchSize = 1000;

    const flushBatch = async () => {
      if (batch.length === 0) return;
      await sensorReadingsColl.insertMany(batch);
      batch.length = 0;
    };

    for (
      let offset = 0;
      offset < req.body.length;
      offset += sensorConfig.recordSizeBytes
    ) {
      const tsUs = req.body.readUInt32LE(offset);

      const timestampSeconds = tsUs / 1_000_000.0;
      if (firstTimestamp === null) firstTimestamp = timestampSeconds;
      lastTimestamp = timestampSeconds;

      let parsedData;
      if (resolvedSensorType === "strainGauge") {
        parsedData = [
          req.body.readInt32LE(offset + 4),
          req.body.readInt32LE(offset + 8),
          req.body.readInt32LE(offset + 12),
          req.body.readInt32LE(offset + 16),
          req.body.readInt32LE(offset + 20),
          req.body.readInt32LE(offset + 24),
          req.body.readInt32LE(offset + 28),
          req.body.readInt32LE(offset + 32),
        ];
      } else {
        const x = req.body.readInt32LE(offset + 4);
        const y = req.body.readInt32LE(offset + 8);
        const z = req.body.readInt32LE(offset + 12);

        parsedData = [
          (x * sensitivityX) / 1_000_000.0,
          (y * sensitivityY) / 1_000_000.0,
          (z * sensitivityZ) / 1_000_000.0,
        ];
      }

      batch.push({
        runId: resolvedRunId,
        sensorId: resolvedSensorId,
        sensorType: resolvedSensorType,
        timestamp: timestampSeconds,
        data: parsedData,
      });

      if (batch.length >= batchSize) {
        await flushBatch();
      }
    }

    await flushBatch();

    if (timeOverride === null && firstTimestamp !== null && runCreated) {
      const derivedSeconds = Math.max(
        0,
        Math.round(lastTimestamp - firstTimestamp)
      );
      await runsColl.updateOne(
        { _id: resolvedRunId },
        { $set: { time: derivedSeconds } }
      );
    } else if (timeOverride !== null && !runCreated) {
      await runsColl.updateOne(
        { _id: resolvedRunId },
        { $set: { time: timeOverride } }
      );
    }

    return res.status(runCreated ? 201 : 200).json({
      message: runCreated
        ? "Run uploaded successfully."
        : "Sensor data uploaded to existing run successfully.",
      runId: resolvedRunId,
      name: resolvedRunName || `Run ${resolvedRunId.toString()}`,
      createdRun: runCreated,
      sensorType: resolvedSensorType,
      sensorId: resolvedSensorId,
    });
  } catch (error) {
    return res.status(500).json({
      message: "Error uploading run.",
      error: error.message,
    });
  }
});

runRouter.post("/", async (req, res) => {
  try {
    const message = JSON.parse(data.toString());
    console.log(message.type);

    const data = Buffer.from(req.body);
    var parsedData = parseApiDataObject(data);

    // const newRun = await runController.createRun(parsedData);

    res.json(newRun);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error creating run", error: error.message });
  }
});

runRouter.post("/filter-runs", async (req, res) => {
  try {
    const { "date-from": dateFrom, "date-to": dateTo } = req.body;
    const filteredRuns = await runController.filterRunsByDate(dateFrom, dateTo);
    // res.render("dashboard", {
    //   title: "Runs",
    //   runs: filteredRuns,
    //   selectedRun: null,
    //   dateFrom: dateFrom,
    //   dateTo: dateTo,
    // });
    return res.json(filteredRuns);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error filtering runs", error: error.message });
  }
});

sensorRouter.get("/", async (req, res) => {
  try {
    const runid = req.params.runid;
    const sensors = await runController.getRunSensors(runid);
    res.json(sensors);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching sensors", error: error.message });
  }
});

sensorRouter.get("/orientation", async (req, res) => {
  try {
    const runid = req.params.runid;
    const { accelerometerid, gyroscopeid, magnetometerid } = req.query;

    const orientationData = await runController.getRunSensorOrientationData(
      runid,
      accelerometerid,
      gyroscopeid,
      magnetometerid
    );

    return res.json(orientationData);
  } catch (err) {
    res.status(500).json({
      message: "Error fetching sensor orientation",
      error: err.message,
    });
  }
});

sensorRouter.get("/:sensorid", async (req, res) => {
  try {
    const runid = req.params.runid;
    const sensorid = req.params.sensorid;
    const sensorData = await runController.getRunSensorData(runid, sensorid);
    res.json(sensorData);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching sensor data", error: error.message });
  }
});

//TODO: Implement the filtering passing and array of filters to use and recieving filtered data
sensorDataRouter.get("/data", async (req, res) => {
  try {
    const { filters, start, end, resolution, mode } = req.query;
    const runid = req.params.runid;
    const sensorid = req.params.sensorid;
    const sensorData = await runController.getRunSensorData(runid, sensorid, {
      filters,
      start,
      end,
      resolution,
      mode,
    });

    res.json(sensorData);
  } catch (err) {
    res.status(500).json({
      message: "Error fetching sensor data",
      error: err.message,
    });
  }
});

module.exports = runRouter;
