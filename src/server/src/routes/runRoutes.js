const express = require("express");
const runRouter = express.Router();
const sensorRouter = express.Router({ mergeParams: true });
const sensorDataRouter = express.Router({ mergeParams: true });

const runController = require("../controllers/runController");
const runService = require("../services/runService");
const trackController = require("../controllers/trackController");
const driverController = require("../controllers/driverController");
const { parseApiDataObject } = require("../controllers/sensorDataController");
const { connectDB, getCollection } = require("../config/db");
const { ObjectId } = require("mongodb");
const { getRunVideoDirectory } = require("../utils/videoStorage");
const fs = require("fs");

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
    csvColumns: ["timestamp", "x", "y", "z"],
  },
  strainGauge: {
    recordSizeBytes: 36,
    dataAxis: 8,
    csvColumns: ["timestamp", "ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8"],
  },
  gps: {
    recordSizeBytes: 16,
    dataAxis: 3,
    csvColumns: ["timestamp", "x", "y", "z"],
  },
});
const DEFAULT_SENSOR_TYPE = "accelerometer";
const CSV_TIMESTAMP_ALIASES = Object.freeze([
  "timestamp",
  "timestampseconds",
  "timestamps",
  "timestampsec",
  "timestampus",
  "timestampmicroseconds",
  "timestampms",
  "timestampmilliseconds",
]);
const CSV_VALUE_ALIASES = Object.freeze({
  accelerometer: [
    ["x", "accelx", "xaxis"],
    ["y", "accely", "yaxis"],
    ["z", "accelz", "zaxis"],
  ],
  gps: [
    ["x", "latitude", "lat"],
    ["y", "longitude", "lon", "lng"],
    ["z", "altitude", "alt"],
  ],
  strainGauge: [
    ["ch1", "channel1", "v1", "value1"],
    ["ch2", "channel2", "v2", "value2"],
    ["ch3", "channel3", "v3", "value3"],
    ["ch4", "channel4", "v4", "value4"],
    ["ch5", "channel5", "v5", "value5"],
    ["ch6", "channel6", "v6", "value6"],
    ["ch7", "channel7", "v7", "value7"],
    ["ch8", "channel8", "v8", "value8"],
  ],
});

const normalizeLabelNumber = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const parseFiniteNumber = (...values) => {
  for (const value of values) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
};

const normalizeRunLabels = (labels) => {
  if (!Array.isArray(labels)) {
    throw new Error("Labels must be an array.");
  }

  return labels.map((label, index) => {
    const id = String(label?.id || "").trim();
    const legacyXTimestamp = parseFiniteNumber(label?.xTimestamp);
    const legacyYValue = parseFiniteNumber(label?.yValue);
    const kind = String(label?.kind || (legacyXTimestamp !== null ? "single" : ""))
      .trim()
      .toLowerCase();
    const text = String(label?.text || "").trim();
    const traceKeys = Array.isArray(label?.traceKeys)
      ? label.traceKeys.map((traceKey) => String(traceKey).trim()).filter(Boolean)
      : [];
    const points = Array.isArray(label?.points)
      ? label.points
          .map((point) => {
            const traceKey = String(point?.traceKey || "").trim();
            const timestamp = parseFiniteNumber(point?.timestamp);
            const yValue = parseFiniteNumber(point?.yValue);
            if (!traceKey || timestamp === null || yValue === null) {
              return null;
            }
            return { traceKey, timestamp, yValue };
          })
          .filter(Boolean)
      : [];
    const startTimestamp = parseFiniteNumber(label?.startTimestamp, legacyXTimestamp);
    const endTimestamp = parseFiniteNumber(label?.endTimestamp, legacyXTimestamp);
    const anchorTimestamp = parseFiniteNumber(label?.anchorTimestamp, legacyXTimestamp);
    const anchorY = parseFiniteNumber(label?.anchorY, legacyYValue);

    if (!id) {
      throw new Error(`Label ${index + 1} is missing an id.`);
    }

    if (!["single", "range"].includes(kind)) {
      throw new Error(`Label ${index + 1} has invalid kind.`);
    }

    if (
      startTimestamp === null ||
      endTimestamp === null ||
      anchorTimestamp === null ||
      anchorY === null
    ) {
      throw new Error(`Label ${index + 1} has invalid sensor grouping coordinates.`);
    }

    return {
      id,
      kind,
      text,
      color: String(label?.color || "#0d6efd").trim() || "#0d6efd",
      traceKeys,
      points: kind === "single" ? points : [],
      startTimestamp: Math.min(startTimestamp, endTimestamp),
      endTimestamp: Math.max(startTimestamp, endTimestamp),
      anchorTimestamp,
      anchorY,
      dx: normalizeLabelNumber(label?.dx, 0),
      dy: normalizeLabelNumber(label?.dy, 0),
      createdAt: label?.createdAt ? new Date(label.createdAt) : new Date(),
      updatedAt: new Date(),
    };
  });
};

const normalizeContext = (value) => {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  return normalized || null;
};

const isGlobalAdmin = (user) => user?.role === "admin";

const getUserContexts = (user) =>
  Array.isArray(user?.contexts)
    ? user.contexts
        .map((context) => normalizeContext(context?.name))
        .filter(Boolean)
    : [];

const getUserContextIds = (user) =>
  Array.isArray(user?.contexts)
    ? user.contexts
        .map((context) =>
          ObjectId.isValid(context?.id) ? new ObjectId(context.id) : null
        )
        .filter(Boolean)
    : [];

const canAccessContext = (user, contextName, contextId = null) => {
  if (isGlobalAdmin(user)) return true;
  if (contextId && ObjectId.isValid(contextId)) {
    return getUserContextIds(user).some(
      (entry) => String(entry) === String(contextId)
    );
  }
  return getUserContexts(user).includes(normalizeContext(contextName));
};

const canAdministerContext = (user, contextName) => {
  if (isGlobalAdmin(user)) return true;
  return false;
};

const buildRunAccessQuery = (user) => {
  if (isGlobalAdmin(user)) {
    return {};
  }

  const contexts = getUserContexts(user);
  const contextIds = getUserContextIds(user);
  if (contexts.length === 0 && contextIds.length === 0) {
    return { _id: { $exists: false } };
  }

  const filters = [];
  if (contexts.length > 0) {
    filters.push({ context: { $in: contexts } });
  }
  if (contextIds.length > 0) {
    filters.push({ contextId: { $in: contextIds } });
  }

  return filters.length === 1 ? filters[0] : { $or: filters };
};

const findRunForUser = async (runId, user) => {
  const runObjectId = new ObjectId(runId);
  const db = await connectDB();
  const runsColl = await getCollection(db, "runs");

  return runsColl.findOne({
    _id: runObjectId,
    ...buildRunAccessQuery(user),
  });
};

const parseNumber = (value, fallback) => {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const parseInteger = (value, fallback) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const hasText = (value) => String(value || "").trim().length > 0;

const parseRunMetadata = (value) => {
  if (!hasText(value)) return null;

  let parsed;
  try {
    parsed = JSON.parse(String(value));
  } catch (error) {
    throw new Error("metadata must be valid JSON.");
  }

  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("metadata must be a JSON object.");
  }

  return parsed;
};

const normalizeCsvHeader = (value) =>
  String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");

const parseCsvLine = (line) => {
  const values = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const nextChar = line[index + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      values.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  values.push(current.trim());
  return values;
};

const parseCsvRows = (csvText) => {
  const normalizedText = String(csvText || "").replace(/^\uFEFF/, "");
  const lines = normalizedText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    throw new Error("CSV upload requires a header row and at least one data row.");
  }

  const headerCells = parseCsvLine(lines[0]).map(normalizeCsvHeader);
  if (headerCells.length === 0 || headerCells.every((cell) => !cell)) {
    throw new Error("CSV header row is empty.");
  }

  const rows = lines.slice(1).map((line, index) => {
    const cells = parseCsvLine(line);
    const row = {};
    headerCells.forEach((header, cellIndex) => {
      if (header) {
        row[header] = cells[cellIndex] ?? "";
      }
    });
    row.__rowNumber = index + 2;
    return row;
  });

  return { headerCells, rows };
};

const getCsvFieldValue = (row, aliases) => {
  for (const alias of aliases) {
    if (row[alias] !== undefined && row[alias] !== null && row[alias] !== "") {
      return row[alias];
    }
  }
  return null;
};

const parseCsvNumberField = (row, aliases, label, rowNumber) => {
  const rawValue = getCsvFieldValue(row, aliases);
  if (rawValue === null) {
    throw new Error(`CSV row ${rowNumber} is missing required column ${label}.`);
  }

  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    throw new Error(`CSV row ${rowNumber} has invalid numeric value for ${label}.`);
  }

  return parsed;
};

const parseCsvTimestamp = (row, rowNumber) => {
  if (row.timestamp !== undefined && row.timestamp !== null && row.timestamp !== "") {
    return parseCsvNumberField(row, ["timestamp"], "timestamp", rowNumber);
  }
  if (
    row.timestampseconds !== undefined &&
    row.timestampseconds !== null &&
    row.timestampseconds !== ""
  ) {
    return parseCsvNumberField(
      row,
      ["timestampseconds"],
      "timestampSeconds",
      rowNumber
    );
  }
  if (row.timestamps !== undefined && row.timestamps !== null && row.timestamps !== "") {
    return parseCsvNumberField(row, ["timestamps"], "timestamp_s", rowNumber);
  }
  if (row.timestampsec !== undefined && row.timestampsec !== null && row.timestampsec !== "") {
    return parseCsvNumberField(row, ["timestampsec"], "timestampSec", rowNumber);
  }
  if (row.timestampms !== undefined && row.timestampms !== null && row.timestampms !== "") {
    return (
      parseCsvNumberField(row, ["timestampms"], "timestamp_ms", rowNumber) / 1000
    );
  }
  if (
    row.timestampmilliseconds !== undefined &&
    row.timestampmilliseconds !== null &&
    row.timestampmilliseconds !== ""
  ) {
    return (
      parseCsvNumberField(
        row,
        ["timestampmilliseconds"],
        "timestampMilliseconds",
        rowNumber
      ) / 1000
    );
  }
  if (row.timestampus !== undefined && row.timestampus !== null && row.timestampus !== "") {
    return (
      parseCsvNumberField(row, ["timestampus"], "timestamp_us", rowNumber) /
      1_000_000
    );
  }
  if (
    row.timestampmicroseconds !== undefined &&
    row.timestampmicroseconds !== null &&
    row.timestampmicroseconds !== ""
  ) {
    return (
      parseCsvNumberField(
        row,
        ["timestampmicroseconds"],
        "timestampMicroseconds",
        rowNumber
      ) / 1_000_000
    );
  }

  throw new Error(
    `CSV row ${rowNumber} is missing a timestamp column. Expected one of: ${CSV_TIMESTAMP_ALIASES.join(", ")}.`
  );
};

const buildCsvSensorReadings = (csvText, sensorType) => {
  const { rows } = parseCsvRows(csvText);
  const aliasesByAxis = CSV_VALUE_ALIASES[sensorType];
  if (!aliasesByAxis) {
    throw new Error(`CSV import is not configured for sensorType ${sensorType}.`);
  }

  const readings = rows.map((row) => {
    const rowNumber = row.__rowNumber;
    const timestamp = parseCsvTimestamp(row, rowNumber);
    const data = aliasesByAxis.map((aliases, axisIndex) =>
      parseCsvNumberField(
        row,
        aliases.map(normalizeCsvHeader),
        SENSOR_TYPE_CONFIG[sensorType].csvColumns[axisIndex + 1],
        rowNumber
      )
    );

    return { timestamp, data };
  });

  return readings.sort((left, right) => left.timestamp - right.timestamp);
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
    const runs = dateFrom || dateTo
      ? await runController.filterRunsByDate(dateFrom, dateTo)
      : await runController.getAllRuns();
    const visibleRuns = runs.filter((run) =>
      canAccessContext(req.user, run.context, run.contextId),
    );
    res.json(visibleRuns);
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
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }
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

runRouter.put("/:runid/labels", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }

    const labels = normalizeRunLabels(req.body?.labels);
    const updatedRun = await runService.updateRunLabels(runid, labels);
    return res.json({ labels: updatedRun?.labels || [] });
  } catch (error) {
    return res.status(400).json({
      message: "Failed to update run labels.",
      error: error.message,
    });
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

    if (!canAdministerContext(req.user, existingRun.context, existingRun.contextId)) {
      return res.status(403).json({ message: "Not allowed to delete this run." });
    }

    const sensorDeleteResult = await sensorReadingsColl.deleteMany({
      runId: runObjectId,
    });
    await runService.deleteRunLabels(runid);
    const runDeleteResult = await runsColl.deleteOne({ _id: runObjectId });
    const runVideoDirectory = getRunVideoDirectory(runid);

    try {
      await fs.promises.rm(runVideoDirectory, { recursive: true, force: true });
    } catch (videoDeleteError) {
      return res.status(500).json({
        message: "Run deleted, but associated video cleanup failed.",
        error: videoDeleteError.message,
      });
    }

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
      metadata,
      sensorType,
      sensorId,
      uploadFormat,
      sensX,
      sensY,
      sensZ,
      context,
      contextId,
    } = req.query;

    const contentType = String(req.headers["content-type"] || "").toLowerCase();
    const requestedFormat = String(uploadFormat || "").trim().toLowerCase();
    const isCsvUpload =
      requestedFormat === "csv" ||
      contentType.includes("text/csv") ||
      contentType.includes("application/csv") ||
      contentType.includes("text/plain") ||
      contentType.includes("application/vnd.ms-excel");
    const isBinUpload = !isCsvUpload && Buffer.isBuffer(req.body);
    const csvBodyText =
      typeof req.body === "string"
        ? req.body
        : Buffer.isBuffer(req.body)
          ? req.body.toString("utf8")
          : "";

    if (
      (!isBinUpload && !isCsvUpload) ||
      (isBinUpload && req.body.length === 0) ||
      (isCsvUpload && csvBodyText.trim().length === 0)
    ) {
      return res.status(400).json({
        message:
          "Upload requires either application/octet-stream .BIN data or text/csv data.",
      });
    }

    const resolvedSensorType = normalizeSensorType(sensorType);
    if (!resolvedSensorType) {
      return res.status(400).json({
        message:
          "Invalid sensorType. Supported values: accelerometer, strainGauge, gps.",
      });
    }

    const sensorConfig = SENSOR_TYPE_CONFIG[resolvedSensorType];
    if (isBinUpload && req.body.length % sensorConfig.recordSizeBytes !== 0) {
      return res.status(400).json({
        message: `Invalid .BIN length (${req.body.length}). Expected multiple of ${sensorConfig.recordSizeBytes} for sensorType ${resolvedSensorType}.`,
      });
    }

    const db = await connectDB();
    const runsColl = await getCollection(db, "runs");
    const contextsColl = await getCollection(db, "contexts");
    const driversColl = await getCollection(db, "drivers");
    const tracksColl = await getCollection(db, "tracks");
    const sensorReadingsColl = await getCollection(db, "sensor_readings");

    let resolvedRunId = null;
    let runCreated = false;
    let timeOverride = runTime !== undefined ? parseInteger(runTime, 0) : null;
    let resolvedRunName = String(name || runName || "").trim();
    let resolvedContext = normalizeContext(context);
    let resolvedContextId = null;
    let metadataUpdate = null;

    try {
      metadataUpdate = parseRunMetadata(metadata);
    } catch (error) {
      return res.status(400).json({ message: error.message });
    }

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

      if (!canAccessContext(req.user, existingRun.context, existingRun.contextId)) {
        return res.status(403).json({ message: "Not allowed to upload to this run." });
      }

      resolvedContext = normalizeContext(existingRun.context);
      resolvedContextId =
        existingRun.contextId && ObjectId.isValid(existingRun.contextId)
          ? new ObjectId(existingRun.contextId)
          : null;

      resolvedRunName =
        resolvedRunName ||
        (existingRun.name && String(existingRun.name).trim()) ||
        `Run ${resolvedRunId.toString()}`;

      const runUpdates = {};
      if (metadataUpdate) {
        runUpdates.metadata = {
          ...(existingRun.metadata && typeof existingRun.metadata === "object" ? existingRun.metadata : {}),
          ...metadataUpdate,
        };
      }
      if (Object.keys(runUpdates).length > 0) {
        await runsColl.updateOne({ _id: resolvedRunId }, { $set: runUpdates });
      }
    } else {
      if (!contextId || !ObjectId.isValid(contextId)) {
        return res.status(400).json({
          message: "A valid contextId is required when creating a new run.",
        });
      }

      const selectedContext = await contextsColl.findOne({
        _id: new ObjectId(contextId),
        deletedAt: null,
      });
      if (!selectedContext) {
        return res.status(400).json({ message: "Selected context not found." });
      }

      resolvedContext = normalizeContext(selectedContext.name);
      resolvedContextId = selectedContext._id;

      if (!canAccessContext(req.user, resolvedContext, resolvedContextId)) {
        return res.status(403).json({
          message: "Not allowed to create runs in this context.",
        });
      }

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
      } else if (hasText(driverName) || hasText(licenseNumber) || hasText(driverAge)) {
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
      } else if (hasText(trackName) || hasText(trackLocation) || hasText(trackLength)) {
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
        context: resolvedContext,
        contextId: resolvedContextId,
        date: parsedRunDate,
        driverId: resolvedDriverId,
        trackId: resolvedTrackId,
        time: timeOverride ?? 0,
        metadata: metadataUpdate || {},
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

    const readings = isBinUpload
      ? (() => {
          const parsedReadings = [];
          for (
            let offset = 0;
            offset < req.body.length;
            offset += sensorConfig.recordSizeBytes
          ) {
            const tsUs = req.body.readUInt32LE(offset);
            const timestampSeconds = tsUs / 1_000_000.0;

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

            parsedReadings.push({
              timestamp: timestampSeconds,
              data: parsedData,
            });
          }
          return parsedReadings;
        })()
      : buildCsvSensorReadings(csvBodyText, resolvedSensorType);

    if (!Array.isArray(readings) || readings.length === 0) {
      return res.status(400).json({
        message: "Upload did not contain any sensor readings.",
      });
    }

    let firstTimestamp = null;
    let lastTimestamp = null;
    const batch = [];
    const batchSize = 1000;

    const flushBatch = async () => {
      if (batch.length === 0) return;
      await sensorReadingsColl.insertMany(batch);
      batch.length = 0;
    };

    for (const reading of readings) {
      if (firstTimestamp === null) firstTimestamp = reading.timestamp;
      lastTimestamp = reading.timestamp;

      batch.push({
        runId: resolvedRunId,
        sensorId: resolvedSensorId,
        sensorType: resolvedSensorType,
        timestamp: reading.timestamp,
        data: reading.data,
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
        ? `Run created and ${isCsvUpload ? "CSV" : "BIN"} data uploaded successfully.`
        : `${isCsvUpload ? "CSV" : "BIN"} sensor data uploaded to existing run successfully.`,
      runId: resolvedRunId,
      name: resolvedRunName || `Run ${resolvedRunId.toString()}`,
      context: resolvedContext,
      contextId: resolvedContextId,
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
    return res.json(
      filteredRuns.filter((run) => canAccessContext(req.user, run.context))
    );
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error filtering runs", error: error.message });
  }
});

sensorRouter.get("/", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }
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
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }
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
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }
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
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }
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
