import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import "./UPlotGraph.css";
import { fetchRuns, updateRunLabels } from "./api";

const SERVER_URL = import.meta.env.VITE_SERVER_URL;
const ACCESS_TOKEN_STORAGE_KEY = "vppsports_access_token";
const DEFAULT_PLOT_RESOLUTION = 1400;

const FILTERS = [
  { id: "kalman", label: "Kalman" },
  { id: "movingaverage", label: "MovAvg" },
  { id: "savitzkygolay", label: "SavGol" },
];

const TRACE_COLORS = [
  "#1f77b4",
  "#d62728",
  "#2ca02c",
  "#ff7f0e",
  "#17becf",
  "#8c564b",
];

const getAuthHeaders = () => {
  const token = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const fetchJson = async (url) => {
  const response = await fetch(url, {
    headers: getAuthHeaders(),
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Network response was not ok");
  }

  return response.json();
};

const fetchRunSensors = async (runId) =>
  fetchJson(`${SERVER_URL}/run/${runId}/sensor`);
const fetchRun = async (runId) => fetchJson(`${SERVER_URL}/run/${runId}`);

const buildSensorDataUrl = (runId, sensorId, options = {}) => {
  const params = new URLSearchParams();
  if (options.filters) params.set("filters", options.filters);
  if (options.mode) params.set("mode", options.mode);
  if (Number.isFinite(options.start))
    params.set("start", String(options.start));
  if (Number.isFinite(options.end)) params.set("end", String(options.end));
  if (Number.isFinite(options.resolution))
    params.set("resolution", String(options.resolution));
  const query = params.toString();
  return `${SERVER_URL}/run/${runId}/sensor/${sensorId}/data${query ? `?${query}` : ""}`;
};

const fetchSensorData = async (runId, sensorId, options = {}) =>
  fetchJson(buildSensorDataUrl(runId, sensorId, options));

const normalizeSeriesPayload = (payload) => {
  if (Array.isArray(payload)) {
    return {
      readings: payload,
      sampleCountRaw: payload.length,
      sampleCountReturned: payload.length,
    };
  }

  return {
    readings: Array.isArray(payload?.readings) ? payload.readings : [],
    sampleCountRaw: payload?.sampleCountRaw ?? 0,
    sampleCountReturned: payload?.sampleCountReturned ?? 0,
  };
};

const getAxisCount = (readings) => {
  if (!Array.isArray(readings) || readings.length === 0) return 0;
  return readings.reduce((maxAxisCount, reading) => {
    const axisCount = Array.isArray(reading?.data) ? reading.data.length : 0;
    return Math.max(maxAxisCount, axisCount);
  }, 0);
};

const getAxisLabel = (axisIndex, axisCount) => {
  if (axisCount === 3) {
    return ["X-axis", "Y-axis", "Z-axis"][axisIndex] || `Axis ${axisIndex + 1}`;
  }
  return `raw_value${axisIndex + 1}`;
};

const getPlotResolution = () => {
  if (typeof window === "undefined") return DEFAULT_PLOT_RESOLUTION;
  const width = window.innerWidth || DEFAULT_PLOT_RESOLUTION;
  return Math.max(400, Math.min(Math.floor(width * 1.25), 2200));
};

const getInitialRange = (run) => {
  const timestamps = run?.totalTimestamps;
  if (!Array.isArray(timestamps) || timestamps.length === 0) {
    return { start: null, end: null };
  }

  return {
    start: timestamps[0],
    end: timestamps[timestamps.length - 1],
  };
};

const getCacheKey = (runId, sensorId, options = {}) => {
  const normalized = {
    mode: options.mode || "raw",
    start: Number.isFinite(options.start) ? options.start : "",
    end: Number.isFinite(options.end) ? options.end : "",
    filters: options.filters || "",
    resolution: Number.isFinite(options.resolution) ? options.resolution : "",
  };
  return `${runId}:${sensorId}:${normalized.mode}:${normalized.start}:${normalized.end}:${normalized.filters}:${normalized.resolution}`;
};

const filterKeyFromSelection = (useFilteredData, selectedFilters) => {
  if (!useFilteredData || selectedFilters.length === 0) return "";
  return selectedFilters.join(",");
};

const getSensorOffset = (offsetsBySensor, sensorId) => {
  const offset = offsetsBySensor[sensorId];
  return Number.isFinite(offset) ? offset : 0;
};

const getNearestIndex = (timestamps, target) => {
  if (
    !Array.isArray(timestamps) ||
    timestamps.length === 0 ||
    !Number.isFinite(target)
  ) {
    return -1;
  }

  let lo = 0;
  let hi = timestamps.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (timestamps[mid] < target) lo = mid + 1;
    else hi = mid;
  }

  if (lo === 0) return 0;
  const current = timestamps[lo];
  const previous = timestamps[lo - 1];
  if (!Number.isFinite(current)) return lo - 1;
  return Math.abs(current - target) < Math.abs(previous - target) ? lo : lo - 1;
};

const getNearestReading = (readings, target) => {
  if (!Array.isArray(readings) || readings.length === 0) return null;

  let lo = 0;
  let hi = readings.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (readings[mid].timestamp < target) lo = mid + 1;
    else hi = mid;
  }

  if (lo === 0) return readings[0];
  const current = readings[lo];
  const previous = readings[lo - 1];
  if (!current) return previous ?? null;
  return Math.abs(current.timestamp - target) <
    Math.abs(previous.timestamp - target)
    ? current
    : previous;
};

const interpolateSeriesValue = (points, target) => {
  if (!Array.isArray(points) || points.length === 0 || !Number.isFinite(target)) {
    return null;
  }

  let lo = 0;
  let hi = points.length - 1;

  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (points[mid].x < target) lo = mid + 1;
    else hi = mid;
  }

  if (lo === 0) return points[0]?.y ?? null;

  const right = points[lo];
  const left = points[lo - 1];
  if (!right) return left?.y ?? null;
  if (!left) return right?.y ?? null;
  if (!Number.isFinite(left.y) || !Number.isFinite(right.y)) {
    return Number.isFinite(left.y) ? left.y : Number.isFinite(right.y) ? right.y : null;
  }

  const span = right.x - left.x;
  if (!(span > 0)) return left.y;

  const ratio = (target - left.x) / span;
  return left.y + (right.y - left.y) * ratio;
};

const interpolateSeriesValueWithinBounds = (points, target) => {
  if (!Array.isArray(points) || points.length === 0 || !Number.isFinite(target)) {
    return null;
  }

  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  if (!Number.isFinite(firstPoint?.x) || !Number.isFinite(lastPoint?.x)) {
    return null;
  }
  if (target < firstPoint.x || target > lastPoint.x) {
    return null;
  }

  return interpolateSeriesValue(points, target);
};

const buildTraceKey = ({ runId, sensorId, axisIndex, useFilteredData }) =>
  `${runId}:${sensorId}:${axisIndex}:${useFilteredData ? "filtered" : "raw"}`;

const getSensorDisplayLabel = (entry) => {
  const hasName = entry.sensorName && String(entry.sensorName).trim();
  const hasType = entry.sensorType && String(entry.sensorType).trim();
  if (hasType && hasName) return `${entry.sensorType} - ${entry.sensorName}`;
  if (hasType) return `${entry.sensorType} (${entry.sensorId})`;
  if (hasName) return entry.sensorName;
  return `Sensor ${entry.sensorId}`;
};

const createLabelId = () =>
  `label-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
const labelsEqual = (left, right) =>
  JSON.stringify(left) === JSON.stringify(right);
const serializeLabelForSave = (label) => ({
  ...label,
  points:
    label?.kind === "single"
      ? Array.isArray(label?.points)
        ? label.points
        : []
      : [],
  updatedAt: new Date().toISOString(),
});

const HIGHLIGHT_LABEL_COLOR = "#0d6efd";
const HIGHLIGHT_LABEL_PREFIX = "Detected section";

const buildHighlightSectionsFromReadings = (readings, syncOffset = 0) => {
  if (!Array.isArray(readings) || readings.length === 0) return [];

  const sections = [];
  let active = false;
  let sectionStart = null;

  readings.forEach((reading, index) => {
    const zValue = reading?.data?.[2];
    if (typeof zValue !== "number") return;

    if (zValue > 1.25 && !active) {
      active = true;
      sectionStart = index;
      return;
    }

    if (zValue < 1.1 && active) {
      active = false;
      const x0 = readings[sectionStart]?.timestamp + syncOffset;
      const x1 = readings[index]?.timestamp + syncOffset;
      if (Number.isFinite(x0) && Number.isFinite(x1) && x1 >= x0) {
        sections.push({
          x0,
          x1,
          color: "rgba(13, 110, 253, 0.12)",
        });
      }
    }
  });

  if (active && sectionStart !== null) {
    const x0 = readings[sectionStart]?.timestamp + syncOffset;
    const x1 = readings[readings.length - 1]?.timestamp + syncOffset;
    if (Number.isFinite(x0) && Number.isFinite(x1) && x1 >= x0) {
      sections.push({
        x0,
        x1,
        color: "rgba(13, 110, 253, 0.12)",
      });
    }
  }

  return sections;
};

const buildHighlightLabelId = (entryKey, startTimestamp, endTimestamp) =>
  `highlight-${entryKey}-${Math.round(startTimestamp * 1000)}-${Math.round(endTimestamp * 1000)}`;

const buildRangeLabelFromSection = ({
  section,
  sectionIndex,
  sourceEntryKey,
  seriesItems,
}) => {
  if (!section || !Array.isArray(seriesItems) || seriesItems.length === 0) {
    return null;
  }

  const selectedPoints = seriesItems.flatMap((seriesItem) =>
    (seriesItem.points || [])
      .filter(
        (point) =>
          Number.isFinite(point?.x) &&
          Number.isFinite(point?.y) &&
          point.x >= section.x0 &&
          point.x <= section.x1,
      )
      .map((point) => ({
        traceKey: seriesItem.traceKey,
        timestamp: point.x,
        yValue: point.y,
      })),
  );

  if (selectedPoints.length === 0) {
    return null;
  }

  const orderedPoints = [...selectedPoints].sort(
    (left, right) => left.timestamp - right.timestamp,
  );
  const firstPoint = orderedPoints[0];
  const traceKeys = [...new Set(selectedPoints.map((point) => point.traceKey))];

  return normalizeLabel({
    id: buildHighlightLabelId(sourceEntryKey, section.x0, section.x1),
    kind: "range",
    text: `${HIGHLIGHT_LABEL_PREFIX} ${sectionIndex + 1}`,
    color: HIGHLIGHT_LABEL_COLOR,
    traceKeys,
    points: [],
    startTimestamp: section.x0,
    endTimestamp: section.x1,
    anchorTimestamp: firstPoint.timestamp,
    anchorY: firstPoint.yValue,
    dx: 0,
    dy: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });
};

const normalizeLabel = (label) => {
  const kind = String(label?.kind || "")
    .trim()
    .toLowerCase();
  const startTimestamp = Number(label?.startTimestamp);
  const endTimestamp = Number(label?.endTimestamp);
  const anchorTimestamp = Number(label?.anchorTimestamp);
  const anchorY = Number(label?.anchorY);

  if (
    !label?.id ||
    !["single", "range"].includes(kind) ||
    !Number.isFinite(startTimestamp) ||
    !Number.isFinite(endTimestamp) ||
    !Number.isFinite(anchorTimestamp) ||
    !Number.isFinite(anchorY)
  ) {
    return null;
  }

  return {
    id: String(label.id),
    kind,
    text: String(label?.text || ""),
    color: String(label?.color || "#0d6efd"),
    traceKeys: Array.isArray(label?.traceKeys)
      ? label.traceKeys
          .map((traceKey) => String(traceKey).trim())
          .filter(Boolean)
      : [],
    points: Array.isArray(label?.points)
      ? label.points
          .map((point) => {
            const traceKey = String(point?.traceKey || "").trim();
            const timestamp = Number(point?.timestamp);
            const yValue = Number(point?.yValue);
            if (
              !traceKey ||
              !Number.isFinite(timestamp) ||
              !Number.isFinite(yValue)
            )
              return null;
            return { traceKey, timestamp, yValue };
          })
          .filter(Boolean)
      : [],
    startTimestamp: Math.min(startTimestamp, endTimestamp),
    endTimestamp: Math.max(startTimestamp, endTimestamp),
    anchorTimestamp,
    anchorY,
    dx: Number.isFinite(Number(label?.dx)) ? Number(label.dx) : 0,
    dy: Number.isFinite(Number(label?.dy)) ? Number(label.dy) : 0,
    createdAt: label?.createdAt || new Date().toISOString(),
    updatedAt: label?.updatedAt || new Date().toISOString(),
  };
};

const getLabelSeries = (traceKeys, seriesByTraceKey) =>
  [...new Set((traceKeys || []).map((traceKey) => String(traceKey).trim()).filter(Boolean))]
    .map((traceKey) => seriesByTraceKey.get(traceKey))
    .filter(Boolean);

const rebuildSingleLabel = (label, traceKeys, seriesByTraceKey) => {
  const linkedSeries = getLabelSeries(traceKeys, seriesByTraceKey);
  if (linkedSeries.length === 0) return label;

  const anchorTimestamp = Number.isFinite(Number(label?.anchorTimestamp))
    ? Number(label.anchorTimestamp)
    : Number(label?.startTimestamp);
  if (!Number.isFinite(anchorTimestamp)) return label;

  const points = linkedSeries
    .map((seriesItem) => {
      const nearest = getNearestReading(
        seriesItem.points.map((point) => ({ timestamp: point.x, data: [point.y] })),
        anchorTimestamp,
      );
      if (!nearest) return null;
      return {
        traceKey: seriesItem.traceKey,
        timestamp: nearest.timestamp,
        yValue: nearest.data[0],
      };
    })
    .filter(Boolean);

  const anchorY =
    points.length > 0
      ? points.reduce((sum, point) => sum + point.yValue, 0) / points.length
      : label.anchorY;

  return normalizeLabel({
    ...label,
    traceKeys: linkedSeries.map((seriesItem) => seriesItem.traceKey),
    points,
    startTimestamp: anchorTimestamp,
    endTimestamp: anchorTimestamp,
    anchorTimestamp,
    anchorY,
    updatedAt: new Date().toISOString(),
  });
};

const rebuildRangeLabel = (label, traceKeys, startTimestamp, endTimestamp, seriesByTraceKey) => {
  const linkedSeries = getLabelSeries(traceKeys, seriesByTraceKey);
  if (linkedSeries.length === 0) return label;

  const rangeStart = Math.min(startTimestamp, endTimestamp);
  const rangeEnd = Math.max(startTimestamp, endTimestamp);
  if (!Number.isFinite(rangeStart) || !Number.isFinite(rangeEnd)) return label;

  const anchorTimestamp = (rangeStart + rangeEnd) / 2;
  const anchorValues = linkedSeries
    .map((seriesItem) => interpolateSeriesValue(seriesItem.points, anchorTimestamp))
    .filter((value) => Number.isFinite(value));
  const anchorY =
    anchorValues.length > 0
      ? anchorValues.reduce((sum, value) => sum + value, 0) / anchorValues.length
      : label.anchorY;

  return normalizeLabel({
    ...label,
    traceKeys: linkedSeries.map((seriesItem) => seriesItem.traceKey),
    points: [],
    startTimestamp: rangeStart,
    endTimestamp: rangeEnd,
    anchorTimestamp,
    anchorY,
    updatedAt: new Date().toISOString(),
  });
};

export default function EChartGraph({
  selectedRun,
  sliderValue,
  setSliderValue,
  removeFunction,
}) {
  const [useFilteredData, setUseFilteredData] = useState(false);
  const [selectedFilters, setSelectedFilters] = useState([]);
  const [pendingFilters, setPendingFilters] = useState([]);
  const [availableSensors, setAvailableSensors] = useState([]);
  const [selectedSensorKeys, setSelectedSensorKeys] = useState([]);
  const [sensorSyncOffsets, setSensorSyncOffsets] = useState({});
  const [draggedFilter, setDraggedFilter] = useState(null);
  const [plotSeriesBySensor, setPlotSeriesBySensor] = useState({});
  const [rawSeriesBySensor, setRawSeriesBySensor] = useState({});
  const [plotResolution, setPlotResolution] = useState(getPlotResolution);
  const [traceVisibility, setTraceVisibility] = useState({});
  const [isPlotLoading, setIsPlotLoading] = useState(false);
  const [isRawLoading, setIsRawLoading] = useState(false);
  const [sliderReadout, setSliderReadout] = useState([]);
  const [showHighlightSections, setShowHighlightSections] = useState(false);
  const [availableRuns, setAvailableRuns] = useState([]);
  const [comparisonRunId, setComparisonRunId] = useState("");
  const [comparisonRuns, setComparisonRuns] = useState([]);
  const [comparisonSensorsByRun, setComparisonSensorsByRun] = useState({});
  const [comparisonPlotSeriesByRun, setComparisonPlotSeriesByRun] = useState(
    {},
  );
  const [comparisonRawSeriesByRun, setComparisonRawSeriesByRun] = useState({});
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [runLabels, setRunLabels] = useState([]);
  const [selectedLabelTraceKeys, setSelectedLabelTraceKeys] = useState([]);
  const [pendingLabelMode, setPendingLabelMode] = useState(null);
  const [activeLabelId, setActiveLabelId] = useState(null);
  const [labelDraftText, setLabelDraftText] = useState("");
  const [labelDraftColor, setLabelDraftColor] = useState("#0d6efd");
  const [chartRevision, setChartRevision] = useState(0);
  const [showLabels, setShowLabels] = useState(true);
  const [independentScales, setIndependentScales] = useState(false);
  const [selectionBox, setSelectionBox] = useState(null);
  const [visibleRange, setVisibleRange] = useState(() =>
    getInitialRange(selectedRun),
  );

  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const requestIdRef = useRef({
    plot: 0,
    raw: 0,
    comparisonPlot: 0,
    comparisonRaw: 0,
  });
  const cacheRef = useRef({ plot: new Map(), raw: new Map() });
  const zoomCommitTimeoutRef = useRef(null);
  const labelSaveTimeoutRef = useRef(null);
  const lastSavedLabelsRef = useRef([]);
  const draggingLabelRef = useRef(null);
  const selectionDragRef = useRef(null);
  const selectionBoxRef = useRef(null);

  const getChartInstance = useCallback(() => {
    const container = chartContainerRef.current;
    if (!container) return null;

    const existing = chartRef.current;
    if (
      existing &&
      typeof existing.isDisposed === "function" &&
      !existing.isDisposed()
    ) {
      return existing;
    }

    const domInstance = echarts.getInstanceByDom(container);
    if (
      domInstance &&
      typeof domInstance.isDisposed === "function" &&
      !domInstance.isDisposed()
    ) {
      chartRef.current = domInstance;
      return domInstance;
    }

    const instance = echarts.init(container, null, { renderer: "canvas" });
    chartRef.current = instance;
    return instance;
  }, []);

  const filterKey = filterKeyFromSelection(useFilteredData, selectedFilters);
  const runTimestamps = selectedRun?.totalTimestamps ?? [];
  const currentTimestamp = runTimestamps[sliderValue] ?? runTimestamps[0] ?? 0;
  const currentRunName = selectedRun?.name || `Run ${selectedRun?._id}`;

  const availableSensorEntries = useMemo(() => {
    const currentEntries = (availableSensors || []).map((sensor) => {
      const sensorId = typeof sensor === "object" ? sensor.sensorId : sensor;
      const sensorName = typeof sensor === "object" ? sensor.name || "" : "";
      const sensorType = typeof sensor === "object" ? sensor.sensorType || "" : "";
      return {
        key: `${selectedRun?._id}:${sensorId}`,
        runId: selectedRun?._id,
        runName: currentRunName,
        sensorId,
        sensorName,
        sensorType,
        isPrimary: true,
      };
    });

    const comparisonEntries = comparisonRuns.flatMap((run) =>
      (comparisonSensorsByRun[run._id] || []).map((sensor) => {
        const sensorId = typeof sensor === "object" ? sensor.sensorId : sensor;
        const sensorName = typeof sensor === "object" ? sensor.name || "" : "";
        const sensorType = typeof sensor === "object" ? sensor.sensorType || "" : "";
        return {
          key: `${run._id}:${sensorId}`,
          runId: run._id,
          runName: run.name || `Run ${run._id}`,
          sensorId,
          sensorName,
          sensorType,
          isPrimary: false,
        };
      }),
    );

    return [...currentEntries, ...comparisonEntries];
  }, [
    availableSensors,
    comparisonRuns,
    comparisonSensorsByRun,
    currentRunName,
    selectedRun?._id,
  ]);

  const selectedSensorEntries = useMemo(
    () =>
      availableSensorEntries.filter((entry) =>
        selectedSensorKeys.includes(entry.key),
      ),
    [availableSensorEntries, selectedSensorKeys],
  );

  const primarySelectedSensorIds = useMemo(
    () =>
      selectedSensorEntries
        .filter((entry) => entry.isPrimary)
        .map((entry) => entry.sensorId),
    [selectedSensorEntries],
  );

  const comparisonSelectedEntriesByRun = useMemo(
    () =>
      selectedSensorEntries
        .filter((entry) => !entry.isPrimary)
        .reduce((acc, entry) => {
          if (!acc[entry.runId]) acc[entry.runId] = [];
          acc[entry.runId].push(entry);
          return acc;
        }, {}),
    [selectedSensorEntries],
  );

  useEffect(
    () => () => {
      if (zoomCommitTimeoutRef.current !== null) {
        window.clearTimeout(zoomCommitTimeoutRef.current);
      }
    },
    [],
  );

  useEffect(
    () => () => {
      if (labelSaveTimeoutRef.current !== null) {
        window.clearTimeout(labelSaveTimeoutRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    const handleResize = () => setPlotResolution(getPlotResolution());
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    cacheRef.current = { plot: new Map(), raw: new Map() };
    requestIdRef.current = {
      plot: 0,
      raw: 0,
      comparisonPlot: 0,
      comparisonRaw: 0,
    };
    setPlotSeriesBySensor({});
    setRawSeriesBySensor({});
    setSelectedSensorKeys([]);
    setSensorSyncOffsets({});
    setTraceVisibility({});
    setSliderReadout([]);
    setShowHighlightSections(false);
    setVisibleRange(getInitialRange(selectedRun));
    setComparisonRunId("");
    setComparisonRuns([]);
    setComparisonSensorsByRun({});
    setComparisonPlotSeriesByRun({});
    setComparisonRawSeriesByRun({});
    setShowLabels(true);
    setSelectionBox(null);
    selectionBoxRef.current = null;
    selectionDragRef.current = null;
    setPendingLabelMode(null);
    setActiveLabelId(null);
  }, [selectedRun?._id]);

  useEffect(() => {
    const nextLabels = Array.isArray(selectedRun?.labels)
      ? selectedRun.labels.map(normalizeLabel).filter(Boolean)
      : [];
    lastSavedLabelsRef.current = nextLabels;
    setRunLabels(nextLabels);
    setPendingLabelMode(null);
    setActiveLabelId((prev) =>
      nextLabels.some((label) => label.id === prev) ? prev : null,
    );
  }, [selectedRun?.labels]);

  useEffect(() => {
    fetchRuns()
      .then((runs) => setAvailableRuns(Array.isArray(runs) ? runs : []))
      .catch((error) => {
        console.error("Error loading runs for comparison:", error);
        setAvailableRuns([]);
      });
  }, []);

  useEffect(() => {
    const loadAvailableSensors = async () => {
      if (!selectedRun?._id) return;
      try {
        const sensors = await fetchRunSensors(selectedRun._id);
        setAvailableSensors(Array.isArray(sensors) ? sensors : []);
      } catch (error) {
        console.error("Error loading available sensors:", error);
        setAvailableSensors([]);
      }
    };

    loadAvailableSensors();
  }, [selectedRun?._id]);

  useEffect(() => {
    setSensorSyncOffsets((prev) =>
      Object.fromEntries(
        selectedSensorKeys.map((sensorKey) => [
          sensorKey,
          getSensorOffset(prev, sensorKey),
        ]),
      ),
    );
  }, [selectedSensorKeys]);

  useEffect(() => {
    const loadComparisonSensors = async () => {
      if (!comparisonRuns.length) {
        setComparisonSensorsByRun({});
        return;
      }

      try {
        const entries = await Promise.all(
          comparisonRuns.map(async (run) => [
            run._id,
            await fetchRunSensors(run._id),
          ]),
        );
        setComparisonSensorsByRun(Object.fromEntries(entries));
      } catch (error) {
        console.error("Error loading comparison run sensors:", error);
      }
    };

    loadComparisonSensors();
  }, [comparisonRuns]);

  useEffect(() => {
    const requestId = ++requestIdRef.current.plot;

    const loadPlotSeries = async () => {
      if (!selectedRun?._id || primarySelectedSensorIds.length === 0) {
        setPlotSeriesBySensor({});
        setIsPlotLoading(false);
        return;
      }

      setIsPlotLoading(true);

      const nextEntries = await Promise.all(
        primarySelectedSensorIds.map(async (sensorId) => {
          const cacheKey = getCacheKey(selectedRun._id, sensorId, {
            mode: "plot",
            start: visibleRange.start,
            end: visibleRange.end,
            filters: filterKey,
            resolution: plotResolution,
          });

          let cached = cacheRef.current.plot.get(cacheKey);
          if (!cached) {
            cached = fetchSensorData(selectedRun._id, sensorId, {
              mode: "plot",
              start: visibleRange.start,
              end: visibleRange.end,
              filters: filterKey || undefined,
              resolution: plotResolution,
            }).then(normalizeSeriesPayload);
            cacheRef.current.plot.set(cacheKey, cached);
          }

          return [sensorId, await cached];
        }),
      );

      if (requestId !== requestIdRef.current.plot) return;
      setPlotSeriesBySensor(Object.fromEntries(nextEntries));
      setIsPlotLoading(false);
    };

    loadPlotSeries().catch((error) => {
      if (requestId === requestIdRef.current.plot) {
        setIsPlotLoading(false);
      }
      console.error("Error loading ECharts plot data:", error);
    });
  }, [
    filterKey,
    plotResolution,
    primarySelectedSensorIds,
    selectedRun?._id,
    visibleRange.end,
    visibleRange.start,
  ]);

  useEffect(() => {
    const requestId = ++requestIdRef.current.raw;

    const loadRawSeries = async () => {
      if (!selectedRun?._id || primarySelectedSensorIds.length === 0) {
        setRawSeriesBySensor({});
        setIsRawLoading(false);
        return;
      }

      setIsRawLoading(true);

      const nextEntries = await Promise.all(
        primarySelectedSensorIds.map(async (sensorId) => {
          const cacheKey = getCacheKey(selectedRun._id, sensorId, {
            mode: "raw",
            filters: filterKey,
          });

          let cached = cacheRef.current.raw.get(cacheKey);
          if (!cached) {
            cached = fetchSensorData(selectedRun._id, sensorId, {
              mode: "raw",
              filters: filterKey || undefined,
            });
            cacheRef.current.raw.set(cacheKey, cached);
          }

          const readings = await cached;
          return [sensorId, Array.isArray(readings) ? readings : []];
        }),
      );

      if (requestId !== requestIdRef.current.raw) return;
      setRawSeriesBySensor(Object.fromEntries(nextEntries));
      setIsRawLoading(false);
    };

    loadRawSeries().catch((error) => {
      if (requestId === requestIdRef.current.raw) {
        setIsRawLoading(false);
      }
      console.error("Error loading ECharts raw data:", error);
    });
  }, [filterKey, primarySelectedSensorIds, selectedRun?._id]);

  useEffect(() => {
    const requestId = ++requestIdRef.current.comparisonPlot;

    const loadComparisonPlotSeries = async () => {
      if (
        !comparisonRuns.length ||
        !selectedRun?._id ||
        Object.keys(comparisonSelectedEntriesByRun).length === 0
      ) {
        setComparisonPlotSeriesByRun({});
        return;
      }

      const currentBaseTimestamp = selectedRun?.totalTimestamps?.[0];
      if (!Number.isFinite(currentBaseTimestamp)) {
        setComparisonPlotSeriesByRun({});
        return;
      }

      const runEntries = await Promise.all(
        comparisonRuns
          .filter(
            (comparisonRun) =>
              comparisonSelectedEntriesByRun[comparisonRun._id]?.length,
          )
          .map(async (comparisonRun) => {
            const comparisonBaseTimestamp = comparisonRun?.totalTimestamps?.[0];
            const mappedStart =
              Number.isFinite(visibleRange.start) &&
              Number.isFinite(comparisonBaseTimestamp)
                ? comparisonBaseTimestamp +
                  (visibleRange.start - currentBaseTimestamp)
                : undefined;
            const mappedEnd =
              Number.isFinite(visibleRange.end) &&
              Number.isFinite(comparisonBaseTimestamp)
                ? comparisonBaseTimestamp +
                  (visibleRange.end - currentBaseTimestamp)
                : undefined;

            const sensorEntries = await Promise.all(
              comparisonSelectedEntriesByRun[comparisonRun._id].map(
                async (entry) => {
                  const sensorId = entry.sensorId;
                  const cacheKey = getCacheKey(comparisonRun._id, sensorId, {
                    mode: "plot",
                    start: mappedStart,
                    end: mappedEnd,
                    filters: filterKey,
                    resolution: plotResolution,
                  });

                  let cached = cacheRef.current.plot.get(cacheKey);
                  if (!cached) {
                    cached = fetchSensorData(comparisonRun._id, sensorId, {
                      mode: "plot",
                      start: mappedStart,
                      end: mappedEnd,
                      filters: filterKey || undefined,
                      resolution: plotResolution,
                    }).then(normalizeSeriesPayload);
                    cacheRef.current.plot.set(cacheKey, cached);
                  }

                  return [sensorId, await cached];
                },
              ),
            );

            return [comparisonRun._id, Object.fromEntries(sensorEntries)];
          }),
      );

      if (requestId !== requestIdRef.current.comparisonPlot) return;
      setComparisonPlotSeriesByRun(Object.fromEntries(runEntries));
    };

    loadComparisonPlotSeries().catch((error) => {
      console.error("Error loading comparison plot data:", error);
    });
  }, [
    comparisonSelectedEntriesByRun,
    comparisonRuns,
    filterKey,
    plotResolution,
    selectedRun,
    visibleRange.end,
    visibleRange.start,
  ]);

  useEffect(() => {
    const requestId = ++requestIdRef.current.comparisonRaw;

    const loadComparisonRawSeries = async () => {
      if (
        !comparisonRuns.length ||
        Object.keys(comparisonSelectedEntriesByRun).length === 0
      ) {
        setComparisonRawSeriesByRun({});
        return;
      }

      const runEntries = await Promise.all(
        comparisonRuns
          .filter(
            (comparisonRun) =>
              comparisonSelectedEntriesByRun[comparisonRun._id]?.length,
          )
          .map(async (comparisonRun) => {
            const sensorEntries = await Promise.all(
              comparisonSelectedEntriesByRun[comparisonRun._id].map(
                async (entry) => {
                  const sensorId = entry.sensorId;
                  const cacheKey = getCacheKey(comparisonRun._id, sensorId, {
                    mode: "raw",
                    filters: filterKey,
                  });

                  let cached = cacheRef.current.raw.get(cacheKey);
                  if (!cached) {
                    cached = fetchSensorData(comparisonRun._id, sensorId, {
                      mode: "raw",
                      filters: filterKey || undefined,
                    });
                    cacheRef.current.raw.set(cacheKey, cached);
                  }

                  const readings = await cached;
                  return [sensorId, Array.isArray(readings) ? readings : []];
                },
              ),
            );

            return [comparisonRun._id, Object.fromEntries(sensorEntries)];
          }),
      );

      if (requestId !== requestIdRef.current.comparisonRaw) return;
      setComparisonRawSeriesByRun(Object.fromEntries(runEntries));
    };

    loadComparisonRawSeries().catch((error) => {
      console.error("Error loading comparison raw data:", error);
    });
  }, [comparisonRuns, comparisonSelectedEntriesByRun, filterKey]);

  const chartModel = useMemo(() => {
    const series = [];
    const readoutEntries = [];
    const traceColorByLabel = new Map();
    const currentBaseTimestamp = selectedRun?.totalTimestamps?.[0];
    const visibleTimestamps = runTimestamps.filter(
      (timestamp) =>
        timestamp >= visibleRange.start && timestamp <= visibleRange.end,
    );
    const displayResolution = Math.max(
      2,
      Math.min(plotResolution, Math.max(visibleTimestamps.length, 2)),
    );
    const fallbackStart = Number.isFinite(visibleRange.start)
      ? visibleRange.start
      : runTimestamps[0];
    const fallbackEnd = Number.isFinite(visibleRange.end)
      ? visibleRange.end
      : runTimestamps[runTimestamps.length - 1];
    const xValues =
      visibleTimestamps.length > 1
        ? visibleTimestamps
        : fallbackEnd > fallbackStart
          ? Array.from({ length: displayResolution }, (_, index) => {
              const ratio =
                displayResolution === 1 ? 0 : index / (displayResolution - 1);
              return fallbackStart + (fallbackEnd - fallbackStart) * ratio;
            })
          : [];

    selectedSensorEntries.forEach((entry) => {
      const payload = entry.isPrimary
        ? plotSeriesBySensor[entry.sensorId]
        : comparisonPlotSeriesByRun[entry.runId]?.[entry.sensorId];
      const plotReadings = payload?.readings;
      if (!Array.isArray(plotReadings) || plotReadings.length === 0) return;

      const axisCount = getAxisCount(plotReadings);
      const entryBaseTimestamp = entry.isPrimary
        ? currentBaseTimestamp
        : comparisonRuns.find((run) => run._id === entry.runId)
            ?.totalTimestamps?.[0];
      const alignmentOffset =
        !entry.isPrimary &&
        Number.isFinite(currentBaseTimestamp) &&
        Number.isFinite(entryBaseTimestamp)
          ? currentBaseTimestamp - entryBaseTimestamp
          : 0;
      const offset = getSensorOffset(sensorSyncOffsets, entry.key);

      for (let axisIndex = 0; axisIndex < axisCount; axisIndex += 1) {
        const label = `${entry.runName} ${getSensorDisplayLabel(entry)} ${getAxisLabel(axisIndex, axisCount)}${useFilteredData ? " (filtered)" : ""}`;
        const traceKey = buildTraceKey({
          runId: entry.runId,
          sensorId: entry.sensorId,
          axisIndex,
          useFilteredData,
        });
        const color = TRACE_COLORS[series.length % TRACE_COLORS.length];
        traceColorByLabel.set(label, color);
        const points = plotReadings
          .map((reading) => ({
            x: reading.timestamp + offset + alignmentOffset,
            y: reading.data?.[axisIndex] ?? null,
          }))
          .filter(
            (point) => Number.isFinite(point.x) && Number.isFinite(point.y),
          );
        const renderData = xValues.map((timestamp) => [
          timestamp,
          interpolateSeriesValueWithinBounds(points, timestamp),
        ]);

        series.push({
          traceKey,
          sensorId: entry.sensorId,
          axisIndex,
          label,
          color,
          runId: entry.runId,
          runName: entry.runName,
          points,
          renderData,
        });
      }

      const rawReadings = entry.isPrimary
        ? rawSeriesBySensor[entry.sensorId]
        : comparisonRawSeriesByRun[entry.runId]?.[entry.sensorId];
      const nearest = getNearestReading(rawReadings, currentTimestamp - offset);
      if (!nearest) return;

      const axes = (nearest.data || [])
        .map((value, axisIndex) => {
          const axisLabel = `${entry.runName} ${getSensorDisplayLabel(entry)} ${getAxisLabel(axisIndex, nearest.data.length)}${useFilteredData ? " (filtered)" : ""}`;
          if (!(traceVisibility[axisLabel] ?? true)) return null;
          return {
            name: getAxisLabel(axisIndex, nearest.data.length).replace(
              "-axis",
              "",
            ),
            value,
            color: traceColorByLabel.get(axisLabel) || "#6c757d",
          };
        })
        .filter(Boolean);

      if (axes.length === 0) return;

      readoutEntries.push({
        sensorId: entry.sensorId,
        sensorName: entry.sensorName,
        sensorType: entry.sensorType,
        runId: entry.runId,
        runName: entry.runName,
        timelineTimestamp: currentTimestamp,
        sensorTimestamp: nearest.timestamp,
        shift: offset,
        axes,
      });
    });

    return { series, readoutEntries, xValues };
  }, [
    comparisonPlotSeriesByRun,
    comparisonRawSeriesByRun,
    comparisonRuns,
    currentTimestamp,
    plotResolution,
    plotSeriesBySensor,
    rawSeriesBySensor,
    selectedRun,
    selectedSensorEntries,
    sensorSyncOffsets,
    traceVisibility,
    useFilteredData,
    visibleRange.end,
    visibleRange.start,
    runTimestamps,
  ]);

  const seriesByTraceKey = useMemo(
    () =>
      new Map(
        chartModel.series.map((seriesItem) => [
          seriesItem.traceKey,
          seriesItem,
        ]),
      ),
    [chartModel.series],
  );
  const activeLabel = useMemo(
    () => runLabels.find((label) => label.id === activeLabelId) || null,
    [activeLabelId, runLabels],
  );

  const computePixelPoint = useCallback(
    (x, y) => {
      const chart = getChartInstance();
      if (!chart) return null;
      try {
        const [left, top] = chart.convertToPixel(
          { xAxisIndex: 0, yAxisIndex: 0 },
          [x, y],
        );
        if (!Number.isFinite(left) || !Number.isFinite(top)) return null;
        return { left, top };
      } catch {
        return null;
      }
    },
    [getChartInstance],
  );

  const labelRenderItems = useMemo(
    () =>
      runLabels
        .map((label) => {
          const anchor = computePixelPoint(
            label.anchorTimestamp,
            label.anchorY,
          );
          if (!anchor) return null;
          const linkedSeries = label.traceKeys
            .map((traceKey) => seriesByTraceKey.get(traceKey))
            .filter(Boolean);
          const allHidden =
            linkedSeries.length > 0 &&
            linkedSeries.every(
              (seriesItem) => !(traceVisibility[seriesItem.label] ?? true),
            );
          return {
            ...label,
            left: anchor.left + label.dx,
            top: anchor.top + label.dy,
            anchorLeft: anchor.left,
            anchorTop: anchor.top,
            titleLeft: Math.max(8, anchor.left - 60),
            titleTop: 8,
            allHidden,
            color: label.color || "#0d6efd",
          };
        })
        .filter(Boolean),
    [
      chartRevision,
      computePixelPoint,
      runLabels,
      seriesByTraceKey,
      traceVisibility,
    ],
  );

  const labelPointMarkers = useMemo(
    () =>
      runLabels.flatMap((label) =>
        label.kind !== "single"
          ? []
          : (label.points || [])
              .map((point, index) => {
                const pixel = computePixelPoint(point.timestamp, point.yValue);
                if (!pixel) return null;
                return {
                  id: `${label.id}-${index}`,
                  left: pixel.left,
                  top: pixel.top,
                  color: label.color || "#0d6efd",
                };
              })
              .filter(Boolean),
      ),
    [chartRevision, computePixelPoint, runLabels],
  );

  const highlightSections = useMemo(() => {
    if (!showHighlightSections || selectedSensorEntries.length === 0) return [];
    const entry = selectedSensorEntries[0];
    const readings = entry.isPrimary
      ? rawSeriesBySensor[entry.sensorId]
      : comparisonRawSeriesByRun[entry.runId]?.[entry.sensorId];
    if (!Array.isArray(readings) || readings.length === 0) return [];

    const currentBaseTimestamp = selectedRun?.totalTimestamps?.[0];
    const entryBaseTimestamp = entry.isPrimary
      ? currentBaseTimestamp
      : comparisonRuns.find((run) => run._id === entry.runId)
          ?.totalTimestamps?.[0];
    const alignmentOffset =
      !entry.isPrimary &&
      Number.isFinite(currentBaseTimestamp) &&
      Number.isFinite(entryBaseTimestamp)
        ? currentBaseTimestamp - entryBaseTimestamp
        : 0;
    const syncOffset =
      getSensorOffset(sensorSyncOffsets, entry.key) + alignmentOffset;
    return buildHighlightSectionsFromReadings(readings, syncOffset);
  }, [
    comparisonRawSeriesByRun,
    comparisonRuns,
    rawSeriesBySensor,
    selectedRun,
    selectedSensorEntries,
    sensorSyncOffsets,
    showHighlightSections,
  ]);

  useEffect(() => {
    setSliderReadout(chartModel.readoutEntries);
  }, [chartModel.readoutEntries]);

  useEffect(() => {
    const validTraceKeys = new Set(
      chartModel.series.map((seriesItem) => seriesItem.traceKey),
    );
    setSelectedLabelTraceKeys((prev) =>
      prev.filter((traceKey) => validTraceKeys.has(traceKey)),
    );
  }, [chartModel.series]);

  useEffect(() => {
    const activeLabel = runLabels.find((label) => label.id === activeLabelId);
    setLabelDraftText(activeLabel?.text || "");
    setLabelDraftColor(activeLabel?.color || "#0d6efd");
  }, [activeLabelId, runLabels]);

  useEffect(() => {
    selectionBoxRef.current = selectionBox;
  }, [selectionBox]);

  useEffect(() => {
    if (!selectedRun?._id) return;
    if (labelsEqual(runLabels, lastSavedLabelsRef.current)) return;
    if (labelSaveTimeoutRef.current !== null) {
      window.clearTimeout(labelSaveTimeoutRef.current);
    }

    labelSaveTimeoutRef.current = window.setTimeout(async () => {
      try {
        const payload = runLabels.map(serializeLabelForSave);
        const response = await updateRunLabels(selectedRun._id, payload);
        const normalized = Array.isArray(response?.labels)
          ? response.labels.map(normalizeLabel).filter(Boolean)
          : payload.map(normalizeLabel).filter(Boolean);
        lastSavedLabelsRef.current = normalized;
        setRunLabels((prev) =>
          labelsEqual(prev, normalized) ? prev : normalized,
        );
      } catch (error) {
        console.error("Error saving run labels:", error);
      }
    }, 250);

    return () => {
      if (labelSaveTimeoutRef.current !== null) {
        window.clearTimeout(labelSaveTimeoutRef.current);
        labelSaveTimeoutRef.current = null;
      }
    };
  }, [runLabels, selectedRun?._id]);

  useEffect(() => {
    return () => {
      if (chartRef.current) {
        chartRef.current.dispose();
        chartRef.current = null;
      }
    };
  }, []);

  const chartOption = useMemo(() => {
    const visibleSeries = chartModel.series.filter(
      (seriesItem) => traceVisibility[seriesItem.label] ?? true,
    );

    let yAxisConfig;
    let seriesYAxisIndices;

    if (independentScales && visibleSeries.length > 0) {
      yAxisConfig = visibleSeries.map((seriesItem, idx) => {
        const values = seriesItem.renderData
          .map((pt) => pt[1])
          .filter((v) => v !== null && Number.isFinite(v));
        const min = values.length ? Math.min(...values) : 0;
        const max = values.length ? Math.max(...values) : 1;
        const padding = (max - min) * 0.05 || Math.abs(max) * 0.05 || 0.05;
        return {
          type: "value",
          scale: true,
          show: idx === 0,
          min: min - padding,
          max: max + padding,
          splitLine: idx === 0 ? { lineStyle: { color: "#eef1f4" } } : { show: false },
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: idx === 0 ? {} : { show: false },
        };
      });
      seriesYAxisIndices = visibleSeries.map((_, idx) => idx);
    } else {
      yAxisConfig = {
        type: "value",
        scale: true,
        splitLine: { lineStyle: { color: "#eef1f4" } },
      };
      seriesYAxisIndices = visibleSeries.map(() => 0);
    }

    return {
      animation: false,
      grid: { left: 52, right: 16, top: 24, bottom: 46 },
      tooltip: { show: false },
      xAxis: {
        type: "value",
        min: runTimestamps[0],
        max: runTimestamps[runTimestamps.length - 1],
        splitLine: { lineStyle: { color: "#eef1f4" } },
      },
      yAxis: yAxisConfig,
      dataZoom: visibleSeries.length
        ? [
            {
              type: "inside",
              xAxisIndex: 0,
              filterMode: "none",
              startValue: visibleRange.start,
              endValue: visibleRange.end,
            },
          ]
        : [],
      series: [
        {
          type: "line",
          silent: true,
          data: [],
          yAxisIndex: 0,
          lineStyle: { opacity: 0 },
          itemStyle: { opacity: 0 },
          markLine: Number.isFinite(currentTimestamp)
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#1f77b4", width: 2, type: "dashed" },
                data: [{ xAxis: currentTimestamp }],
              }
            : undefined,
          markArea:
            showHighlightSections || showLabels
              ? {
                  silent: true,
                  data: [
                    ...highlightSections.map((section) => [
                      {
                        xAxis: section.x0,
                        itemStyle: { color: section.color, borderWidth: 0 },
                      },
                      { xAxis: section.x1 },
                    ]),
                    ...runLabels
                      .filter((label) => showLabels && label.kind === "range")
                      .map((label) => [
                        {
                          xAxis: label.startTimestamp,
                          itemStyle: {
                            color: `${label.color || "#0d6efd"}22`,
                            borderColor: label.color || "#0d6efd",
                            borderWidth: 1,
                          },
                        },
                        { xAxis: label.endTimestamp },
                      ]),
                  ],
                }
              : undefined,
        },
        ...visibleSeries.map((seriesItem, idx) => ({
          name: seriesItem.label,
          type: "line",
          yAxisIndex: seriesYAxisIndices[idx],
          showSymbol: false,
          large: true,
          largeThreshold: 2000,
          sampling: "lttb",
          animation: false,
          progressive: 5000,
          progressiveThreshold: 10000,
          hoverLayerThreshold: Infinity,
          lineStyle: { width: 1.5, color: seriesItem.color },
          connectNulls: false,
          data: seriesItem.renderData,
        })),
      ],
    };
  }, [
    chartModel.series,
    currentTimestamp,
    highlightSections,
    independentScales,
    runLabels,
    runTimestamps,
    showHighlightSections,
    showLabels,
    traceVisibility,
    visibleRange.end,
    visibleRange.start,
  ]);

  useEffect(() => {
    const chart = getChartInstance();
    if (!chart) return;
    chart.setOption(chartOption, true);
    chart.resize();
    setChartRevision((prev) => prev + 1);
  }, [chartOption, getChartInstance]);

  useEffect(() => {
    const chart = getChartInstance();
    if (!chart) return;
    const zr = chart.getZr();

    const commitZoom = () => {
      if (zoomCommitTimeoutRef.current !== null)
        window.clearTimeout(zoomCommitTimeoutRef.current);
      zoomCommitTimeoutRef.current = window.setTimeout(() => {
        zoomCommitTimeoutRef.current = null;
        const zoom = chart.getOption()?.dataZoom?.[0];
        const start = Number(zoom?.startValue);
        const end = Number(zoom?.endValue);
        if (Number.isFinite(start) && Number.isFinite(end)) {
          setVisibleRange((prev) =>
            prev.start === start && prev.end === end ? prev : { start, end },
          );
          setChartRevision((prev) => prev + 1);
        }
      }, 120);
    };

    const handleClick = (params) => {
      if (!params?.event) return;
      const relativeX = params.event.zrX;
      const relativeY = params.event.zrY;
      if (pendingLabelMode === "single" && selectedLabelTraceKeys.length > 0) {
        const clickedTimestamp = chart.convertFromPixel(
          { xAxisIndex: 0 },
          relativeX,
        );
        let anchor = null;
        const selectedPoints = chartModel.series
          .filter((seriesItem) =>
            selectedLabelTraceKeys.includes(seriesItem.traceKey),
          )
          .map((seriesItem) => {
            const point = getNearestReading(
              seriesItem.points.map((entry) => ({
                timestamp: entry.x,
                data: [entry.y],
              })),
              clickedTimestamp,
            );
            if (!point) return null;
            const pixel = computePixelPoint(point.timestamp, point.data[0]);
            if (!pixel) return null;
            const distance = Math.hypot(
              pixel.left - relativeX,
              pixel.top - relativeY,
            );
            if (!anchor || distance < anchor.distance) {
              anchor = {
                traceKey: seriesItem.traceKey,
                xTimestamp: point.timestamp,
                yValue: point.data[0],
                distance,
              };
            }
            return {
              traceKey: seriesItem.traceKey,
              timestamp: point.timestamp,
              yValue: point.data[0],
            };
          })
          .filter(Boolean);

        if (anchor && selectedPoints.length > 0) {
          const nextLabel = rebuildSingleLabel(
            {
              id: createLabelId(),
              kind: "single",
              text: "",
              color: "#0d6efd",
              traceKeys: [
                ...new Set(selectedPoints.map((point) => point.traceKey)),
              ],
              points: [],
              startTimestamp: anchor.xTimestamp,
              endTimestamp: anchor.xTimestamp,
              anchorTimestamp: anchor.xTimestamp,
              anchorY: anchor.yValue,
              dx: 0,
              dy: 0,
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
            selectedLabelTraceKeys,
            seriesByTraceKey,
          );
          if (nextLabel) {
            setRunLabels((prev) => [...prev, nextLabel]);
            setActiveLabelId(nextLabel.id);
            setLabelDraftText("");
          }
        }
        setPendingLabelMode(null);
        return;
      }
      const xValue = chart.convertFromPixel({ xAxisIndex: 0 }, relativeX);
      const nextIndex = getNearestIndex(runTimestamps, xValue);
      if (nextIndex >= 0) setSliderValue(nextIndex);
    };

    chart.off("dataZoom", commitZoom);
    chart.off("finished", commitZoom);
    zr.off("click", handleClick);
    chart.on("dataZoom", commitZoom);
    chart.on("finished", commitZoom);
    zr.on("click", handleClick);
    return () => {
      chart.off("dataZoom", commitZoom);
      chart.off("finished", commitZoom);
      zr.off("click", handleClick);
    };
  }, [
    chartModel.series,
    computePixelPoint,
    getChartInstance,
    pendingLabelMode,
    runTimestamps,
    selectedLabelTraceKeys,
    setSliderValue,
  ]);

  useEffect(() => {
    const handlePointerMove = (event) => {
      const dragState = draggingLabelRef.current;
      if (!dragState) return;
      const nextDx =
        dragState.startDx + (event.clientX - dragState.startClientX);
      const nextDy =
        dragState.startDy + (event.clientY - dragState.startClientY);
      setRunLabels((prev) =>
        prev.map((label) =>
          label.id === dragState.labelId
            ? {
                ...label,
                dx: nextDx,
                dy: nextDy,
                updatedAt: new Date().toISOString(),
              }
            : label,
        ),
      );
    };
    const handlePointerUp = () => {
      draggingLabelRef.current = null;
    };
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, []);

  const toggleSensor = (sensorKey) =>
    setSelectedSensorKeys((prev) =>
      prev.includes(sensorKey)
        ? prev.filter((id) => id !== sensorKey)
        : [...prev, sensorKey],
    );
  const toggleTrace = (label) =>
    setTraceVisibility((prev) => ({
      ...prev,
      [label]: !(prev[label] ?? true),
    }));
  const toggleLabelTraceSelection = (traceKey) =>
    setSelectedLabelTraceKeys((prev) =>
      prev.includes(traceKey)
        ? prev.filter((key) => key !== traceKey)
        : [...prev, traceKey],
    );
  const beginAddSingleLabel = () => {
    if (selectedLabelTraceKeys.length === 0) return;
    setActiveLabelId(null);
    setLabelDraftText("");
    setPendingLabelMode("single");
  };
  const beginAddRangeLabel = () => {
    if (selectedLabelTraceKeys.length === 0) return;
    setActiveLabelId(null);
    setLabelDraftText("");
    selectionDragRef.current = null;
    selectionBoxRef.current = null;
    setSelectionBox(null);
    setPendingLabelMode("range");
  };
  const cancelAddLabel = () => {
    setPendingLabelMode(null);
    selectionDragRef.current = null;
    selectionBoxRef.current = null;
    setSelectionBox(null);
  };
  const updateLabelText = (labelId, text) =>
    setRunLabels((prev) =>
      prev.map((label) =>
        label.id === labelId
          ? { ...label, text, updatedAt: new Date().toISOString() }
          : label,
      ),
    );
  const updateLabelColor = (labelId, color) =>
    setRunLabels((prev) =>
      prev.map((label) =>
        label.id === labelId
          ? { ...label, color, updatedAt: new Date().toISOString() }
          : label,
      ),
    );
  const deleteLabel = (labelId) => {
    setRunLabels((prev) => prev.filter((label) => label.id !== labelId));
    if (activeLabelId === labelId) {
      setActiveLabelId(null);
      setLabelDraftText("");
    }
  };
  const commitDraftToActiveLabel = () => {
    if (activeLabelId) {
      updateLabelText(activeLabelId, labelDraftText);
      updateLabelColor(activeLabelId, labelDraftColor);
    }
  };
  const updateLabelRange = (labelId, field, rawValue) => {
    const nextValue = Number(rawValue);
    if (!Number.isFinite(nextValue)) return;

    setRunLabels((prev) =>
      prev.map((label) => {
        if (label.id !== labelId || label.kind !== "range") return label;
        const nextLabel = rebuildRangeLabel(
          label,
          label.traceKeys,
          field === "startTimestamp" ? nextValue : label.startTimestamp,
          field === "endTimestamp" ? nextValue : label.endTimestamp,
          seriesByTraceKey,
        );
        return nextLabel || label;
      }),
    );
  };
  const toggleActiveLabelTrace = (traceKey) => {
    if (!activeLabel) return;

    const nextTraceKeys = activeLabel.traceKeys.includes(traceKey)
      ? activeLabel.traceKeys.filter((key) => key !== traceKey)
      : [...activeLabel.traceKeys, traceKey];

    if (nextTraceKeys.length === 0) return;

    setRunLabels((prev) =>
      prev.map((label) => {
        if (label.id !== activeLabel.id) return label;
        const nextLabel =
          label.kind === "range"
            ? rebuildRangeLabel(
                label,
                nextTraceKeys,
                label.startTimestamp,
                label.endTimestamp,
                seriesByTraceKey,
              )
            : rebuildSingleLabel(label, nextTraceKeys, seriesByTraceKey);
        return nextLabel || label;
      }),
    );
  };
  const toggleFilter = (filterId) =>
    setPendingFilters((prev) =>
      prev.includes(filterId)
        ? prev.filter((id) => id !== filterId)
        : [...prev, filterId],
    );
  const applyFilters = () => {
    setSelectedFilters(pendingFilters);
    setUseFilteredData(true);
  };
  const disableFilters = () => {
    setUseFilteredData(false);
    setPendingFilters(selectedFilters);
  };
  const handleDragStart = (event, filterId) => {
    setDraggedFilter(filterId);
    event.dataTransfer.effectAllowed = "move";
  };
  const handleDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  };
  const handleDrop = (event, targetFilterId) => {
    event.preventDefault();
    if (draggedFilter === targetFilterId) return;
    setPendingFilters((prev) => {
      const next = [...prev];
      const draggedIndex = next.indexOf(draggedFilter);
      const targetIndex = next.indexOf(targetFilterId);
      if (draggedIndex === -1 || targetIndex === -1) return prev;
      next.splice(draggedIndex, 1);
      next.splice(targetIndex, 0, draggedFilter);
      return next;
    });
    setDraggedFilter(null);
  };
  const handleDragEnd = () => setDraggedFilter(null);
  const handleSyncOffsetChange = (sensorId, value) => {
    const parsed = Number(value);
    setSensorSyncOffsets((prev) => ({
      ...prev,
      [sensorId]: Number.isFinite(parsed) ? parsed : 0,
    }));
  };
  const nudgeSyncOffset = (sensorId, delta) =>
    setSensorSyncOffsets((prev) => ({
      ...prev,
      [sensorId]: getSensorOffset(prev, sensorId) + delta,
    }));
  const resetAllSyncOffsets = () =>
    setSensorSyncOffsets(
      Object.fromEntries(selectedSensorKeys.map((sensorKey) => [sensorKey, 0])),
    );
  const resetZoom = () => {
    const nextRange = getInitialRange(selectedRun);
    setVisibleRange(nextRange);
    const chart = getChartInstance();
    if (chart)
      chart.dispatchAction({
        type: "dataZoom",
        startValue: nextRange.start,
        endValue: nextRange.end,
      });
  };
  const handleLabelPointerDown = (event, labelId) => {
    event.preventDefault();
    event.stopPropagation();
    const label = runLabels.find((entry) => entry.id === labelId);
    if (!label) return;
    setActiveLabelId(labelId);
    setLabelDraftText(label.text || "");
    draggingLabelRef.current = {
      labelId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startDx: label.dx,
      startDy: label.dy,
    };
  };
  const buildLabelReadingCount = useCallback(
    (label) =>
      Array.isArray(label.points) && label.points.length > 0
        ? label.points.length
        : label.traceKeys.reduce((total, traceKey) => {
            const seriesItem = seriesByTraceKey.get(traceKey);
            if (!seriesItem) return total;
            return (
              total +
              seriesItem.points.filter(
                (point) =>
                  point.x >= label.startTimestamp &&
                  point.x <= label.endTimestamp,
              ).length
            );
          }, 0),
    [seriesByTraceKey],
  );
  const buildGroupLabelFromSelection = useCallback(
    (selection) => {
      if (!selection) return null;
      const selectedPoints = chartModel.series
        .filter((seriesItem) =>
          selectedLabelTraceKeys.includes(seriesItem.traceKey),
        )
        .flatMap((seriesItem) =>
          seriesItem.points
            .map((point) => {
              const pixel = computePixelPoint(point.x, point.y);
              if (
                !pixel ||
                pixel.left < selection.left ||
                pixel.left > selection.left + selection.width ||
                pixel.top < selection.top ||
                pixel.top > selection.top + selection.height
              )
                return null;
              return {
                traceKey: seriesItem.traceKey,
                timestamp: point.x,
                yValue: point.y,
              };
            })
            .filter(Boolean),
        );
      if (selectedPoints.length === 0) return null;
      const orderedPoints = [...selectedPoints].sort(
        (left, right) => left.timestamp - right.timestamp,
      );
      const firstPoint = orderedPoints[0];
      const timestamps = selectedPoints.map((point) => point.timestamp);
      return normalizeLabel({
        id: createLabelId(),
        kind: "range",
        text: "",
        color: "#0d6efd",
        traceKeys: [...new Set(selectedPoints.map((point) => point.traceKey))],
        points: [],
        startTimestamp: Math.min(...timestamps),
        endTimestamp: Math.max(...timestamps),
        anchorTimestamp: firstPoint.timestamp,
        anchorY: firstPoint.yValue,
        dx: 0,
        dy: 0,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      });
    },
    [chartModel.series, computePixelPoint, selectedLabelTraceKeys],
  );
  const analyzeHighlightSections = useCallback(() => {
    if (selectedSensorEntries.length === 0) return;

    const sourceEntry = selectedSensorEntries[0];
    const sourceReadings = sourceEntry.isPrimary
      ? rawSeriesBySensor[sourceEntry.sensorId]
      : comparisonRawSeriesByRun[sourceEntry.runId]?.[sourceEntry.sensorId];

    if (!Array.isArray(sourceReadings) || sourceReadings.length === 0) return;

    const currentBaseTimestamp = selectedRun?.totalTimestamps?.[0];
    const entryBaseTimestamp = sourceEntry.isPrimary
      ? currentBaseTimestamp
      : comparisonRuns.find((run) => run._id === sourceEntry.runId)
          ?.totalTimestamps?.[0];
    const alignmentOffset =
      !sourceEntry.isPrimary &&
      Number.isFinite(currentBaseTimestamp) &&
      Number.isFinite(entryBaseTimestamp)
        ? currentBaseTimestamp - entryBaseTimestamp
        : 0;
    const syncOffset =
      getSensorOffset(sensorSyncOffsets, sourceEntry.key) + alignmentOffset;
    const sections = buildHighlightSectionsFromReadings(
      sourceReadings,
      syncOffset,
    );

    if (sections.length === 0) return;

    const targetTraceKeys =
      selectedLabelTraceKeys.length > 0
        ? new Set(selectedLabelTraceKeys)
        : new Set(chartModel.series.map((seriesItem) => seriesItem.traceKey));
    const targetSeries = chartModel.series.filter((seriesItem) =>
      targetTraceKeys.has(seriesItem.traceKey),
    );

    if (targetSeries.length === 0) return;

    const nextLabels = sections
      .map((section, index) =>
        buildRangeLabelFromSection({
          section,
          sectionIndex: index,
          sourceEntryKey: sourceEntry.key,
          seriesItems: targetSeries,
        }),
      )
      .filter(Boolean);

    if (nextLabels.length === 0) return;

    setShowHighlightSections(true);
    setPendingLabelMode(null);
    setSelectionBox(null);
    setRunLabels((prev) => {
      const nextById = new Map(nextLabels.map((label) => [label.id, label]));
      const preserved = prev.filter((label) => !nextById.has(label.id));
      return [...preserved, ...nextLabels].sort(
        (left, right) => left.startTimestamp - right.startTimestamp,
      );
    });
    setActiveLabelId(nextLabels[0].id);
  }, [
    chartModel.series,
    comparisonRawSeriesByRun,
    comparisonRuns,
    rawSeriesBySensor,
    selectedLabelTraceKeys,
    selectedRun,
    selectedSensorEntries,
    sensorSyncOffsets,
  ]);
  const addComparisonRun = async () => {
    if (
      !comparisonRunId ||
      comparisonRuns.some((run) => run._id === comparisonRunId)
    )
      return;
    try {
      const run = await fetchRun(comparisonRunId);
      setComparisonRuns((prev) => [...prev, run]);
      setComparisonRunId("");
    } catch (error) {
      console.error("Error loading comparison run:", error);
    }
  };
  const removeComparisonRun = (runId) => {
    setComparisonRuns((prev) => prev.filter((run) => run._id !== runId));
    setComparisonSensorsByRun((prev) => {
      const next = { ...prev };
      delete next[runId];
      return next;
    });
    setComparisonPlotSeriesByRun((prev) => {
      const next = { ...prev };
      delete next[runId];
      return next;
    });
    setComparisonRawSeriesByRun((prev) => {
      const next = { ...prev };
      delete next[runId];
      return next;
    });
    setSelectedSensorKeys((prev) =>
      prev.filter((key) => !key.startsWith(`${runId}:`)),
    );
    setSensorSyncOffsets((prev) =>
      Object.fromEntries(
        Object.entries(prev).filter(([key]) => !key.startsWith(`${runId}:`)),
      ),
    );
  };
  const handleSelectionStart = (event) => {
    if (pendingLabelMode !== "range" || selectedLabelTraceKeys.length === 0)
      return;
    const bounds = chartContainerRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const startX = event.clientX - bounds.left;
    const startY = event.clientY - bounds.top;
    selectionDragRef.current = { startX, startY };
    const nextSelectionBox = { left: startX, top: startY, width: 0, height: 0 };
    selectionBoxRef.current = nextSelectionBox;
    setSelectionBox(nextSelectionBox);
  };
  const handleSelectionMove = (event) => {
    if (pendingLabelMode !== "range" || !selectionDragRef.current) return;
    const bounds = chartContainerRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const currentX = event.clientX - bounds.left;
    const currentY = event.clientY - bounds.top;
    const { startX, startY } = selectionDragRef.current;
    const nextSelectionBox = {
      left: Math.min(startX, currentX),
      top: Math.min(startY, currentY),
      width: Math.abs(currentX - startX),
      height: Math.abs(currentY - startY),
    };
    selectionBoxRef.current = nextSelectionBox;
    setSelectionBox(nextSelectionBox);
  };
  const handleSelectionEnd = () => {
    if (pendingLabelMode !== "range" || !selectionDragRef.current) return;
    const nextLabel = buildGroupLabelFromSelection(selectionBoxRef.current);
    selectionDragRef.current = null;
    selectionBoxRef.current = null;
    setSelectionBox(null);
    setPendingLabelMode(null);
    if (nextLabel) {
      setRunLabels((prev) => [...prev, nextLabel]);
      setActiveLabelId(nextLabel.id);
      setLabelDraftText("");
    }
  };

  return (
    <div className="uplot-prototype">
      <div className="uplot-prototype__header">
        <div>
          <strong>Sensor Graph</strong>
        </div>
        <button
          type="button"
          className="btn btn-sm btn-outline-danger"
          onClick={removeFunction}
        >
          Remove
        </button>
      </div>
      {(isPlotLoading || isRawLoading) && selectedSensorEntries.length > 0 && (
        <div className="alert alert-info py-2 px-3 mb-3">
          {isPlotLoading ? "Updating plot data..." : "Syncing sensor data..."}
        </div>
      )}
      <div className="uplot-prototype__chart-shell">
        <div className="uplot-prototype__chart-toolbar">
          <button
            type="button"
            className={`btn btn-sm ${isConfigOpen ? "btn-primary" : "btn-outline-primary"}`}
            onClick={() => setIsConfigOpen((prev) => !prev)}
          >
            Config
          </button>
          <button
            type="button"
            className="btn btn-sm btn-outline-primary"
            onClick={resetZoom}
          >
            Reset Zoom
          </button>
          <button
            type="button"
            className={`btn btn-sm ${independentScales ? "btn-success" : "btn-outline-secondary"}`}
            onClick={() => setIndependentScales((prev) => !prev)}
            title="Scale each series independently so patterns are comparable regardless of magnitude"
          >
            Ind. Scale
          </button>
        </div>
        <div
          className={`uplot-prototype__overlay-controls ${isConfigOpen ? "is-open" : ""}`}
        >
          <div className="plot-configuration">
          <details className="card sensors-collapsible" open>
            <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
              <strong>Sensors</strong>
              <span className="badge bg-secondary">
                {selectedSensorKeys.length} / {availableSensorEntries.length}
              </span>
            </summary>
            <div className="card-body">
              <div className="list-group">
                {availableSensorEntries.map((entry) => (
                  <label
                    key={entry.key}
                    className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center ${selectedSensorKeys.includes(entry.key) ? "active" : ""}`}
                  >
                    <div className="form-check d-flex align-items-center m-0">
                      <input
                        className="form-check-input me-2"
                        type="checkbox"
                        checked={selectedSensorKeys.includes(entry.key)}
                        onChange={() => toggleSensor(entry.key)}
                      />
                      <span className="form-check-label">
                        {entry.runName} - {getSensorDisplayLabel(entry)}
                      </span>
                    </div>
                    {/* <small className="text-muted">ID: {entry.sensorId}</small> */}
                  </label>
                ))}
              </div>
            </div>
          </details>
          <details className="card sync-collapsible">
            <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
              <strong>Synchronization</strong>
              <span className="badge bg-secondary">
                {selectedSensorEntries.filter((entry) => getSensorOffset(sensorSyncOffsets, entry.key) !== 0).length} shifted
              </span>
            </summary>
            <div className="card-body">
              {selectedSensorEntries.map((entry) => (
                <div key={entry.key} className="sync-offset-row">
                  <div>
                    <strong>
                      {entry.runName} {getSensorDisplayLabel(entry)}
                    </strong>
                  </div>
                  <div className="sync-offset-controls">
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-secondary"
                      onClick={() => nudgeSyncOffset(entry.key, -1)}
                    >
                      -1
                    </button>
                    <input
                      type="number"
                      step="any"
                      className="form-control form-control-sm sync-offset-input"
                      value={getSensorOffset(sensorSyncOffsets, entry.key)}
                      onChange={(event) =>
                        handleSyncOffsetChange(entry.key, event.target.value)
                      }
                    />
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-secondary"
                      onClick={() => nudgeSyncOffset(entry.key, 1)}
                    >
                      +1
                    </button>
                  </div>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-sm btn-outline-danger mt-3"
                onClick={resetAllSyncOffsets}
              >
                Reset All Offsets
              </button>
            </div>
          </details>
          <details className="card filters-collapsible">
            <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
              <strong>Filters</strong>
              <span className={`badge ${useFilteredData ? "bg-success" : "bg-secondary"}`}>
                {useFilteredData ? "Active" : "Inactive"} ({pendingFilters.length} selected)
              </span>
            </summary>
            <div className="card-body">
              {FILTERS.map((filter) => (
                <label
                  key={filter.id}
                  className="list-group-item list-group-item-action d-flex align-items-center"
                >
                  <input
                    className="form-check-input me-2"
                    type="checkbox"
                    checked={pendingFilters.includes(filter.id)}
                    onChange={() => toggleFilter(filter.id)}
                  />
                  <span>{filter.label}</span>
                </label>
              ))}
              <div className="d-flex gap-2 mt-3">
                {useFilteredData ? (
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger flex-fill"
                    onClick={disableFilters}
                  >
                    Disable Filters
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-primary flex-fill"
                    onClick={applyFilters}
                    disabled={pendingFilters.length === 0}
                  >
                    Apply Filters
                  </button>
                )}
              </div>
            </div>
          </details>
          <details className="card">
            <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
              <strong>Compare Runs</strong>
              <span className="badge bg-secondary">{comparisonRuns.length} overlayed</span>
            </summary>
            <div className="card-body">
              <div className="uplot-prototype__compare-controls">
                <select
                  className="form-select form-select-sm"
                  value={comparisonRunId}
                  onChange={(event) => setComparisonRunId(event.target.value)}
                >
                  <option value="">Select run to overlay</option>
                  {availableRuns
                    .filter(
                      (run) =>
                        run._id !== selectedRun?._id &&
                        !comparisonRuns.some((item) => item._id === run._id),
                    )
                    .map((run) => (
                      <option key={run._id} value={run._id}>
                        {run.name || `Run ${run._id}`}
                      </option>
                    ))}
                </select>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-primary"
                  onClick={addComparisonRun}
                  disabled={!comparisonRunId}
                >
                  Add Overlay
                </button>
              </div>
              {comparisonRuns.length > 0 && (
                <div className="list-group mt-3">
                  {comparisonRuns.map((run) => (
                    <div
                      key={run._id}
                      className="list-group-item d-flex justify-content-between align-items-center"
                    >
                      <span>{run.name || `Run ${run._id}`}</span>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => removeComparisonRun(run._id)}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
          <details className="card" open>
            <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
              <strong>Labels</strong>
              <span className={`badge ${pendingLabelMode ? "bg-primary" : "bg-secondary"}`}>
                {runLabels.length} saved
              </span>
            </summary>
            <div className="card-body">
              <label className="list-group-item list-group-item-action d-flex align-items-center mb-3">
                <input
                  className="form-check-input me-2"
                  type="checkbox"
                  checked={showLabels}
                  onChange={(event) => setShowLabels(event.target.checked)}
                />
                <span>Show labels on graph</span>
              </label>
              <div className="list-group mb-3">
                {chartModel.series.map((seriesItem) => (
                  <label
                    key={seriesItem.traceKey}
                    className="list-group-item list-group-item-action d-flex align-items-center"
                  >
                    <input
                      className="form-check-input me-2"
                      type="checkbox"
                      checked={selectedLabelTraceKeys.includes(
                        seriesItem.traceKey,
                      )}
                      onChange={() =>
                        toggleLabelTraceSelection(seriesItem.traceKey)
                      }
                    />
                    <span>{seriesItem.label}</span>
                  </label>
                ))}
              </div>
              <div className="d-flex gap-2 mb-3">
                <button
                  type="button"
                  className={`btn btn-sm ${pendingLabelMode === "single" ? "btn-primary" : "btn-outline-primary"} flex-fill`}
                  disabled={selectedLabelTraceKeys.length === 0}
                  onClick={
                    pendingLabelMode === "single"
                      ? cancelAddLabel
                      : beginAddSingleLabel
                  }
                >
                  {pendingLabelMode === "single"
                    ? "Click Graph For Reading"
                    : "Single Reading"}
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${pendingLabelMode === "range" ? "btn-primary" : "btn-outline-primary"} flex-fill`}
                  disabled={selectedLabelTraceKeys.length === 0}
                  onClick={
                    pendingLabelMode === "range"
                      ? cancelAddLabel
                      : beginAddRangeLabel
                  }
                >
                  {pendingLabelMode === "range"
                    ? "Drag Box On Graph"
                    : "Group Selected Points"}
                </button>
              </div>
              {activeLabel && (
                <div className="uplot-prototype__label-editor mb-3">
                  <label className="form-label mb-1">Label text</label>
                  <textarea
                    className="form-control form-control-sm"
                    rows={3}
                    value={labelDraftText}
                    onChange={(event) => setLabelDraftText(event.target.value)}
                    onBlur={commitDraftToActiveLabel}
                  />
                  <label className="form-label mb-1 mt-2">Label color</label>
                  <input
                    className="form-control form-control-color form-control-sm"
                    type="color"
                    value={labelDraftColor}
                    onChange={(event) => setLabelDraftColor(event.target.value)}
                    onBlur={commitDraftToActiveLabel}
                  />
                  {activeLabel.kind === "range" && (
                    <div className="row g-2 mt-2">
                      <div className="col-6">
                        <label className="form-label mb-1">Start timestamp</label>
                        <input
                          className="form-control form-control-sm"
                          type="number"
                          step="any"
                          value={activeLabel.startTimestamp}
                          onChange={(event) =>
                            updateLabelRange(
                              activeLabel.id,
                              "startTimestamp",
                              event.target.value,
                            )
                          }
                        />
                      </div>
                      <div className="col-6">
                        <label className="form-label mb-1">End timestamp</label>
                        <input
                          className="form-control form-control-sm"
                          type="number"
                          step="any"
                          value={activeLabel.endTimestamp}
                          onChange={(event) =>
                            updateLabelRange(
                              activeLabel.id,
                              "endTimestamp",
                              event.target.value,
                            )
                          }
                        />
                      </div>
                    </div>
                  )}
                  <div className="mt-3">
                    <label className="form-label mb-1">Traces in label</label>
                    <div className="list-group">
                      {chartModel.series.map((seriesItem) => (
                        <label
                          key={`active-label-${seriesItem.traceKey}`}
                          className="list-group-item list-group-item-action d-flex align-items-center"
                        >
                          <input
                            className="form-check-input me-2"
                            type="checkbox"
                            checked={activeLabel.traceKeys.includes(
                              seriesItem.traceKey,
                            )}
                            onChange={() =>
                              toggleActiveLabelTrace(seriesItem.traceKey)
                            }
                            disabled={
                              activeLabel.traceKeys.length === 1 &&
                              activeLabel.traceKeys.includes(
                                seriesItem.traceKey,
                              )
                            }
                          />
                          <span>{seriesItem.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="d-flex gap-2 mt-2">
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-primary"
                      onClick={commitDraftToActiveLabel}
                    >
                      Save Label
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-danger"
                      onClick={() => deleteLabel(activeLabel.id)}
                    >
                      Delete Label
                    </button>
                  </div>
                </div>
              )}
              <div className="list-group">
                {runLabels.map((label) => (
                  <button
                    key={label.id}
                    type="button"
                    className={`list-group-item list-group-item-action text-start ${activeLabelId === label.id ? "active" : ""}`}
                    onClick={() => setActiveLabelId(label.id)}
                  >
                    <div className="d-flex justify-content-between align-items-center gap-2">
                      <span>{label.text?.trim() || "Untitled label"}</span>
                      <span
                        className="badge"
                        style={{ backgroundColor: label.color || "#0d6efd" }}
                      >
                        {label.kind === "range" ? "Range" : "Single"}
                      </span>
                    </div>
                    <small className="text-muted d-block mt-1">
                      {buildLabelReadingCount(label)} readings across{" "}
                      {label.traceKeys.length} trace
                      {label.traceKeys.length === 1 ? "" : "s"}
                    </small>
                  </button>
                ))}
              </div>
            </div>
          </details>
          <details className="card">
            <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
              <strong>Highlights</strong>
              <span className={`badge ${showHighlightSections ? "bg-success" : "bg-secondary"}`}>
                {showHighlightSections ? "On" : "Off"}
              </span>
            </summary>
            <div className="card-body">
              <label className="list-group-item list-group-item-action d-flex align-items-center">
                <input
                  className="form-check-input me-2"
                  type="checkbox"
                  checked={showHighlightSections}
                  onChange={(event) =>
                    setShowHighlightSections(event.target.checked)
                  }
                />
                <span>Show green/red highlight sections</span>
              </label>
              <button
                type="button"
                className="btn btn-sm btn-outline-primary mt-3 w-100"
                onClick={analyzeHighlightSections}
                disabled={
                  selectedSensorEntries.length === 0 ||
                  chartModel.series.length === 0
                }
              >
                Analyze Highlights To Labels
              </button>
            </div>
          </details>
          <details className="card traces-collapsible">
            <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
              <strong>Traces</strong>
              <span className="badge bg-secondary">
                {chartModel.series.filter((seriesItem) => traceVisibility[seriesItem.label] ?? true).length} visible
              </span>
            </summary>
            <div className="card-body">
              <div className="list-group">
                {chartModel.series.map((seriesItem) => (
                  <label
                    key={seriesItem.label}
                    className={`list-group-item list-group-item-action d-flex align-items-center ${(traceVisibility[seriesItem.label] ?? true) ? "" : "text-muted"}`}
                  >
                    <input
                      className="form-check-input me-2"
                      type="checkbox"
                      checked={traceVisibility[seriesItem.label] ?? true}
                      onChange={() => toggleTrace(seriesItem.label)}
                    />
                    <span>{seriesItem.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </details>
          </div>
        </div>
        <div ref={chartContainerRef} className="uplot-prototype__chart" />
        <div
          className="uplot-prototype__interaction-layer"
          style={{
            pointerEvents: pendingLabelMode === "range" ? "auto" : "none",
          }}
          onMouseDown={handleSelectionStart}
          onMouseMove={handleSelectionMove}
          onMouseUp={handleSelectionEnd}
          onMouseLeave={handleSelectionEnd}
        >
          {showLabels &&
            labelPointMarkers.map((point) => (
              <div
                key={point.id}
                className="uplot-prototype__label-point"
                style={{
                  left: `${point.left}px`,
                  top: `${point.top}px`,
                  background: point.color,
                  boxShadow: `0 0 0 1px ${point.color}33`,
                }}
              />
            ))}
          {pendingLabelMode === "range" && selectionBox && (
            <div
              className="uplot-prototype__selection-box"
              style={{
                left: `${selectionBox.left}px`,
                top: `${selectionBox.top}px`,
                width: `${selectionBox.width}px`,
                height: `${selectionBox.height}px`,
              }}
            />
          )}
        </div>
        <div
          className="uplot-prototype__interaction-layer"
          style={{ pointerEvents: "none" }}
        >
          {showLabels &&
            labelRenderItems.map((label) => (
              <div key={label.id}>
                <button
                  type="button"
                  className={`uplot-prototype__label ${activeLabelId === label.id ? "is-active" : ""} ${label.allHidden ? "is-dimmed" : ""}`}
                  style={{
                    left: `${label.titleLeft}px`,
                    top: `${label.titleTop}px`,
                    pointerEvents: "auto",
                    minWidth: "0",
                    maxWidth: "140px",
                    padding: "4px 8px",
                    transform: "none",
                    borderColor: label.color,
                    color: "#0f172a",
                  }}
                  onPointerDown={(event) =>
                    handleLabelPointerDown(event, label.id)
                  }
                  onClick={(event) => {
                    event.stopPropagation();
                    setActiveLabelId(label.id);
                  }}
                >
                  <span
                    className="uplot-prototype__label-kind"
                    style={{ color: label.color }}
                  >
                  </span>
                  <span>{label.text?.trim() || "Untitled label"}</span>
                </button>
              </div>
            ))}
        </div>
        {sliderReadout.length > 0 && (
          <div className="uplot-prototype__readout">
            {sliderReadout.map((entry) => (
              <div
                key={`${entry.runId}:${entry.sensorId}`}
                className="uplot-prototype__readout-item"
              >
                <strong>{entry.runName} - </strong>
                <strong>{getSensorDisplayLabel(entry)}</strong>
                <span>Timeline: {entry.timelineTimestamp}</span>
                <span>Sensor: {entry.sensorTimestamp}</span>
                {entry.shift !== 0 && (
                  <span>
                    Shift: {entry.shift >= 0 ? "+" : ""}
                    {entry.shift}
                  </span>
                )}
                {entry.axes.map((axis) => (
                  <span
                    key={`${entry.runId}:${entry.sensorId}:${axis.name}`}
                    className="uplot-prototype__readout-axis"
                    style={{ "--trace-color": axis.color }}
                  >
                    <span className="uplot-prototype__readout-swatch" />
                    {axis.name}: {axis.value}
                  </span>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
