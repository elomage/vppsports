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
    binaryAxes: ["x", "y", "z"],
  },
  gyroscope: {
    recordSizeBytes: 16,
    dataAxis: 3,
    binaryAxes: ["x", "y", "z"],
  },
  strainGauge: {
    recordSizeBytes: 36,
    dataAxis: 8,
    binaryAxes: ["ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8"],
  },
  gps: {
    recordSizeBytes: 16,
    dataAxis: 3,
    binaryAxes: ["x", "y", "z"],
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

const CSV_SEGMENT_ALIASES = new Set(["segment", "label", "annotation"]);

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

// ── CSV helpers ──────────────────────────────────────────────────────────────

const csvEscape = (value) => {
  if (value === null || value === undefined) return "";
  const s = String(value);
  // Wrap in quotes if the value contains a comma, double-quote, or newline.
  if (s.includes(",") || s.includes('"') || s.includes("\n") || s.includes("\r")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
};

const buildCsvLine = (values) => values.map(csvEscape).join(",");

// Axis column names: x/y/z for the first three, then numeric for the rest.
const axisColumnName = (index) => {
  if (index === 0) return "value_x";
  if (index === 1) return "value_y";
  if (index === 2) return "value_z";
  return `value_${index}`;
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

// ─── Wide feature-matrix export helpers ──────────────────────────────────────

const abbreviateSensorType = (sensorType) => {
  const map = {
    accelerometer: "acc",
    gyroscope: "gyro",
    magnetometer: "mag",
    straingauge: "strain",
    gps: "gps",
  };
  const key = String(sensorType || "").toLowerCase();
  return (
    map[key] ||
    key.replace(/[^a-z0-9]/g, "").slice(0, 8) ||
    "sensor"
  );
};

const traceAxisLabel = (axisIndex) =>
  ["x", "y", "z"][axisIndex] ?? `v${axisIndex + 1}`;

const traceColumnPrefix = (sensorType, sensorId, axisIndex) =>
  `${abbreviateSensorType(sensorType)}_${sensorId}_${traceAxisLabel(axisIndex)}`;

const WIDE_STAT_KEYS = [
  "firstValue", "lastValue", "maxValue", "meanValue",
  "minValue", "peakValue", "rangeValue", "rmsValue", "stdValue",
];

/**
 * Produces one wide row per labeled event.
 *
 * Columns:
 *   - Event metadata (labelInstanceId, runId, labelText, duration, …)
 *   - Per-trace statistics: {sensorAbbr}_{sensorId}_{axis}_{stat}
 *       e.g. acc_3_x_meanValue, gyro_2_z_rmsValue
 */
const collectWideRows = (runDocument, sensorReadings) => {
  const runId = String(runDocument._id);
  const traceSeriesMap = buildTraceSeriesMap(runId, sensorReadings);

  const sensorTypeBySensorId = new Map();
  sensorReadings.forEach((reading) => {
    const sensorType =
      reading?.sensorType || reading?.sensorDetails?.[0]?.type || "";
    if (reading?.sensorId !== undefined && sensorType) {
      sensorTypeBySensorId.set(Number(reading.sensorId), String(sensorType));
    }
  });

  // Compute run temporal extent from all sensor readings (avoid spread to prevent stack overflow).
  let runFirstTs = Infinity;
  let runLastTs = -Infinity;
  for (const reading of sensorReadings) {
    if (Array.isArray(reading?.timestamps)) {
      for (const ts of reading.timestamps) {
        if (ts < runFirstTs) runFirstTs = ts;
        if (ts > runLastTs) runLastTs = ts;
      }
    } else if (reading?.timestamp != null) {
      const ts = Number(reading.timestamp);
      if (ts < runFirstTs) runFirstTs = ts;
      if (ts > runLastTs) runLastTs = ts;
    }
  }
  const runTsDuration =
    Number.isFinite(runFirstTs) && Number.isFinite(runLastTs) && runLastTs > runFirstTs
      ? runLastTs - runFirstTs
      : null;

  const metadata = flattenMetadata(runDocument.metadata);
  const labels = Array.isArray(runDocument.labels) ? runDocument.labels : [];

  return labels
    .map((label) => {
      const labelTraceKeys = Array.isArray(label.traceKeys) ? label.traceKeys : [];
      const effectiveTraceKeys = labelTraceKeys.length > 0 ? labelTraceKeys : [...traceSeriesMap.keys()];

      const traces = effectiveTraceKeys
        .map((traceKey) => {
          const traceInfo =
            traceSeriesMap.get(traceKey) ||
            traceSeriesMap.get(toRawTraceKey(traceKey));
          if (!traceInfo) return null;

          const parsed = parseTraceKey(traceKey);
          const sensorType =
            sensorTypeBySensorId.get(Number(parsed.sensorId)) || "";

          const timestamps = [];
          const values = [];
          for (let i = 0; i < traceInfo.timestamps.length; i++) {
            const ts = traceInfo.timestamps[i];
            if (ts >= label.startTimestamp && ts <= label.endTimestamp) {
              timestamps.push(ts);
              values.push(traceInfo.values[i]);
            }
          }
          if (timestamps.length === 0) return null;

          return {
            traceKey,
            prefix: traceColumnPrefix(sensorType, parsed.sensorId, parsed.axisIndex),
            sensorId: Number(parsed.sensorId),
            axisIndex: Number(parsed.axisIndex),
            sensorType,
            timestamps,
            values,
          };
        })
        .filter(Boolean);

      if (traces.length === 0) return null;

      const featureColumns = {};

      // ── Per-trace statistics, combined across sensors of the same type ──
      // Group by (sensorType, axisIndex) so acc_1 and acc_3 merge into acc_x.
      const typeAxisMap = new Map();
      for (const trace of traces) {
        const groupKey = `${trace.sensorType}__${trace.axisIndex}`;
        if (!typeAxisMap.has(groupKey)) {
          typeAxisMap.set(groupKey, {
            sensorType: trace.sensorType,
            axisIndex: trace.axisIndex,
            values: [],
          });
        }
        const group = typeAxisMap.get(groupKey);
        for (const v of trace.values) group.values.push(v);
      }

      for (const { sensorType, axisIndex, values } of typeAxisMap.values()) {
        const colPrefix = `${abbreviateSensorType(sensorType)}_${traceAxisLabel(axisIndex)}`;
        const stats = computeStats(values);
        for (const key of WIDE_STAT_KEYS) {
          featureColumns[`${colPrefix}_${key}`] = stats[key] ?? null;
        }
      }

      const startTs = Number(label.startTimestamp);
      const endTs = Number(label.endTimestamp);
      const duration = endTs - startTs;

      const temporalFeatures = {};
      if (runTsDuration !== null) {
        temporalFeatures.run_sensor_duration = runTsDuration;
        temporalFeatures.event_start_ratio =
          (startTs - runFirstTs) / runTsDuration;
        temporalFeatures.event_end_ratio =
          (endTs - runFirstTs) / runTsDuration;
        temporalFeatures.event_mid_ratio =
          ((startTs + endTs) / 2 - runFirstTs) / runTsDuration;
        temporalFeatures.event_duration_ratio = duration / runTsDuration;
      } else {
        temporalFeatures.run_sensor_duration = null;
        temporalFeatures.event_start_ratio = null;
        temporalFeatures.event_end_ratio = null;
        temporalFeatures.event_mid_ratio = null;
        temporalFeatures.event_duration_ratio = null;
      }

      return {
        labelInstanceId: label.id,
        runId,
        runName: runDocument.name || `Run ${runId}`,
        runDate: runDocument.date
          ? new Date(runDocument.date).toISOString()
          : "",
        context: runDocument.context || "",
        labelText: label.text || "",
        labelKind: label.kind,
        duration,
        startTimestamp: startTs,
        endTimestamp: endTs,
        ...temporalFeatures,
        class: normalizeClassValue(label),
        ...metadata,
        ...featureColumns,
      };
    })
    .filter(Boolean);
};

/**
 * Formats a numeric boundary value for use in a bin label.
 * Uses up to 4 significant figures, strips trailing zeros.
 * e.g. 0.33333 → "0.3333", 1500 → "1500", 0.1 → "0.1"
 */
const formatBinBound = (value) => String(parseFloat(value.toPrecision(4)));

/**
 * Discretizes numeric columns in a set of wide rows into equal-width bins.
 *
 * Each bin is labelled with the actual value range it covers, e.g.
 * "0_to_0.3333", "0.3333_to_0.6667", "0.6667_to_1" — so the ARFF nominal
 * declaration documents the real data scale rather than generic low/medium/high.
 *
 * - numericKeys: column names that hold numeric values.
 * - numBins: number of bins (default 3).
 * - Boundaries are computed from the global min/max across ALL rows for each
 *   column, so multi-run exports share a consistent scale.
 * - Null/non-finite values remain null and become "?" in the ARFF output.
 *
 * Returns:
 *   discretized    – rows with bin-label strings replacing raw numbers
 *   colNominalTypes – Map<key, arffTypeString> giving each column's
 *                    ARFF declaration, e.g. "{'0_to_1','1_to_2','2_to_3'}"
 */
const DEFAULT_APRIORI_BINS = 3;

const discretizeRows = (rows, numericKeys, numBins = DEFAULT_APRIORI_BINS) => {
  // ── Step 1: compute per-column min/max ──────────────────────────────────
  const colStats = new Map();
  for (const key of numericKeys) {
    let min = Infinity;
    let max = -Infinity;
    for (const row of rows) {
      const v = Number(row[key]);
      if (Number.isFinite(v)) {
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
    colStats.set(key, { min, max });
  }

  // ── Step 2: build per-column bin labels and ARFF type strings ───────────
  // Bin label format: "<lowerBound>_to_<upperBound>" using the actual data
  // values as boundaries.  Values are single-quoted in the ARFF declaration
  // so that periods and underscores are not misinterpreted by parsers.
  const colBinLabels = new Map(); // key → string[]
  const colNominalTypes = new Map(); // key → ARFF type string

  for (const key of numericKeys) {
    const { min, max } = colStats.get(key);

    if (!Number.isFinite(min)) {
      // No finite values in this column — leave as missing.
      colBinLabels.set(key, []);
      colNominalTypes.set(key, "STRING");
      continue;
    }

    const labels = [];
    if (min === max) {
      // Constant feature: a single bin whose lower and upper bound are equal.
      const label = `${formatBinBound(min)}_to_${formatBinBound(max)}`;
      labels.push(label);
    } else {
      const step = (max - min) / numBins;
      for (let i = 0; i < numBins; i++) {
        const lo = min + i * step;
        const hi = i === numBins - 1 ? max : min + (i + 1) * step;
        labels.push(`${formatBinBound(lo)}_to_${formatBinBound(hi)}`);
      }
    }

    colBinLabels.set(key, labels);
    // Quote each value so ARFF parsers handle periods/underscores safely.
    colNominalTypes.set(
      key,
      `{${labels.map((l) => `'${l}'`).join(",")}}`
    );
  }

  // ── Step 3: replace numeric values with their bin labels ─────────────────
  const discretized = rows.map((row) => {
    const newRow = { ...row };
    for (const key of numericKeys) {
      const raw = row[key];
      if (raw === null || raw === undefined || !Number.isFinite(Number(raw))) {
        newRow[key] = null;
        continue;
      }
      const { min, max } = colStats.get(key);
      const labels = colBinLabels.get(key);
      if (!labels || labels.length === 0) {
        newRow[key] = null;
        continue;
      }
      if (min === max) {
        newRow[key] = labels[0];
        continue;
      }
      const n = Number(raw);
      let idx = Math.floor(((n - min) / (max - min)) * numBins);
      if (idx >= numBins) idx = numBins - 1; // clamp max value to last bin
      newRow[key] = labels[idx];
    }
    return newRow;
  });

  return { discretized, colNominalTypes };
};

// ── Association rule mining (Apriori) ────────────────────────────────────────

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

  if (lines.length < 1) {
    throw new Error("CSV upload requires at least one data row.");
  }

  // Detect headerless CSV: every cell in the first line parses as a finite number.
  const firstCells = parseCsvLine(lines[0]);
  const isHeaderless =
    firstCells.length > 0 &&
    firstCells.every((c) => c.trim() !== "" && Number.isFinite(Number(c.trim())));

  let headerCells, originalHeaderCells, dataLines;

  if (isHeaderless) {
    if (firstCells.length < 2) {
      throw new Error(
        "Headerless CSV must have at least 2 columns (timestamp + one value column)."
      );
    }
    // First column \u2192 "timestamp"; remaining \u2192 "col1", "col2", \u2026
    headerCells = ["timestamp", ...firstCells.slice(1).map((_, i) => `col${i + 1}`)];
    originalHeaderCells = [...headerCells];
    dataLines = lines;
  } else {
    if (lines.length < 2) {
      throw new Error("CSV upload requires a header row and at least one data row.");
    }
    const rawHeaderCells = parseCsvLine(lines[0]);
    headerCells = rawHeaderCells.map(normalizeCsvHeader);
    originalHeaderCells = rawHeaderCells.map((h) => String(h || "").trim());

    if (headerCells.length === 0 || headerCells.every((cell) => !cell)) {
      throw new Error("CSV header row is empty.");
    }
    dataLines = lines.slice(1);
  }

  const rows = dataLines.map((line, index) => {
    const cells = parseCsvLine(line);
    const row = {};
    headerCells.forEach((header, cellIndex) => {
      if (header) {
        row[header] = cells[cellIndex] ?? "";
      }
    });
    row.__rowNumber = isHeaderless ? index + 1 : index + 2;
    return row;
  });

  return { headerCells, originalHeaderCells, rows };
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

const buildCsvSensorReadings = (csvText) => {
  const { headerCells, originalHeaderCells, rows } = parseCsvRows(csvText);
  const timestampSet = new Set(CSV_TIMESTAMP_ALIASES);

  const segmentNormalized = headerCells.find((h) => CSV_SEGMENT_ALIASES.has(h)) || null;

  const valueColumns = [];
  headerCells.forEach((normalized, i) => {
    if (normalized && !timestampSet.has(normalized) && normalized !== segmentNormalized) {
      valueColumns.push({ normalized, label: originalHeaderCells[i] || normalized });
    }
  });

  if (valueColumns.length === 0) {
    throw new Error(
      "CSV must contain at least one value column in addition to the timestamp column."
    );
  }

  const pairs = rows.map((row) => {
    const rowNumber = row.__rowNumber;
    const timestamp = parseCsvTimestamp(row, rowNumber);
    const data = valueColumns.map(({ normalized, label }) => {
      const rawValue = row[normalized];
      if (rawValue === undefined || rawValue === null || rawValue === "") {
        throw new Error(`CSV row ${rowNumber} is missing a value for column "${label}".`);
      }
      const parsed = Number(rawValue);
      if (!Number.isFinite(parsed)) {
        throw new Error(`CSV row ${rowNumber} has non-numeric value for column "${label}": ${rawValue}`);
      }
      return parsed;
    });
    const segment = segmentNormalized ? String(row[segmentNormalized] || "").trim() : "";
    return { timestamp, data, segment };
  });

  pairs.sort((a, b) => a.timestamp - b.timestamp);

  const axes = valueColumns.map(({ label }) => label);
  return {
    readings: pairs.map(({ timestamp, data }) => ({ timestamp, data })),
    axes,
    segments: pairs.map(({ segment }) => segment),
  };
};

const LABEL_IMPORT_COLORS = ["#0d6efd", "#dc3545", "#198754", "#ffc107", "#0dcaf0", "#fd7e14", "#6f42c1", "#20c997"];

const hashSegmentColor = (text) => {
  let h = 0;
  for (const ch of text) h = ((h * 31) + ch.charCodeAt(0)) & 0xffffffff;
  return LABEL_IMPORT_COLORS[Math.abs(h) % LABEL_IMPORT_COLORS.length];
};

const inferLabelsFromSegments = (readings, segments, runId, sensorId) => {
  const labels = [];
  let i = 0;
  while (i < segments.length) {
    const text = segments[i];
    if (!text) { i++; continue; }
    let j = i + 1;
    while (j < segments.length && segments[j] === text) j++;
    const startTs = readings[i].timestamp;
    const endTs = readings[j - 1].timestamp;
    const color = hashSegmentColor(text);
    const id = `label-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    const traceKey = `${runId}:${sensorId}:0:raw`;
    if (j - i === 1) {
      labels.push({
        id,
        kind: "single",
        text,
        color,
        traceKeys: [traceKey],
        points: [{ traceKey, timestamp: startTs, yValue: 0 }],
        startTimestamp: startTs,
        endTimestamp: startTs,
        anchorTimestamp: startTs,
        anchorY: 0,
        dx: 0,
        dy: 0,
      });
    } else {
      labels.push({
        id,
        kind: "range",
        text,
        color,
        traceKeys: [traceKey],
        points: [],
        startTimestamp: startTs,
        endTimestamp: endTs,
        anchorTimestamp: startTs,
        anchorY: 0,
        dx: 0,
        dy: 0,
      });
    }
    i = j;
  }
  return labels;
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
    if (!["features", "resampled", "wide", "apriori"].includes(variant)) {
      return res.status(400).json({
        message: "Invalid variant. Supported values: features, resampled, wide, apriori.",
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

    let attributes;
    let dataRows;

    if (variant === "wide" || variant === "apriori") {
      // ── Wide feature matrix: one row per labeled event ───────────────────
      const wideRows = collectWideRows(runDocument, sensorReadings);

      if (wideRows.length === 0) {
        return res.status(400).json({
          message: "Run has no labeled trace data to export.",
        });
      }

      // Discover the union of all column keys across every row so that rows
      // with missing sensors get ARFF "?" rather than being dropped.
      const META_KEYS = new Set([
        "labelInstanceId", "runId", "runName", "runDate", "context",
        "labelText", "labelKind", "duration", "startTimestamp", "endTimestamp",
        "run_sensor_duration", "event_start_ratio", "event_end_ratio",
        "event_mid_ratio", "event_duration_ratio",
        "class",
      ]);
      const metadataKeys = [
        ...new Set(
          wideRows.flatMap((row) =>
            Object.keys(row).filter((k) => k.startsWith("meta_"))
          )
        ),
      ].sort();
      const featureKeys = [
        ...new Set(
          wideRows.flatMap((row) =>
            Object.keys(row).filter(
              (k) => !META_KEYS.has(k) && !k.startsWith("meta_")
            )
          )
        ),
      ].sort();

      if (variant === "wide") {
        dataRows = wideRows;
        attributes = [
          { name: "labelInstanceId",       type: "STRING" },
          { name: "runId",                 type: "STRING" },
          { name: "runName",               type: "STRING" },
          { name: "runDate",               type: "STRING" },
          { name: "context",               type: "STRING" },
          { name: "labelText",             type: "STRING" },
          { name: "labelKind",             type: "STRING" },
          { name: "duration",              type: "NUMERIC" },
          { name: "startTimestamp",        type: "NUMERIC" },
          { name: "endTimestamp",          type: "NUMERIC" },
          { name: "run_sensor_duration",   type: "NUMERIC" },
          { name: "event_start_ratio",     type: "NUMERIC" },
          { name: "event_end_ratio",       type: "NUMERIC" },
          { name: "event_mid_ratio",       type: "NUMERIC" },
          { name: "event_duration_ratio",  type: "NUMERIC" },
          ...metadataKeys.map((k) => ({ name: k, type: "STRING" })),
          ...featureKeys.map((k)  => ({ name: k, type: "NUMERIC" })),
          { name: "class", type: "STRING" },
        ];
      } else {
        // ── Apriori: discretize all numeric columns into equal-width bins ───
        // Keys to discretize = numeric META_KEYS + all feature keys.
        const numericMetaKeys = [
          "duration", "startTimestamp", "endTimestamp",
          "run_sensor_duration", "event_start_ratio", "event_end_ratio",
          "event_mid_ratio", "event_duration_ratio",
        ];
        const numericKeys = [...numericMetaKeys, ...featureKeys];
        const { discretized, colNominalTypes } = discretizeRows(wideRows, numericKeys);
        dataRows = discretized;

        // Enumerate class values so Weka treats the attribute as nominal,
        // not as free-form STRING (Apriori ignores STRING attributes).
        const classValues = [
          ...new Set(dataRows.map((r) => r.class).filter(Boolean)),
        ].sort();
        const classNominalType = classValues.length > 0
          ? `{${classValues.map((v) => `'${v}'`).join(",")}}`
          : "STRING";

        const colType = (k) => colNominalTypes.get(k) || "STRING";
        attributes = [
          { name: "labelInstanceId",       type: "STRING" },
          { name: "runId",                 type: "STRING" },
          { name: "runName",               type: "STRING" },
          { name: "runDate",               type: "STRING" },
          { name: "context",               type: "STRING" },
          { name: "labelText",             type: "STRING" },
          { name: "labelKind",             type: "STRING" },
          { name: "duration",              type: colType("duration") },
          { name: "startTimestamp",        type: colType("startTimestamp") },
          { name: "endTimestamp",          type: colType("endTimestamp") },
          { name: "run_sensor_duration",   type: colType("run_sensor_duration") },
          { name: "event_start_ratio",     type: colType("event_start_ratio") },
          { name: "event_end_ratio",       type: colType("event_end_ratio") },
          { name: "event_mid_ratio",       type: colType("event_mid_ratio") },
          { name: "event_duration_ratio",  type: colType("event_duration_ratio") },
          ...metadataKeys.map((k) => ({ name: k, type: "STRING" })),
          ...featureKeys.map((k)  => ({ name: k, type: colType(k) })),
          { name: "class", type: classNominalType },
        ];
      }
    } else {
      // ── Features / resampled variants (trace-centric) ────────────────────
      const rows = collectLabelTraceRows(runDocument, sensorReadings);

      if (rows.length === 0) {
        return res.status(400).json({
          message: "Run has no labeled trace data to export.",
        });
      }

      const metadataKeys = [
        ...new Set(
          rows.flatMap((row) =>
            Object.keys(row).filter((key) => key.startsWith("meta_"))
          )
        ),
      ].sort();

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
          { name: "runId",      type: "STRING" },
          { name: "runName",    type: "STRING" },
          { name: "runDate",    type: "STRING" },
          { name: "runTime",    type: "NUMERIC" },
          { name: "context",    type: "STRING" },
          { name: "sensorType", type: "STRING" },
          { name: "sensorId",   type: "NUMERIC" },
          { name: "axisIndex",  type: "NUMERIC" },
          { name: "traceKey",   type: "STRING" },
          { name: "timestamp",  type: "NUMERIC" },
          { name: "readings",   type: "NUMERIC" },
          { name: "labelId",    type: "STRING" },
          { name: "labelText",  type: "STRING" },
          { name: "labelKind",  type: "STRING" },
          ...metadataKeys.map((key) => ({ name: key, type: "STRING" })),
          { name: "class", type: "STRING" },
        ];
      } else {
        // resampled
        attributes = [
          { name: "runId",        type: "STRING" },
          { name: "runName",      type: "STRING" },
          { name: "labelId",      type: "STRING" },
          { name: "labelText",    type: "STRING" },
          { name: "labelKind",    type: "STRING" },
          { name: "traceKey",     type: "STRING" },
          { name: "sensorId",     type: "NUMERIC" },
          { name: "axisIndex",    type: "NUMERIC" },
          { name: "readingCount", type: "NUMERIC" },
          { name: "duration",     type: "NUMERIC" },
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
          return { ...row, ...sampleFields };
        });
        if (dataRows.length === 0) {
          return res.status(400).json({
            message: "Run labels were found, but no matching sensor reading rows could be resolved for export.",
          });
        }
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

runRouter.post("/export/multi-arff", async (req, res) => {
  try {
    const { runIds, variant: rawVariant } = req.body || {};
    const variant = String(rawVariant || "wide").trim().toLowerCase();

    if (!["wide", "apriori"].includes(variant)) {
      return res.status(400).json({
        message: "Invalid variant. Supported values: wide, apriori.",
      });
    }

    if (!Array.isArray(runIds) || runIds.length === 0) {
      return res.status(400).json({ message: "Provide a non-empty runIds array." });
    }

    // De-duplicate and validate
    const uniqueRunIds = [...new Set(runIds.map(String))];
    if (uniqueRunIds.length > 50) {
      return res.status(400).json({ message: "At most 50 runs can be exported at once." });
    }

    // Authorize each run and collect data
    const allRows = [];
    const errors = [];

    for (const runId of uniqueRunIds) {
      let authorizedRun;
      try {
        authorizedRun = await findRunForUser(runId, req.user);
      } catch (_e) {
        authorizedRun = null;
      }

      if (!authorizedRun) {
        errors.push(`Run ${runId} not found or not accessible.`);
        continue;
      }

      try {
        const [runDocument, sensorReadings] = await Promise.all([
          runService.getSingleRunDB(runId),
          runService.getRunSensorReadingsAll(runId),
        ]);
        const rows = collectWideRows(runDocument, sensorReadings);
        allRows.push(...rows);
      } catch (err) {
        errors.push(`Run ${runId}: ${err.message}`);
      }
    }

    if (allRows.length === 0) {
      return res.status(400).json({
        message: "No labeled trace data found across the selected runs.",
        errors,
      });
    }

    const MULTI_META_KEYS = new Set([
      "labelInstanceId", "runId", "runName", "runDate", "context",
      "labelText", "labelKind", "duration", "startTimestamp", "endTimestamp",
      "run_sensor_duration", "event_start_ratio", "event_end_ratio",
      "event_mid_ratio", "event_duration_ratio",
      "class",
    ]);
    const metadataKeys = [
      ...new Set(
        allRows.flatMap((row) =>
          Object.keys(row).filter((k) => k.startsWith("meta_"))
        )
      ),
    ].sort();
    const featureKeys = [
      ...new Set(
        allRows.flatMap((row) =>
          Object.keys(row).filter(
            (k) => !MULTI_META_KEYS.has(k) && !k.startsWith("meta_")
          )
        )
      ),
    ].sort();

    let exportRows;
    let attributes;

    if (variant === "apriori") {
      const numericMetaKeys = [
        "duration", "startTimestamp", "endTimestamp",
        "run_sensor_duration", "event_start_ratio", "event_end_ratio",
        "event_mid_ratio", "event_duration_ratio",
      ];
      const numericKeys = [...numericMetaKeys, ...featureKeys];
      const { discretized, colNominalTypes } = discretizeRows(allRows, numericKeys);
      exportRows = discretized;

      const classValues = [
        ...new Set(exportRows.map((r) => r.class).filter(Boolean)),
      ].sort();
      const classNominalType = classValues.length > 0
        ? `{${classValues.map((v) => `'${v}'`).join(",")}}`
        : "STRING";

      const colType = (k) => colNominalTypes.get(k) || "STRING";
      attributes = [
        { name: "labelInstanceId",       type: "STRING" },
        { name: "runId",                 type: "STRING" },
        { name: "runName",               type: "STRING" },
        { name: "runDate",               type: "STRING" },
        { name: "context",               type: "STRING" },
        { name: "labelText",             type: "STRING" },
        { name: "labelKind",             type: "STRING" },
        { name: "duration",              type: colType("duration") },
        { name: "startTimestamp",        type: colType("startTimestamp") },
        { name: "endTimestamp",          type: colType("endTimestamp") },
        { name: "run_sensor_duration",   type: colType("run_sensor_duration") },
        { name: "event_start_ratio",     type: colType("event_start_ratio") },
        { name: "event_end_ratio",       type: colType("event_end_ratio") },
        { name: "event_mid_ratio",       type: colType("event_mid_ratio") },
        { name: "event_duration_ratio",  type: colType("event_duration_ratio") },
        ...metadataKeys.map((k) => ({ name: k, type: "STRING" })),
        ...featureKeys.map((k)  => ({ name: k, type: colType(k) })),
        { name: "class", type: classNominalType },
      ];
    } else {
      exportRows = allRows;
      attributes = [
        { name: "labelInstanceId",       type: "STRING" },
        { name: "runId",                 type: "STRING" },
        { name: "runName",               type: "STRING" },
        { name: "runDate",               type: "STRING" },
        { name: "context",               type: "STRING" },
        { name: "labelText",             type: "STRING" },
        { name: "labelKind",             type: "STRING" },
        { name: "duration",              type: "NUMERIC" },
        { name: "startTimestamp",        type: "NUMERIC" },
        { name: "endTimestamp",          type: "NUMERIC" },
        { name: "run_sensor_duration",   type: "NUMERIC" },
        { name: "event_start_ratio",     type: "NUMERIC" },
        { name: "event_end_ratio",       type: "NUMERIC" },
        { name: "event_mid_ratio",       type: "NUMERIC" },
        { name: "event_duration_ratio",  type: "NUMERIC" },
        ...metadataKeys.map((k) => ({ name: k, type: "STRING" })),
        ...featureKeys.map((k)  => ({ name: k, type: "NUMERIC" })),
        { name: "class", type: "STRING" },
      ];
    }

    const arff = buildArffDocument(`multi_run_${variant}`, attributes, exportRows);
    const timestamp = new Date().toISOString().slice(0, 10);

    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader(
      "Content-Disposition",
      `attachment; filename="multi-run-${variant}-${timestamp}.arff"`
    );
    return res.status(200).send(arff);
  } catch (error) {
    return res.status(500).json({
      message: "Failed to export multi-run ARFF.",
      error: error.message,
    });
  }
});

runRouter.post("/export/apriori-csv", async (req, res) => {
  try {
    const { runIds, numBins: rawNumBins } = req.body || {};
    const numBins = Math.max(2, Math.min(20, parseInt(rawNumBins, 10) || DEFAULT_APRIORI_BINS));

    if (!Array.isArray(runIds) || runIds.length === 0) {
      return res.status(400).json({ message: "Provide a non-empty runIds array." });
    }

    const uniqueRunIds = [...new Set(runIds.map(String))];
    if (uniqueRunIds.length > 50) {
      return res.status(400).json({ message: "At most 50 runs can be exported at once." });
    }

    const allRows = [];
    const db = await connectDB();
    const aprioriViewStatesColl = await getCollection(db, "run_view_states");

    for (const runId of uniqueRunIds) {
      let authorizedRun;
      try {
        authorizedRun = await findRunForUser(runId, req.user);
      } catch (_e) {
        authorizedRun = null;
      }
      if (!authorizedRun) continue;

      try {
        const viewStateDoc = await aprioriViewStatesColl.findOne({ runId });
        const charts = Array.isArray(viewStateDoc?.charts) ? viewStateDoc.charts : [];

        const mergedSensorKeys = new Set();
        const mergedFilterPipelines = {};
        const mergedFiltersActive = {};

        for (const chartState of charts) {
          if (!chartState) continue;
          for (const key of (chartState.selectedSensorKeys || [])) {
            if (!key.startsWith(`${runId}:`)) continue;
            mergedSensorKeys.add(key);
            if (mergedFilterPipelines[key] === undefined && chartState.sensorFilterPipelines?.[key]) {
              mergedFilterPipelines[key] = chartState.sensorFilterPipelines[key];
            }
            if (mergedFiltersActive[key] === undefined && chartState.sensorFiltersActive?.[key] !== undefined) {
              mergedFiltersActive[key] = chartState.sensorFiltersActive[key];
            }
          }
        }

        const runDocument = await runService.getSingleRunDB(runId);
        const allSensors = await runService.getRunSensors(runId);

        let sensorsToExport;
        if (mergedSensorKeys.size > 0) {
          const selectedIds = new Set([...mergedSensorKeys].map((k) => String(k.slice(runId.length + 1))));
          sensorsToExport = allSensors.filter((s) => selectedIds.has(String(s.sensorId)));
        } else {
          sensorsToExport = allSensors;
        }

        const sensorReadings = [];
        for (const sensor of sensorsToExport) {
          const sensorKey = `${runId}:${sensor.sensorId}`;
          const pipeline = mergedFilterPipelines[sensorKey] || [];
          const isActive = !!(mergedFiltersActive[sensorKey] && pipeline.length > 0);
          const filterKey = isActive
            ? JSON.stringify(pipeline.map(({ type, params }) => ({ type, params })))
            : undefined;
          const readings = await runController.getRunSensorData(runId, sensor.sensorId, { filters: filterKey });
          if (Array.isArray(readings)) {
            for (const r of readings) {
              sensorReadings.push({ ...r, sensorId: sensor.sensorId, sensorType: sensor.sensorType });
            }
          }
        }

        allRows.push(...collectWideRows(runDocument, sensorReadings));
      } catch (_err) {
        // skip inaccessible runs
      }
    }

    if (allRows.length === 0) {
      return res.status(400).json({
        message: "No labeled trace data found across the selected runs.",
      });
    }

    // Keys excluded from the output entirely.
    const EXCLUDED_KEYS = new Set([
      "labelInstanceId", "runId",
      "labelText", "labelKind",
      "startTimestamp", "endTimestamp",
      "run_sensor_duration", "event_start_ratio", "event_end_ratio",
      "event_mid_ratio", "event_duration_ratio",
    ]);
    // String columns kept in the output but not discretized.
    const STRING_KEYS = new Set(["runName", "runDate", "context", "class"]);

    const metadataKeys = [
      ...new Set(allRows.flatMap((r) => Object.keys(r).filter((k) => k.startsWith("meta_")))),
    ].sort();
    const featureKeys = [
      ...new Set(
        allRows.flatMap((r) =>
          Object.keys(r).filter(
            (k) => !EXCLUDED_KEYS.has(k) && !STRING_KEYS.has(k) && k !== "duration" && !k.startsWith("meta_")
          )
        )
      ),
    ].sort();

    const numericKeys = ["duration", ...featureKeys];
    const { discretized } = discretizeRows(allRows, numericKeys, numBins);

    const columnOrder = [
      "runName", "runDate", "context",
      "duration",
      ...metadataKeys,
      ...featureKeys,
      "class",
    ];

    const lines = [buildCsvLine(columnOrder)];
    for (const row of discretized) {
      lines.push(
        buildCsvLine(
          columnOrder.map((k) => {
            let v = row[k];
            // Trim ISO timestamp to plain date so Weka doesn't mis-detect as datetime.
            if (k === "runDate" && v) v = String(v).slice(0, 10);
            // Weka requires "?" for missing values, not empty string.
            return v !== null && v !== undefined && v !== "" ? v : "?";
          })
        )
      );
    }

    const dateStamp = new Date().toISOString().slice(0, 10);
    res.setHeader("Content-Type", "text/csv; charset=utf-8");
    res.setHeader(
      "Content-Disposition",
      `attachment; filename="multi-run-apriori-${dateStamp}.csv"`
    );
    // Use CRLF line endings for Windows/Weka compatibility.
    return res.status(200).send(lines.join("\r\n"));
  } catch (error) {
    return res.status(500).json({
      message: "Failed to export Apriori CSV.",
      error: error.message,
    });
  }
});

const CSV_ALL_FIELDS = ["runId", "runName", "runDate", "context", "sensorId", "sensorType", "timestamp", "sensorValues", "labels", "labelStats"];

runRouter.post("/export/multi-csv", async (req, res) => {
  try {
    const { runIds, fields } = req.body || {};

    const enabledFields = new Set(
      Array.isArray(fields) && fields.length > 0
        ? fields.filter((f) => CSV_ALL_FIELDS.includes(f))
        : CSV_ALL_FIELDS
    );

    if (!Array.isArray(runIds) || runIds.length === 0) {
      return res.status(400).json({ message: "Provide a non-empty runIds array." });
    }

    const uniqueRunIds = [...new Set(runIds.map(String))];
    if (uniqueRunIds.length > 50) {
      return res.status(400).json({ message: "At most 50 runs can be exported at once." });
    }

    const db = await connectDB();
    const viewStatesColl = await getCollection(db, "run_view_states");

    const dataRows = [];
    const maxAxesByType = new Map();

    const findNearest = (sorted, targetOrigTs) => {
      let lo = 0, hi = sorted.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (Number(sorted[mid].timestamp) < targetOrigTs) lo = mid + 1;
        else hi = mid;
      }
      const candidates = [];
      if (lo < sorted.length) candidates.push(sorted[lo]);
      if (lo > 0) candidates.push(sorted[lo - 1]);
      if (!candidates.length) return null;
      const best = candidates.reduce((a, b) =>
        Math.abs(Number(a.timestamp) - targetOrigTs) <= Math.abs(Number(b.timestamp) - targetOrigTs) ? a : b
      );
      return Math.abs(Number(best.timestamp) - targetOrigTs) <= 200 ? best : null;
    };

    for (const runId of uniqueRunIds) {
      let authorizedRun;
      try {
        authorizedRun = await findRunForUser(runId, req.user);
      } catch (_e) {
        authorizedRun = null;
      }
      if (!authorizedRun) continue;

      // Load saved view state and merge sensor config across all chart slots.
      const viewStateDoc = await viewStatesColl.findOne({ runId });
      const charts = Array.isArray(viewStateDoc?.charts) ? viewStateDoc.charts : [];

      const mergedSensorKeys = new Set();
      const mergedFilterPipelines = {};
      const mergedFiltersActive = {};
      const mergedSyncOffsets = {};

      for (const chartState of charts) {
        if (!chartState) continue;
        for (const key of (chartState.selectedSensorKeys || [])) {
          // Only consider sensors that belong to this run (not comparison runs).
          if (!key.startsWith(`${runId}:`)) continue;
          mergedSensorKeys.add(key);
          if (mergedFilterPipelines[key] === undefined && chartState.sensorFilterPipelines?.[key]) {
            mergedFilterPipelines[key] = chartState.sensorFilterPipelines[key];
          }
          if (mergedFiltersActive[key] === undefined && chartState.sensorFiltersActive?.[key] !== undefined) {
            mergedFiltersActive[key] = chartState.sensorFiltersActive[key];
          }
          if (mergedSyncOffsets[key] === undefined && chartState.sensorSyncOffsets?.[key] !== undefined) {
            mergedSyncOffsets[key] = chartState.sensorSyncOffsets[key];
          }
        }
      }

      // Determine which sensors to export: saved selection or all available.
      const allSensors = await runService.getRunSensors(runId);
      let sensorsToExport;
      if (mergedSensorKeys.size > 0) {
        const selectedIds = new Set(
          [...mergedSensorKeys].map((k) => String(k.slice(runId.length + 1)))
        );
        sensorsToExport = allSensors.filter((s) => selectedIds.has(String(s.sensorId)));
      } else {
        sensorsToExport = allSensors;
      }

      const runDocument = await runService.getSingleRunDB(runId);
      const labels = Array.isArray(runDocument.labels) ? runDocument.labels : [];
      const rangeLabels = labels.filter((l) => l.kind === "range");
      const singleLabels = labels.filter((l) => l.kind === "single");

      const findLabel = (ts) => {
        for (const label of rangeLabels) {
          if (ts >= Number(label.startTimestamp) && ts <= Number(label.endTimestamp)) return label;
        }
        for (const label of singleLabels) {
          if (Array.isArray(label.points)) {
            for (const point of label.points) {
              if (Number(point.timestamp) === ts) return label;
            }
          }
        }
        return null;
      };

      const runIdStr = String(runDocument._id);
      const runName  = runDocument.name || runIdStr;
      const runDate  = runDocument.date ? new Date(runDocument.date).toISOString() : "";
      const context  = runDocument.context || "";

      // Fetch filtered data per sensor and build label stats.
      // getRunSensorData applies trims and filter pipeline internally.
      const sensorDataBySensorId = new Map();
      for (const sensor of sensorsToExport) {
        const sensorKey = `${runId}:${sensor.sensorId}`;
        const pipeline = mergedFilterPipelines[sensorKey] || [];
        const isActive = !!(mergedFiltersActive[sensorKey] && pipeline.length > 0);
        const filterKey = isActive
          ? JSON.stringify(pipeline.map(({ type, params }) => ({ type, params })))
          : undefined;

        try {
          const readings = await runController.getRunSensorData(runId, sensor.sensorId, {
            filters: filterKey,
          });
          sensorDataBySensorId.set(sensor.sensorId, { sensor, readings: Array.isArray(readings) ? readings : [] });
        } catch (_err) {
          // skip sensors that fail to load
        }
      }

      const typeGroups = new Map();
      for (const [sensorId, { sensor, readings }] of sensorDataBySensorId) {
        const sensorKey = `${runId}:${sensorId}`;
        const offset = Number.isFinite(mergedSyncOffsets[sensorKey]) ? mergedSyncOffsets[sensorKey] : 0;
        const type = sensor.sensorType || String(sensorId);
        const sorted = [...readings].sort((a, b) => Number(a.timestamp) - Number(b.timestamp));
        if (!typeGroups.has(type)) typeGroups.set(type, []);
        typeGroups.get(type).push({ sensorId, offset, sorted });
      }

      if (typeGroups.size === 0) continue;

      const [primaryType] = typeGroups.keys();
      const primaryEntry = typeGroups.get(primaryType)[0];

      const rangeLabelStats = new Map();
      if (enabledFields.has("labelStats") && rangeLabels.length > 0) {
        for (const [type, sensors] of typeGroups) {
          for (const label of rangeLabels) {
            const start = Number(label.startTimestamp);
            const end = Number(label.endTimestamp);
            const axisAccum = [];
            for (const { offset, sorted } of sensors) {
              for (const r of sorted) {
                const origTs = Number(r.timestamp);
                if (origTs < start || origTs > end) continue;
                (Array.isArray(r.data) ? r.data : []).forEach((v, ai) => {
                  const n = Number(v);
                  if (!Number.isFinite(n)) return;
                  if (!axisAccum[ai]) axisAccum[ai] = { sum: 0, sumSq: 0, count: 0, min: Infinity, max: -Infinity };
                  axisAccum[ai].sum += n;
                  axisAccum[ai].sumSq += n * n;
                  axisAccum[ai].count++;
                  if (n < axisAccum[ai].min) axisAccum[ai].min = n;
                  if (n > axisAccum[ai].max) axisAccum[ai].max = n;
                });
              }
            }
            if (!axisAccum.some(Boolean)) continue;
            const axisStats = axisAccum.map((acc) => {
              if (!acc || acc.count === 0) return { rms: null, std: null, p2p: null };
              const mean = acc.sum / acc.count;
              return {
                rms: Math.sqrt(acc.sumSq / acc.count),
                std: Math.sqrt(Math.max(0, acc.sumSq / acc.count - mean * mean)),
                p2p: acc.max - acc.min,
              };
            });
            if (!rangeLabelStats.has(label.id)) rangeLabelStats.set(label.id, new Map());
            rangeLabelStats.get(label.id).set(type, axisStats);
          }
        }
      }

      for (const primaryReading of primaryEntry.sorted) {
        const origTs = Number(primaryReading.timestamp);
        const shiftedTs = origTs + primaryEntry.offset;

        const valuesByType = new Map();
        for (const [type, sensors] of typeGroups) {
          const axisAccum = [];
          for (const { offset, sorted } of sensors) {
            const nearest = findNearest(sorted, shiftedTs - offset);
            if (!nearest) continue;
            (Array.isArray(nearest.data) ? nearest.data : []).forEach((v, ai) => {
              const n = Number(v);
              if (!Number.isFinite(n)) return;
              if (!axisAccum[ai]) axisAccum[ai] = { sum: 0, count: 0 };
              axisAccum[ai].sum += n;
              axisAccum[ai].count++;
            });
          }
          if (!axisAccum.some(Boolean)) continue;
          const averaged = axisAccum.map((acc) => (acc ? acc.sum / acc.count : null));
          if (averaged.length > (maxAxesByType.get(type) || 0)) maxAxesByType.set(type, averaged.length);
          valuesByType.set(type, averaged);
        }

        if (valuesByType.size === 0) continue;

        const label = findLabel(origTs);
        const statsByType = enabledFields.has("labelStats") && label?.kind === "range"
          ? (rangeLabelStats.get(label.id) || new Map())
          : new Map();

        dataRows.push({
          runId:     runIdStr,
          runName,
          runDate,
          context,
          timestamp: shiftedTs,
          valuesByType,
          labelId:   label?.id   || "",
          labelText: label?.text || "",
          labelKind: label?.kind || "",
          statsByType,
        });
      }
    }

    if (dataRows.length === 0) {
      return res.status(400).json({
        message: "No sensor data found for the selected runs after applying trims.",
      });
    }

    const axisLabel = (i) => (i === 0 ? "x" : i === 1 ? "y" : i === 2 ? "z" : String(i));
    const sortedTypes = [...maxAxesByType.keys()].sort();

    const sensorValueHeaders = enabledFields.has("sensorValues")
      ? sortedTypes.flatMap((type) => {
          const abbrev = abbreviateSensorType(type);
          return Array.from({ length: maxAxesByType.get(type) || 0 }, (_, i) => `${abbrev}_${axisLabel(i)}`);
        })
      : [];

    const statHeaders = enabledFields.has("labelStats")
      ? sortedTypes.flatMap((type) => {
          const abbrev = abbreviateSensorType(type);
          return Array.from({ length: maxAxesByType.get(type) || 0 }, (_, i) => [
            `${abbrev}_label_rms_${axisLabel(i)}`,
            `${abbrev}_label_std_${axisLabel(i)}`,
            `${abbrev}_label_p2p_${axisLabel(i)}`,
          ]).flat();
        })
      : [];

    const headers = [
      ...(enabledFields.has("runId")       ? ["runId"]       : []),
      ...(enabledFields.has("runName")      ? ["runName"]      : []),
      ...(enabledFields.has("runDate")      ? ["runDate"]      : []),
      ...(enabledFields.has("context")      ? ["context"]      : []),
      ...(enabledFields.has("timestamp")    ? ["timestamp"]    : []),
      ...sensorValueHeaders,
      ...(enabledFields.has("labels")       ? ["labelId", "labelText", "labelKind"] : []),
      ...statHeaders,
    ];

    const lines = [buildCsvLine(headers)];
    for (const row of dataRows) {
      const valueCells = enabledFields.has("sensorValues")
        ? sortedTypes.flatMap((type) => {
            const vals = row.valuesByType.get(type) || [];
            return Array.from({ length: maxAxesByType.get(type) || 0 }, (_, i) =>
              vals[i] !== null && vals[i] !== undefined ? vals[i] : ""
            );
          })
        : [];

      const statCells = enabledFields.has("labelStats")
        ? sortedTypes.flatMap((type) => {
            const typeStats = row.statsByType.get(type) || [];
            return Array.from({ length: maxAxesByType.get(type) || 0 }, (_, i) => {
              const s = typeStats[i];
              if (!s) return ["", "", ""];
              return [
                s.rms !== null ? s.rms.toFixed(6) : "",
                s.std !== null ? s.std.toFixed(6) : "",
                s.p2p !== null ? s.p2p.toFixed(6) : "",
              ];
            }).flat();
          })
        : [];

      lines.push(buildCsvLine([
        ...(enabledFields.has("runId")       ? [row.runId]    : []),
        ...(enabledFields.has("runName")      ? [row.runName]  : []),
        ...(enabledFields.has("runDate")      ? [row.runDate]  : []),
        ...(enabledFields.has("context")      ? [row.context]  : []),
        ...(enabledFields.has("timestamp")    ? [row.timestamp]: []),
        ...valueCells,
        ...(enabledFields.has("labels")       ? [row.labelId, row.labelText, row.labelKind] : []),
        ...statCells,
      ]));
    }

    const csv = lines.join("\n");
    const dateStamp = new Date().toISOString().slice(0, 10);

    res.setHeader("Content-Type", "text/csv; charset=utf-8");
    res.setHeader(
      "Content-Disposition",
      `attachment; filename="multi-run-${dateStamp}.csv"`
    );
    return res.status(200).send(csv);
  } catch (error) {
    return res.status(500).json({
      message: "Failed to export multi-run CSV.",
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

runRouter.put("/:runid/metadata", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) return res.status(404).json({ message: "Run not found." });

    const { description, weather, date, metadata } = req.body;
    const fields = {};
    if (description !== undefined) fields.description = String(description);
    if (weather !== undefined) fields.weather = String(weather);
    if (date !== undefined) {
      const parsed = new Date(date);
      if (isNaN(parsed.getTime())) return res.status(400).json({ message: "Invalid date." });
      fields.date = parsed;
    }
    if (metadata !== undefined) {
      if (typeof metadata !== "object" || Array.isArray(metadata) || metadata === null) {
        return res.status(400).json({ message: "Metadata must be a JSON object." });
      }
      fields.metadata = metadata;
    }

    const updated = await runService.updateRunMetadata(runid, fields);
    return res.json({ run: updated });
  } catch (error) {
    return res.status(400).json({ message: "Failed to update run metadata.", error: error.message });
  }
});

// ── View-state (per-run dashboard config) ────────────────────────────────────

const VIEW_STATE_MAX_CHARTS = 8;

const normalizeChartViewState = (raw) => {
  if (!raw || typeof raw !== "object") return null;
  return {
    selectedSensorKeys:    Array.isArray(raw.selectedSensorKeys) ? raw.selectedSensorKeys.filter((k) => typeof k === "string") : [],
    sensorFilterPipelines: raw.sensorFilterPipelines && typeof raw.sensorFilterPipelines === "object" ? raw.sensorFilterPipelines : {},
    sensorFiltersActive:   raw.sensorFiltersActive   && typeof raw.sensorFiltersActive   === "object" ? raw.sensorFiltersActive   : {},
    traceVisibility:       raw.traceVisibility       && typeof raw.traceVisibility       === "object" ? raw.traceVisibility       : {},
    sensorSyncOffsets:     raw.sensorSyncOffsets     && typeof raw.sensorSyncOffsets     === "object" ? raw.sensorSyncOffsets     : {},
    independentScales:     Boolean(raw.independentScales),
    comparisonRunIds:      Array.isArray(raw.comparisonRunIds) ? raw.comparisonRunIds.filter((id) => typeof id === "string") : [],
    showLabels:            typeof raw.showLabels === "boolean" ? raw.showLabels : true,
    showTrims:             typeof raw.showTrims  === "boolean" ? raw.showTrims  : true,
    showHighlightSections: Boolean(raw.showHighlightSections),
    showStatAnnotations:   Boolean(raw.showStatAnnotations),
  };
};

runRouter.get("/:runid/view-state", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) return res.status(404).json({ message: "Run not found." });

    const db = await connectDB();
    const coll = await getCollection(db, "run_view_states");
    const doc = await coll.findOne({ runId: runid });

    return res.json({
      charts: Array.isArray(doc?.charts) ? doc.charts : [],
      videoSyncOffset: typeof doc?.videoSyncOffset === "number" ? doc.videoSyncOffset : null,
    });
  } catch (error) {
    return res.status(500).json({ message: "Failed to fetch view state.", error: error.message });
  }
});

runRouter.put("/:runid/view-state", async (req, res) => {
  try {
    const runid = req.params.runid;
    const authorizedRun = await findRunForUser(runid, req.user).catch(() => null);
    if (!authorizedRun) return res.status(404).json({ message: "Run not found." });

    const db = await connectDB();
    const coll = await getCollection(db, "run_view_states");

    const setFields = { runId: runid, updatedAt: new Date() };

    if (Array.isArray(req.body?.charts)) {
      const rawCharts = req.body.charts;
      setFields.charts = rawCharts
        .slice(0, VIEW_STATE_MAX_CHARTS)
        .map(normalizeChartViewState)
        .filter(Boolean);
    }

    if (typeof req.body?.videoSyncOffset === "number" && Number.isFinite(req.body.videoSyncOffset)) {
      setFields.videoSyncOffset = req.body.videoSyncOffset;
    }

    await coll.updateOne(
      { runId: runid },
      { $set: setFields },
      { upsert: true },
    );

    const updated = await coll.findOne({ runId: runid });
    return res.json({
      charts: Array.isArray(updated?.charts) ? updated.charts : [],
      videoSyncOffset: typeof updated?.videoSyncOffset === "number" ? updated.videoSyncOffset : null,
    });
  } catch (error) {
    return res.status(500).json({ message: "Failed to save view state.", error: error.message });
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
    const viewStatesColl = await getCollection(db, "run_view_states");
    await viewStatesColl.deleteOne({ runId: runid });
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

    // For CSV uploads: parse early to detect column labels (axes) before any DB work.
    let csvReadings = null;
    let csvSegments = null;
    let uploadedAxes = isBinUpload ? sensorConfig.binaryAxes : null;
    if (isCsvUpload) {
      let csvResult;
      try {
        csvResult = buildCsvSensorReadings(csvBodyText);
      } catch (error) {
        return res.status(400).json({ message: error.message });
      }
      if (csvResult.readings.length === 0) {
        return res.status(400).json({ message: "Upload did not contain any sensor readings." });
      }
      csvReadings = csvResult.readings;
      csvSegments = csvResult.segments;
      uploadedAxes = csvResult.axes;
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
          dataAxis: uploadedAxes.length,
          location: "uploaded",
        },
        $setOnInsert: {
          id: resolvedSensorId,
        },
      },
      { upsert: true }
    );

    const runSensorUpdate = { sensorType: resolvedSensorType, axes: uploadedAxes };
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

    let readings;
    if (isBinUpload) {
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

        parsedReadings.push({ timestamp: timestampSeconds, data: parsedData });
      }
      readings = parsedReadings;
    } else {
      readings = csvReadings;
    }

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

    let labelsCreated = 0;
    if (isCsvUpload && Array.isArray(csvSegments) && csvSegments.some((s) => s)) {
      const inferredLabels = inferLabelsFromSegments(
        csvReadings,
        csvSegments,
        resolvedRunId.toString(),
        resolvedSensorId
      );
      if (inferredLabels.length > 0) {
        const runLabelsColl = await getCollection(db, "run_labels");
        const now = new Date();
        await runLabelsColl.insertMany(
          inferredLabels.map((label) => ({ ...label, runId: resolvedRunId, createdAt: now, updatedAt: now }))
        );
        labelsCreated = inferredLabels.length;
      }
    }

    return res.status(runCreated ? 201 : 200).json({
      message: runCreated
        ? `Run created and CSV data uploaded successfully.${labelsCreated ? ` ${labelsCreated} label(s) imported.` : ""}`
        : `CSV sensor data uploaded to existing run successfully.${labelsCreated ? ` ${labelsCreated} label(s) imported.` : ""}`,
      runId: resolvedRunId,
      name: resolvedRunName || `Run ${resolvedRunId.toString()}`,
      context: resolvedContext,
      contextId: resolvedContextId,
      createdRun: runCreated,
      sensorType: resolvedSensorType,
      sensorId: resolvedSensorId,
      labelsCreated,
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
