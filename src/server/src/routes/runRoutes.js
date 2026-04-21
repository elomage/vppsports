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
  gyroscope: 2,
  strainGauge: 5,
  gps: 6,
});
const SENSOR_TYPE_CONFIG = Object.freeze({
  accelerometer: {
    recordSizeBytes: 16,
    dataAxis: 3,
    csvColumns: ["timestamp", "x", "y", "z"],
  },
  gyroscope: {
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
  gyroscope: [
    ["x", "gyrox", "xaxis"],
    ["y", "gyroy", "yaxis"],
    ["z", "gyroz", "zaxis"],
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

const normalizeRunTrims = (trims) => {
  if (!Array.isArray(trims)) {
    throw new Error("Trims must be an array.");
  }
  return trims.map((trim, index) => {
    const startTimestamp = parseFiniteNumber(trim?.startTimestamp);
    const endTimestamp = parseFiniteNumber(trim?.endTimestamp);
    if (startTimestamp === null || endTimestamp === null) {
      throw new Error(`Trim ${index + 1} has invalid timestamps.`);
    }
    return {
      startTimestamp: Math.min(startTimestamp, endTimestamp),
      endTimestamp: Math.max(startTimestamp, endTimestamp),
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

const DEFAULT_ARFF_RESAMPLE_POINTS = 64;

const flattenMetadata = (value, prefix = "meta") => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  return Object.entries(value).reduce((acc, [key, entryValue]) => {
    const normalizedKey = String(key || "")
      .trim()
      .replace(/[^a-zA-Z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .toLowerCase();
    if (!normalizedKey) return acc;

    const nextKey = `${prefix}_${normalizedKey}`;
    if (
      entryValue &&
      typeof entryValue === "object" &&
      !Array.isArray(entryValue)
    ) {
      Object.assign(acc, flattenMetadata(entryValue, nextKey));
      return acc;
    }

    acc[nextKey] = entryValue;
    return acc;
  }, {});
};

const sanitizeArffAttributeName = (value) =>
  String(value || "")
    .trim()
    .replace(/[^a-zA-Z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase() || "field";

const escapeArffString = (value) =>
  `'${String(value ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/\r?\n/g, " ")}'`;

const toArffValue = (value, type) => {
  if (
    value === undefined ||
    value === null ||
    value === "" ||
    (type === "NUMERIC" && !Number.isFinite(Number(value)))
  ) {
    return "?";
  }

  if (type === "NUMERIC") {
    return String(Number(value));
  }

  return escapeArffString(value);
};

const buildArffDocument = (relationName, attributes, rows) => {
  const header = [
    `@relation ${sanitizeArffAttributeName(relationName)}`,
    "",
    ...attributes.map(
      (attribute) =>
        `@attribute ${sanitizeArffAttributeName(attribute.name)} ${attribute.type}`
    ),
    "",
    "@data",
  ];

  const dataLines = rows.map((row) =>
    attributes
      .map((attribute) => toArffValue(row[attribute.name], attribute.type))
      .join(",")
  );

  return `${header.join("\n")}\n${dataLines.join("\n")}\n`;
};

const parseTraceKey = (traceKey) => {
  const [runId, sensorId, axisIndex, dataMode] = String(traceKey || "").split(":");
  return {
    runId: runId || "",
    sensorId: Number.parseInt(sensorId, 10),
    axisIndex: Number.parseInt(axisIndex, 10),
    dataMode: dataMode || "raw",
  };
};

const toRawTraceKey = (traceKey) => {
  const parsed = parseTraceKey(traceKey);
  if (!parsed.runId || !Number.isFinite(parsed.sensorId) || !Number.isFinite(parsed.axisIndex)) {
    return String(traceKey || "");
  }
  return `${parsed.runId}:${parsed.sensorId}:${parsed.axisIndex}:raw`;
};

const normalizeClassValue = (label) => {
  const raw = String(label?.text || "").trim();
  if (!raw) return "unlabeled";
  return raw.toLowerCase().replace(/\s+/g, "_");
};

const computeStats = (values) => {
  if (!Array.isArray(values) || values.length === 0) {
    return {
      readingCount: 0,
      minValue: null,
      maxValue: null,
      meanValue: null,
      stdValue: null,
      medianValue: null,
      rangeValue: null,
      firstValue: null,
      lastValue: null,
      deltaValue: null,
      slope: null,
      areaUnderCurve: null,
      rmsValue: null,
      peakValue: null,
      peakTimeRatio: null,
      zeroCrossings: 0,
    };
  }

  const sorted = [...values].sort((left, right) => left - right);
  const readingCount = values.length;
  const minValue = sorted[0];
  const maxValue = sorted[sorted.length - 1];
  const meanValue = values.reduce((sum, value) => sum + value, 0) / readingCount;
  const variance =
    values.reduce((sum, value) => sum + (value - meanValue) ** 2, 0) / readingCount;
  const stdValue = Math.sqrt(variance);
  const medianValue =
    sorted.length % 2 === 0
      ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
      : sorted[Math.floor(sorted.length / 2)];
  const firstValue = values[0];
  const lastValue = values[values.length - 1];
  const deltaValue = lastValue - firstValue;
  const rmsValue = Math.sqrt(
    values.reduce((sum, value) => sum + value * value, 0) / readingCount
  );

  let peakValue = values[0];
  let peakIndex = 0;
  let zeroCrossings = 0;
  for (let index = 1; index < values.length; index += 1) {
    if (Math.abs(values[index]) > Math.abs(peakValue)) {
      peakValue = values[index];
      peakIndex = index;
    }
    if (
      (values[index - 1] < 0 && values[index] >= 0) ||
      (values[index - 1] > 0 && values[index] <= 0)
    ) {
      zeroCrossings += 1;
    }
  }

  return {
    readingCount,
    minValue,
    maxValue,
    meanValue,
    stdValue,
    medianValue,
    rangeValue: maxValue - minValue,
    firstValue,
    lastValue,
    deltaValue,
    slope: readingCount > 1 ? deltaValue / (readingCount - 1) : 0,
    areaUnderCurve: values.reduce((sum, value) => sum + value, 0),
    rmsValue,
    peakValue,
    peakTimeRatio: readingCount > 1 ? peakIndex / (readingCount - 1) : 0,
    zeroCrossings,
  };
};

const resampleSeries = (timestamps, values, pointCount) => {
  if (
    !Array.isArray(timestamps) ||
    !Array.isArray(values) ||
    timestamps.length === 0 ||
    values.length === 0 ||
    timestamps.length !== values.length
  ) {
    return new Array(pointCount).fill(null);
  }

  if (timestamps.length === 1) {
    return new Array(pointCount).fill(values[0]);
  }

  const start = timestamps[0];
  const end = timestamps[timestamps.length - 1];
  if (!(end > start)) {
    return new Array(pointCount).fill(values[0]);
  }

  const samples = [];
  let cursor = 0;

  for (let index = 0; index < pointCount; index += 1) {
    const target =
      start + ((end - start) * index) / Math.max(pointCount - 1, 1);

    while (
      cursor < timestamps.length - 2 &&
      Number.isFinite(timestamps[cursor + 1]) &&
      timestamps[cursor + 1] < target
    ) {
      cursor += 1;
    }

    const leftTs = timestamps[cursor];
    const rightTs = timestamps[Math.min(cursor + 1, timestamps.length - 1)];
    const leftValue = values[cursor];
    const rightValue = values[Math.min(cursor + 1, values.length - 1)];

    if (!Number.isFinite(leftTs) || !Number.isFinite(rightTs)) {
      samples.push(null);
      continue;
    }

    if (rightTs === leftTs) {
      samples.push(leftValue);
      continue;
    }

    const ratio = (target - leftTs) / (rightTs - leftTs);
    samples.push(leftValue + (rightValue - leftValue) * ratio);
  }

  return samples;
};

const buildTraceSeriesMap = (runId, sensorReadings) => {
  const map = new Map();

  sensorReadings.forEach((reading) => {
    const axisValues = Array.isArray(reading?.data) ? reading.data : [];
    axisValues.forEach((value, axisIndex) => {
      const traceKey = `${runId}:${reading.sensorId}:${axisIndex}:raw`;
      const existing = map.get(traceKey) || {
        traceKey,
        sensorId: reading.sensorId,
        axisIndex,
        dataMode: "raw",
        timestamps: [],
        values: [],
      };

      existing.timestamps.push(reading.timestamp);
      existing.values.push(Number(value));
      map.set(traceKey, existing);
    });
  });

  return map;
};

const collectLabelTraceRows = (runDocument, sensorReadings) => {
  const runId = String(runDocument._id);
  const traceSeriesMap = buildTraceSeriesMap(runId, sensorReadings);
  const sensorTypeBySensorId = new Map();
  sensorReadings.forEach((reading) => {
    const sensorType =
      reading?.sensorType ||
      reading?.sensorDetails?.[0]?.type ||
      "";
    if (reading?.sensorId !== undefined && sensorType) {
      sensorTypeBySensorId.set(Number(reading.sensorId), String(sensorType));
    }
  });
  const metadata = flattenMetadata(runDocument.metadata);
  const labels = Array.isArray(runDocument.labels) ? runDocument.labels : [];

  return labels.flatMap((label) => {
    const traceKeys = Array.isArray(label.traceKeys) ? label.traceKeys : [];

    return traceKeys.map((traceKey) => {
      const traceInfo =
        traceSeriesMap.get(traceKey) ||
        traceSeriesMap.get(toRawTraceKey(traceKey));
      const parsedTrace = parseTraceKey(traceKey);
      const rows = [];

      if (label.kind === "single" && Array.isArray(label.points) && label.points.length > 0) {
        label.points
          .filter(
            (point) =>
              point.traceKey === traceKey ||
              toRawTraceKey(point.traceKey) === toRawTraceKey(traceKey)
          )
          .forEach((point) => {
            rows.push({
              timestamp: Number(point.timestamp),
              value: Number(point.yValue),
            });
          });
      } else if (traceInfo) {
        for (let index = 0; index < traceInfo.timestamps.length; index += 1) {
          const timestamp = traceInfo.timestamps[index];
          if (timestamp >= label.startTimestamp && timestamp <= label.endTimestamp) {
            rows.push({
              timestamp,
              value: traceInfo.values[index],
            });
          }
        }
      }

      const timestamps = rows.map((entry) => entry.timestamp);
      const values = rows.map((entry) => entry.value);
      const stats = computeStats(values);

      return {
        runId,
        runName: runDocument.name || `Run ${runId}`,
        runDate: runDocument.date ? new Date(runDocument.date).toISOString() : "",
        runTime: Number.isFinite(Number(runDocument.time)) ? Number(runDocument.time) : null,
        context: runDocument.context || "",
        labelId: label.id,
        labelText: label.text || "",
        labelKind: label.kind,
        traceKey,
        sensorId: Number.isFinite(parsedTrace.sensorId) ? parsedTrace.sensorId : null,
        sensorType: sensorTypeBySensorId.get(Number(parsedTrace.sensorId)) || "",
        axisIndex: Number.isFinite(parsedTrace.axisIndex) ? parsedTrace.axisIndex : null,
        dataMode: parsedTrace.dataMode,
        startTimestamp: Number(label.startTimestamp),
        endTimestamp: Number(label.endTimestamp),
        duration: Number(label.endTimestamp) - Number(label.startTimestamp),
        anchorTimestamp: Number(label.anchorTimestamp),
        anchorY: Number(label.anchorY),
        class: normalizeClassValue(label),
        timestamps,
        values,
        ...stats,
        ...metadata,
      };
    }).filter((row) => row.timestamps.length > 0);
  });
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
  if (normalized === "gyroscope" || normalized === "gyro") return "gyroscope";
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

runRouter.get("/:runid/export/arff", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }

    const variant = String(req.query.variant || "features").trim().toLowerCase();
    if (!["features", "resampled"].includes(variant)) {
      return res.status(400).json({
        message: "Invalid variant. Supported values: features, resampled.",
      });
    }

    const resamplePoints = Math.max(
      8,
      Math.min(
        parseInteger(req.query.points, DEFAULT_ARFF_RESAMPLE_POINTS),
        512
      )
    );

    const runDocument = await runService.getSingleRunDB(runid);
    const sensorReadings = await runService.getRunSensorReadingsAll(runid);
    const rows = collectLabelTraceRows(runDocument, sensorReadings);

    if (rows.length === 0) {
      return res.status(400).json({
        message: "Run has no labeled trace data to export.",
      });
    }

    const metadataKeys = [...new Set(rows.flatMap((row) =>
      Object.keys(row).filter((key) => key.startsWith("meta_"))
    ))].sort();

    let attributes;
    let dataRows;

    if (variant === "features") {
      dataRows = rows.flatMap((row) =>
        row.timestamps.map((timestamp, index) => ({
          runId: row.runId,
          runName: row.runName,
          runDate: row.runDate,
          runTime: row.runTime,
          context: row.context,
          sensorType: row.sensorType,
          sensorId: row.sensorId,
          axisIndex: row.axisIndex,
          traceKey: row.traceKey,
          timestamp,
          readings: row.values[index],
          labelId: row.labelId,
          labelText: row.labelText,
          labelKind: row.labelKind,
          class: row.class,
          ...Object.fromEntries(
            metadataKeys.map((key) => [key, row[key] ?? ""])
          ),
        }))
      );
      if (dataRows.length === 0) {
        return res.status(400).json({
          message: "Run labels were found, but no matching sensor reading rows could be resolved for export.",
        });
      }

      attributes = [
        { name: "runId", type: "STRING" },
        { name: "runName", type: "STRING" },
        { name: "runDate", type: "STRING" },
        { name: "runTime", type: "NUMERIC" },
        { name: "context", type: "STRING" },
        { name: "sensorType", type: "STRING" },
        { name: "sensorId", type: "NUMERIC" },
        { name: "axisIndex", type: "NUMERIC" },
        { name: "traceKey", type: "STRING" },
        { name: "timestamp", type: "NUMERIC" },
        { name: "readings", type: "NUMERIC" },
        { name: "labelId", type: "STRING" },
        { name: "labelText", type: "STRING" },
        { name: "labelKind", type: "STRING" },
        ...metadataKeys.map((key) => ({ name: key, type: "STRING" })),
        { name: "class", type: "STRING" },
      ];
    } else {
      attributes = [
        { name: "runId", type: "STRING" },
        { name: "runName", type: "STRING" },
        { name: "labelId", type: "STRING" },
        { name: "labelText", type: "STRING" },
        { name: "labelKind", type: "STRING" },
        { name: "traceKey", type: "STRING" },
        { name: "sensorId", type: "NUMERIC" },
        { name: "axisIndex", type: "NUMERIC" },
        { name: "readingCount", type: "NUMERIC" },
        { name: "duration", type: "NUMERIC" },
        ...metadataKeys.map((key) => ({ name: key, type: "STRING" })),
        ...Array.from({ length: resamplePoints }, (_, index) => ({
          name: `p${String(index + 1).padStart(3, "0")}`,
          type: "NUMERIC",
        })),
        { name: "class", type: "STRING" },
      ];

      dataRows = rows.map((row) => {
        const samples = resampleSeries(row.timestamps, row.values, resamplePoints);
        const sampleFields = Object.fromEntries(
          samples.map((value, index) => [
            `p${String(index + 1).padStart(3, "0")}`,
            value,
          ])
        );
        return {
          ...row,
          ...sampleFields,
        };
      });
      if (dataRows.length === 0) {
        return res.status(400).json({
          message: "Run labels were found, but no matching sensor reading rows could be resolved for export.",
        });
      }
    }

    const arff = buildArffDocument(
      `run_${runid}_${variant}`,
      attributes,
      dataRows
    );

    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader(
      "Content-Disposition",
      `attachment; filename="run-${runid}-${variant}.arff"`
    );
    return res.status(200).send(arff);
  } catch (error) {
    return res.status(500).json({
      message: "Failed to export ARFF.",
      error: error.message,
    });
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

runRouter.get("/:runid/trims", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }
    const trims = await runService.getRunTrims(runid);
    return res.json({ trims });
  } catch (error) {
    return res.status(500).json({ message: "Failed to fetch run trims.", error: error.message });
  }
});

runRouter.put("/:runid/trims", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) {
      return res.status(404).json({ message: "Run not found." });
    }
    const trims = normalizeRunTrims(req.body?.trims ?? []);
    const updatedTrims = await runService.updateRunTrims(runid, trims);
    return res.json({ trims: updatedTrims });
  } catch (error) {
    return res.status(400).json({ message: "Failed to update run trims.", error: error.message });
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
    await runService.deleteRunTrims(runid);
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
      sensorName,
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
          "Invalid sensorType. Supported values: accelerometer, gyroscope, strainGauge, gps.",
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

    const resolvedSensorName = String(sensorName || "").trim();
    const runSensorsColl = await getCollection(db, "run_sensors");

    let resolvedSensorId;
    if (sensorId !== undefined && sensorId !== null && String(sensorId).trim() !== "") {
      // Explicit sensorId provided (e.g. from hub or API client).
      resolvedSensorId = parseInteger(sensorId, null);
      if (resolvedSensorId === null) {
        return res.status(400).json({ message: "Invalid sensorId." });
      }
    } else if (resolvedSensorName) {
      // Look up whether a sensor with this name already exists in the run.
      const existingRunSensor = await runSensorsColl.findOne({
        runId: resolvedRunId,
        name: resolvedSensorName,
      });
      if (existingRunSensor) {
        resolvedSensorId = existingRunSensor.sensorId;
      } else {
        // Auto-assign: prefer the type-default ID if unused, otherwise max + 1.
        const defaultSensorId = SENSOR_TYPE_TO_ID[resolvedSensorType];
        const existingRunSensors = await runSensorsColl.find({ runId: resolvedRunId }).toArray();
        const usedIds = existingRunSensors.map((s) => s.sensorId);
        if (!usedIds.includes(defaultSensorId)) {
          resolvedSensorId = defaultSensorId;
        } else {
          resolvedSensorId = usedIds.length > 0 ? Math.max(...usedIds) + 1 : defaultSensorId;
        }
      }
    } else {
      // No name and no explicit ID: fall back to the type-default.
      resolvedSensorId = SENSOR_TYPE_TO_ID[resolvedSensorType];
    }

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

    const runSensorUpdate = { sensorType: resolvedSensorType };
    if (resolvedSensorName) {
      runSensorUpdate.name = resolvedSensorName;
    }
    await runSensorsColl.updateOne(
      { runId: resolvedRunId, sensorId: resolvedSensorId },
      { $set: runSensorUpdate },
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
    const { filters, start, end, resolution, mode, residual } = req.query;
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
      residual,
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
