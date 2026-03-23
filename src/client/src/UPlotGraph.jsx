import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import "./UPlotGraph.css";
import { fetchRuns } from "./api";

const SERVER_URL = import.meta.env.VITE_SERVER_URL;
const ACCESS_TOKEN_STORAGE_KEY = "vppsports_access_token";
const DEFAULT_PLOT_RESOLUTION = 1400;

const FILTERS = [
  { id: "kalman", label: "Kalman" },
  { id: "movingaverage", label: "MovAvg" },
  { id: "savitzkygolay", label: "SavGol" },
];

const TRACE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#17becf", "#8c564b"];

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

const fetchRunSensors = async (runId) => fetchJson(`${SERVER_URL}/run/${runId}/sensor`);
const fetchRun = async (runId) => fetchJson(`${SERVER_URL}/run/${runId}`);

const buildSensorDataUrl = (runId, sensorId, options = {}) => {
  const params = new URLSearchParams();
  if (options.filters) params.set("filters", options.filters);
  if (options.mode) params.set("mode", options.mode);
  if (Number.isFinite(options.start)) params.set("start", String(options.start));
  if (Number.isFinite(options.end)) params.set("end", String(options.end));
  if (Number.isFinite(options.resolution)) {
    params.set("resolution", String(options.resolution));
  }

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
  if (!Array.isArray(timestamps) || timestamps.length === 0 || !Number.isFinite(target)) {
    return -1;
  }

  let lo = 0;
  let hi = timestamps.length - 1;

  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (timestamps[mid] < target) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
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
    if (readings[mid].timestamp < target) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }

  if (lo === 0) return readings[0];
  const current = readings[lo];
  const previous = readings[lo - 1];
  if (!current) return previous ?? null;
  return Math.abs(current.timestamp - target) < Math.abs(previous.timestamp - target)
    ? current
    : previous;
};

const interpolateSeriesValue = (points, target) => {
  if (!Array.isArray(points) || points.length === 0 || !Number.isFinite(target)) return null;

  let lo = 0;
  let hi = points.length - 1;

  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (points[mid].x < target) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
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

const UPlotGraph = ({ selectedRun, sliderValue, setSliderValue, removeFunction }) => {
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
  const [localSliderValue, setLocalSliderValue] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showHighlightSections, setShowHighlightSections] = useState(false);
  const [availableRuns, setAvailableRuns] = useState([]);
  const [comparisonRunId, setComparisonRunId] = useState("");
  const [comparisonRuns, setComparisonRuns] = useState([]);
  const [comparisonSensorsByRun, setComparisonSensorsByRun] = useState({});
  const [comparisonPlotSeriesByRun, setComparisonPlotSeriesByRun] = useState({});
  const [comparisonRawSeriesByRun, setComparisonRawSeriesByRun] = useState({});

  const chartContainerRef = useRef(null);
  const interactionLayerRef = useRef(null);
  const plotInstanceRef = useRef(null);
  const requestIdRef = useRef({ plot: 0, raw: 0, comparisonPlot: 0, comparisonRaw: 0 });
  const cacheRef = useRef({ plot: new Map(), raw: new Map() });
  const cursorTimestampRef = useRef(0);
  const zoomCommitTimeoutRef = useRef(null);
  const panStateRef = useRef({
    active: false,
    moved: false,
    startClientX: 0,
    min: 0,
    max: 0,
  });
  const [visibleRange, setVisibleRange] = useState(() => getInitialRange(selectedRun));
  const filterKey = filterKeyFromSelection(useFilteredData, selectedFilters);
  const runTimestamps = selectedRun?.totalTimestamps ?? [];
  const maxSliderIndex = Math.max(runTimestamps.length - 1, 0);
  const currentTimestamp = runTimestamps[localSliderValue] ?? runTimestamps[0] ?? 0;
  const currentRunName = selectedRun?.name || `Run ${selectedRun?._id}`;
  const availableSensorEntries = useMemo(() => {
    const currentEntries = (availableSensors || []).map((sensorId) => ({
      key: `${selectedRun?._id}:${sensorId}`,
      runId: selectedRun?._id,
      runName: currentRunName,
      sensorId,
      isPrimary: true,
    }));

    const comparisonEntries = comparisonRuns.flatMap((run) =>
      (comparisonSensorsByRun[run._id] || []).map((sensorId) => ({
        key: `${run._id}:${sensorId}`,
        runId: run._id,
        runName: run.name || `Run ${run._id}`,
        sensorId,
        isPrimary: false,
      }))
    );

    return [...currentEntries, ...comparisonEntries];
  }, [availableSensors, comparisonRuns, comparisonSensorsByRun, currentRunName, selectedRun?._id]);
  const selectedSensorEntries = useMemo(
    () => availableSensorEntries.filter((entry) => selectedSensorKeys.includes(entry.key)),
    [availableSensorEntries, selectedSensorKeys]
  );
  const primarySelectedSensorIds = useMemo(
    () => selectedSensorEntries.filter((entry) => entry.isPrimary).map((entry) => entry.sensorId),
    [selectedSensorEntries]
  );
  const comparisonSelectedEntriesByRun = useMemo(() => {
    return selectedSensorEntries
      .filter((entry) => !entry.isPrimary)
      .reduce((acc, entry) => {
        if (!acc[entry.runId]) acc[entry.runId] = [];
        acc[entry.runId].push(entry);
        return acc;
      }, {});
  }, [selectedSensorEntries]);

  useEffect(() => {
    cursorTimestampRef.current = currentTimestamp;
    if (plotInstanceRef.current) {
      plotInstanceRef.current.redraw();
    }
  }, [currentTimestamp]);

  useEffect(() => () => {
    if (zoomCommitTimeoutRef.current !== null) {
      window.clearTimeout(zoomCommitTimeoutRef.current);
    }
  }, []);

  useEffect(() => () => {
  }, []);

  useEffect(() => {
    const handleResize = () => setPlotResolution(getPlotResolution());
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    cacheRef.current = { plot: new Map(), raw: new Map() };
    requestIdRef.current = { plot: 0, raw: 0, comparisonPlot: 0, comparisonRaw: 0 };
    setPlotSeriesBySensor({});
    setRawSeriesBySensor({});
    setSelectedSensorKeys([]);
    setSensorSyncOffsets({});
    setTraceVisibility({});
    setSliderReadout([]);
    setLocalSliderValue(0);
    setIsPlaying(false);
    setShowHighlightSections(false);
    setVisibleRange(getInitialRange(selectedRun));
    setComparisonRunId("");
    setComparisonRuns([]);
    setComparisonSensorsByRun({});
    setComparisonPlotSeriesByRun({});
    setComparisonRawSeriesByRun({});
  }, [selectedRun?._id]);

  useEffect(() => {
    fetchRuns()
      .then((runs) => setAvailableRuns(Array.isArray(runs) ? runs : []))
      .catch((error) => {
        console.error("Error loading runs for comparison:", error);
        setAvailableRuns([]);
      });
  }, []);

  useEffect(() => {
    if (!isPlaying) {
      setLocalSliderValue(sliderValue);
    }
  }, [isPlaying, sliderValue]);

  useEffect(() => {
    const loadAvailableSensors = async () => {
      if (!selectedRun?._id) return;

      try {
        const sensors = await fetchRunSensors(selectedRun._id);
        setAvailableSensors(sensors);
      } catch (error) {
        console.error("Error loading available sensors:", error);
      }
    };

    loadAvailableSensors();
  }, [selectedRun?._id]);

  useEffect(() => {
    setSensorSyncOffsets((prev) =>
      Object.fromEntries(selectedSensorKeys.map((sensorKey) => [sensorKey, getSensorOffset(prev, sensorKey)]))
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
          comparisonRuns.map(async (run) => [run._id, await fetchRunSensors(run._id)])
        );
        setComparisonSensorsByRun(Object.fromEntries(entries));
      } catch (error) {
        console.error("Error loading comparison run sensors:", error);
      }
    };

    loadComparisonSensors();
  }, [comparisonRuns]);

  useEffect(() => {
    const requestId = ++requestIdRef.current.comparisonPlot;

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
        })
      );

      if (requestId !== requestIdRef.current.plot) return;
      setPlotSeriesBySensor(Object.fromEntries(nextEntries));
      setIsPlotLoading(false);
    };

    loadPlotSeries().catch((error) => {
      if (requestId === requestIdRef.current.plot) {
        setIsPlotLoading(false);
      }
      console.error("Error loading uPlot plot data:", error);
    });
  }, [filterKey, plotResolution, primarySelectedSensorIds, selectedRun?._id, visibleRange.end, visibleRange.start]);

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
        })
      );

      if (requestId !== requestIdRef.current.raw) return;
      setRawSeriesBySensor(Object.fromEntries(nextEntries));
      setIsRawLoading(false);
    };

    loadRawSeries().catch((error) => {
      if (requestId === requestIdRef.current.raw) {
        setIsRawLoading(false);
      }
      console.error("Error loading uPlot raw data:", error);
    });
  }, [filterKey, primarySelectedSensorIds, selectedRun?._id]);

  useEffect(() => {
    const requestId = ++requestIdRef.current.plot;

    const loadComparisonPlotSeries = async () => {
      if (!comparisonRuns.length || !selectedRun?._id || Object.keys(comparisonSelectedEntriesByRun).length === 0) {
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
          .filter((comparisonRun) => comparisonSelectedEntriesByRun[comparisonRun._id]?.length)
          .map(async (comparisonRun) => {
          const comparisonBaseTimestamp = comparisonRun?.totalTimestamps?.[0];
          const mappedStart =
            Number.isFinite(visibleRange.start) && Number.isFinite(comparisonBaseTimestamp)
              ? comparisonBaseTimestamp + (visibleRange.start - currentBaseTimestamp)
              : undefined;
          const mappedEnd =
            Number.isFinite(visibleRange.end) && Number.isFinite(comparisonBaseTimestamp)
              ? comparisonBaseTimestamp + (visibleRange.end - currentBaseTimestamp)
              : undefined;

          const sensorEntries = await Promise.all(
            comparisonSelectedEntriesByRun[comparisonRun._id].map(async (entry) => {
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
            })
          );

          return [comparisonRun._id, Object.fromEntries(sensorEntries)];
        })
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
      if (!comparisonRuns.length || Object.keys(comparisonSelectedEntriesByRun).length === 0) {
        setComparisonRawSeriesByRun({});
        return;
      }

      const runEntries = await Promise.all(
        comparisonRuns
          .filter((comparisonRun) => comparisonSelectedEntriesByRun[comparisonRun._id]?.length)
          .map(async (comparisonRun) => {
            const sensorEntries = await Promise.all(
              comparisonSelectedEntriesByRun[comparisonRun._id].map(async (entry) => {
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
              })
            );

            return [comparisonRun._id, Object.fromEntries(sensorEntries)];
          })
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
    const fallbackStart = Number.isFinite(visibleRange.start) ? visibleRange.start : currentBaseTimestamp;
    const fallbackEnd = Number.isFinite(visibleRange.end)
      ? visibleRange.end
      : selectedRun?.totalTimestamps?.[selectedRun.totalTimestamps.length - 1];
    const displayResolution = Math.max(300, Math.min(plotResolution, 1800));
    const xValues =
      Number.isFinite(fallbackStart) &&
      Number.isFinite(fallbackEnd) &&
      fallbackEnd > fallbackStart
        ? Array.from({ length: displayResolution }, (_, index) => {
            const ratio = displayResolution === 1 ? 0 : index / (displayResolution - 1);
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
        : comparisonRuns.find((run) => run._id === entry.runId)?.totalTimestamps?.[0];
      const alignmentOffset =
        !entry.isPrimary && Number.isFinite(currentBaseTimestamp) && Number.isFinite(entryBaseTimestamp)
          ? currentBaseTimestamp - entryBaseTimestamp
          : 0;
      const offset = getSensorOffset(sensorSyncOffsets, entry.key);

      for (let axisIndex = 0; axisIndex < axisCount; axisIndex++) {
        const label = `${entry.runName} Sensor ${entry.sensorId} ${getAxisLabel(axisIndex, axisCount)}${useFilteredData ? " (filtered)" : ""}`;
        const color = TRACE_COLORS[series.length % TRACE_COLORS.length];
        traceColorByLabel.set(label, color);
        const interpolationPoints = plotReadings
          .map((reading) => ({
            x: reading.timestamp + offset + alignmentOffset,
            y: reading.data?.[axisIndex] ?? null,
          }))
          .filter((point) => Number.isFinite(point.x));
        series.push({
          sensorId: entry.sensorId,
          axisIndex,
          label,
          color,
          runId: entry.runId,
          runName: entry.runName,
          values: xValues.map((timestamp) => interpolateSeriesValue(interpolationPoints, timestamp)),
        });
      }

      const rawReadings = entry.isPrimary
        ? rawSeriesBySensor[entry.sensorId]
        : comparisonRawSeriesByRun[entry.runId]?.[entry.sensorId];
      const nearest = getNearestReading(rawReadings, currentTimestamp - offset);
      if (nearest) {
        const axes = (nearest.data || [])
          .map((value, axisIndex) => {
            const axisLabel = `${entry.runName} Sensor ${entry.sensorId} ${getAxisLabel(axisIndex, nearest.data.length)}${useFilteredData ? " (filtered)" : ""}`;
            if (!(traceVisibility[axisLabel] ?? true)) return null;
            return {
              name: getAxisLabel(axisIndex, nearest.data.length).replace("-axis", ""),
              value,
              color: traceColorByLabel.get(axisLabel) || "#6c757d",
            };
          })
          .filter(Boolean);

        if (axes.length === 0) {
          return;
        }

        readoutEntries.push({
          sensorId: entry.sensorId,
          runId: entry.runId,
          runName: entry.runName,
          timelineTimestamp: currentTimestamp,
          sensorTimestamp: nearest.timestamp,
          shift: offset,
          axes,
        });
      }
    });

    return { xValues, series, readoutEntries };
  }, [
    comparisonPlotSeriesByRun,
    comparisonRawSeriesByRun,
    comparisonRuns,
    currentTimestamp,
    plotResolution,
    plotSeriesBySensor,
    rawSeriesBySensor,
    selectedSensorEntries,
    selectedRun,
    sensorSyncOffsets,
    traceVisibility,
    useFilteredData,
    visibleRange.end,
    visibleRange.start,
  ]);

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
      : comparisonRuns.find((run) => run._id === entry.runId)?.totalTimestamps?.[0];
    const alignmentOffset =
      !entry.isPrimary && Number.isFinite(currentBaseTimestamp) && Number.isFinite(entryBaseTimestamp)
        ? currentBaseTimestamp - entryBaseTimestamp
        : 0;
    const syncOffset = getSensorOffset(sensorSyncOffsets, entry.key) + alignmentOffset;
    const sections = [];
    let isInSection = false;
    let sectionStart = null;

    readings.forEach((reading, index) => {
      const zValue = reading?.data?.[2];
      if (typeof zValue !== "number") return;

      if (zValue > 1.2 && !isInSection) {
        isInSection = true;
        sectionStart = index;
      } else if (zValue < 1.1 && isInSection) {
        isInSection = false;
        const sectionEnd = index;

        if (sectionStart === null) return;

        const sectionReadings = readings.slice(sectionStart, sectionEnd + 1);
        const xValues = sectionReadings
          .map((entry) => entry?.data?.[0])
          .filter((value) => typeof value === "number");

        const maxX = xValues.length ? Math.max(...xValues) : Number.NEGATIVE_INFINITY;
        if (!(maxX > 0.2)) return;

        const zValues = sectionReadings
          .map((entry) => entry?.data?.[2])
          .filter((value) => typeof value === "number");
        const maxZ = zValues.length ? Math.max(...zValues) : 0;

        let windowSize = 10;
        if (maxZ > 3.0) windowSize = 100;
        else if (maxZ > 2.1) windowSize = 150;
        else if (maxZ > 1.5) windowSize = 50;

        const yValues = sectionReadings
          .map((entry) => entry?.data?.[1])
          .filter((value) => typeof value === "number");

        let firstExtreme = null;
        for (let i = windowSize; i < yValues.length - windowSize; i++) {
          const current = yValues[i];
          const windowValues = yValues.slice(i - windowSize, i + windowSize + 1);
          const isMaximum = windowValues.every((value, idx) => idx === windowSize || current >= value);
          const isMinimum = windowValues.every((value, idx) => idx === windowSize || current <= value);

          if (isMaximum || isMinimum) {
            firstExtreme = current;
            break;
          }
        }

        if (firstExtreme === null) return;

        const color =
          Math.abs(firstExtreme) < 0.1 || firstExtreme > 0
            ? "rgba(0, 255, 0, 0.18)"
            : "rgba(255, 0, 0, 0.18)";

        const x0 = readings[sectionStart]?.timestamp + syncOffset;
        const x1 = readings[sectionEnd]?.timestamp + syncOffset;
        if (!Number.isFinite(x0) || !Number.isFinite(x1)) return;

        sections.push({ x0, x1, color });
      }
    });

    return sections;
  }, [comparisonRawSeriesByRun, comparisonRuns, rawSeriesBySensor, selectedRun, selectedSensorEntries, sensorSyncOffsets, showHighlightSections]);

  useEffect(() => {
    setSliderReadout(chartModel.readoutEntries);
  }, [chartModel.readoutEntries]);

  useEffect(() => {
    const target = chartContainerRef.current;
    if (!target) return undefined;

    if (plotInstanceRef.current) {
      plotInstanceRef.current.destroy();
      plotInstanceRef.current = null;
    }

    if (chartModel.series.length === 0) {
      return undefined;
    }

    const data = [
      chartModel.xValues,
      ...chartModel.series.map((seriesItem) => seriesItem.values),
    ];

    const chart = new uPlot(
      {
        width: Math.max(target.clientWidth || 600, 320),
        height: Math.max(target.clientHeight || 360, 260),
        scales: {
          x: { time: false },
        },
        series: [
          {},
          ...chartModel.series.map((seriesItem, index) => ({
            label: seriesItem.label,
            stroke: TRACE_COLORS[index % TRACE_COLORS.length],
            width: 1,
            show: traceVisibility[seriesItem.label] ?? true,
          })),
        ],
        axes: [
          { stroke: "#6c757d", grid: { stroke: "#eef1f4" } },
          { stroke: "#6c757d", grid: { stroke: "#eef1f4" } },
        ],
        legend: { show: false },
        cursor: {
          show: false,
          drag: { x: true, y: false, setScale: true },
        },
        select: {
          show: true,
          over: true,
          fill: "rgba(31, 119, 180, 0.12)",
          stroke: "rgba(31, 119, 180, 0.65)",
          width: 1,
        },
        hooks: {
          setScale: [
            (u, key) => {
              if (key !== "x") return;
              const min = u.scales.x.min;
              const max = u.scales.x.max;
              if (!Number.isFinite(min) || !Number.isFinite(max)) return;
              if (zoomCommitTimeoutRef.current !== null) {
                window.clearTimeout(zoomCommitTimeoutRef.current);
              }
              zoomCommitTimeoutRef.current = window.setTimeout(() => {
                zoomCommitTimeoutRef.current = null;
                setVisibleRange((prev) => {
                  if (prev.start === min && prev.end === max) return prev;
                  return { start: min, end: max };
                });
              }, 120);
            },
          ],
          draw: [
            (u) => {
              if (showHighlightSections) {
                u.ctx.save();
                u.ctx.beginPath();
                u.ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height);
                u.ctx.clip();

                highlightSections.forEach((section) => {
                  const startX = u.valToPos(section.x0, "x", true);
                  const endX = u.valToPos(section.x1, "x", true);
                  if (!Number.isFinite(startX) || !Number.isFinite(endX)) return;

                  const leftX = Math.min(startX, endX);
                  const width = Math.abs(endX - startX);
                  u.ctx.fillStyle = section.color;
                  u.ctx.fillRect(leftX, u.bbox.top, width, u.bbox.height);
                });

                u.ctx.restore();
              }

              const timestamp = cursorTimestampRef.current;
              if (!Number.isFinite(timestamp)) return;

              const xPos = u.valToPos(timestamp, "x", true);
              if (!Number.isFinite(xPos)) return;

              const left = Math.round(xPos) + 0.5;

              u.ctx.save();
              u.ctx.beginPath();
              u.ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height);
              u.ctx.clip();
              u.ctx.strokeStyle = "#1f77b4";
              u.ctx.lineWidth = 2;
              u.ctx.setLineDash([8, 6]);
              u.ctx.beginPath();
              u.ctx.moveTo(left, u.bbox.top);
              u.ctx.lineTo(left, u.bbox.top + u.bbox.height);
              u.ctx.stroke();
              u.ctx.restore();
            },
          ],
        },
      },
      data,
      target
    );

    plotInstanceRef.current = chart;

    return () => {
      chart.destroy();
      if (plotInstanceRef.current === chart) {
        plotInstanceRef.current = null;
      }
    };
  }, [chartModel, highlightSections, showHighlightSections, traceVisibility]);

  useEffect(() => {
    if (!isPlaying) return undefined;

    const interval = window.setInterval(() => {
      setLocalSliderValue((prevValue) => {
        const nextValue = Math.min(prevValue + 100, maxSliderIndex);
        setSliderValue(nextValue);
        if (nextValue >= maxSliderIndex) {
          setIsPlaying(false);
        }
        return nextValue;
      });
    }, 100);

    return () => window.clearInterval(interval);
  }, [isPlaying, maxSliderIndex, setSliderValue]);

  const scheduleSharedSliderUpdate = useCallback(
    (value) => {
      setLocalSliderValue(value);
      setSliderValue(value);
    },
    [setSliderValue]
  );

  const toggleSensor = (sensorKey) => {
    setSelectedSensorKeys((prev) =>
      prev.includes(sensorKey) ? prev.filter((id) => id !== sensorKey) : [...prev, sensorKey]
    );
  };

  const toggleTrace = (label) => {
    setTraceVisibility((prev) => ({
      ...prev,
      [label]: !(prev[label] ?? true),
    }));
  };

  const toggleFilter = (filterId) => {
    setPendingFilters((prev) =>
      prev.includes(filterId) ? prev.filter((id) => id !== filterId) : [...prev, filterId]
    );
  };

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

  const handleDragEnd = () => {
    setDraggedFilter(null);
  };

  const handleSyncOffsetChange = (sensorId, value) => {
    if (value === "" || value === "-" || value === "." || value === "-.") {
      setSensorSyncOffsets((prev) => ({ ...prev, [sensorId]: 0 }));
      return;
    }

    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    setSensorSyncOffsets((prev) => ({ ...prev, [sensorId]: parsed }));
  };

  const nudgeSyncOffset = (sensorId, delta) => {
    setSensorSyncOffsets((prev) => ({
      ...prev,
      [sensorId]: getSensorOffset(prev, sensorId) + delta,
    }));
  };

  const resetAllSyncOffsets = () => {
    setSensorSyncOffsets(Object.fromEntries(selectedSensorKeys.map((sensorKey) => [sensorKey, 0])));
  };

  const handleSliderInput = (event) => {
    const value = parseInt(event.target.value, 10);
    if (!Number.isFinite(value)) return;
    setIsPlaying(false);
    scheduleSharedSliderUpdate(value);
  };

  const prevFrame = () => {
    setIsPlaying(false);
    scheduleSharedSliderUpdate(Math.max(localSliderValue - 1, 0));
  };

  const nextFrame = () => {
    setIsPlaying(false);
    scheduleSharedSliderUpdate(Math.min(localSliderValue + 1, maxSliderIndex));
  };

  const resetPlayback = () => {
    setIsPlaying(false);
    scheduleSharedSliderUpdate(0);
  };

  const startPlayback = () => {
    setIsPlaying(true);
  };

  const pausePlayback = () => {
    setIsPlaying(false);
  };

  const handleChartClick = (event) => {
    if (panStateRef.current.moved) {
      panStateRef.current.moved = false;
      return;
    }

    const chart = plotInstanceRef.current;
    if (!chart || runTimestamps.length === 0) return;

    const bounds = chart.root.getBoundingClientRect();
    const relativeX = event.clientX - bounds.left;
    const value = chart.posToVal(relativeX, "x");
    const nextIndex = getNearestIndex(runTimestamps, value);
    if (nextIndex >= 0) {
      scheduleSharedSliderUpdate(nextIndex);
    }
  };

  const handlePanStart = (event) => {
    const chart = plotInstanceRef.current;
    if (!chart) return;
    if (event.button !== 0) return;

    const min = chart.scales.x.min;
    const max = chart.scales.x.max;
    if (!Number.isFinite(min) || !Number.isFinite(max)) return;

    panStateRef.current = {
      active: true,
      moved: false,
      startClientX: event.clientX,
      min,
      max,
    };
  };

  const handlePanMove = (event) => {
    const chart = plotInstanceRef.current;
    const panState = panStateRef.current;
    if (!chart || !panState.active || runTimestamps.length === 0) return;

    const dx = event.clientX - panState.startClientX;
    if (Math.abs(dx) > 2) {
      panState.moved = true;
    }

    const width = chart.bbox.width;
    if (!(width > 0)) return;

    const range = panState.max - panState.min;
    const valueDelta = (-dx / width) * range;

    let nextMin = panState.min + valueDelta;
    let nextMax = panState.max + valueDelta;

    const absoluteMin = runTimestamps[0];
    const absoluteMax = runTimestamps[runTimestamps.length - 1];

    if (nextMin < absoluteMin) {
      nextMin = absoluteMin;
      nextMax = absoluteMin + range;
    }

    if (nextMax > absoluteMax) {
      nextMax = absoluteMax;
      nextMin = absoluteMax - range;
    }

    chart.setScale("x", { min: nextMin, max: nextMax });
  };

  const handlePanEnd = () => {
    if (!panStateRef.current.active) return;
    panStateRef.current = {
      active: false,
      moved: panStateRef.current.moved,
      startClientX: 0,
      min: 0,
      max: 0,
    };
  };

  const handleWheelZoom = (event) => {
    const chart = plotInstanceRef.current;
    if (!chart || runTimestamps.length === 0) return;

    event.preventDefault();

    const currentMin = chart.scales.x.min;
    const currentMax = chart.scales.x.max;
    if (!Number.isFinite(currentMin) || !Number.isFinite(currentMax)) return;

    const bounds = chart.root.getBoundingClientRect();
    const relativeX = event.clientX - bounds.left;
    const anchorValue = chart.posToVal(relativeX, "x");
    if (!Number.isFinite(anchorValue)) return;

    const currentRange = currentMax - currentMin;
    if (!(currentRange > 0)) return;

    const zoomFactor = event.deltaY < 0 ? 0.8 : 1.25;
    const nextRange = Math.max(currentRange * zoomFactor, 1);
    const anchorRatio = (anchorValue - currentMin) / currentRange;

    let nextMin = anchorValue - nextRange * anchorRatio;
    let nextMax = nextMin + nextRange;

    const absoluteMin = runTimestamps[0];
    const absoluteMax = runTimestamps[runTimestamps.length - 1];
    if (!Number.isFinite(absoluteMin) || !Number.isFinite(absoluteMax)) return;

    if (nextMin < absoluteMin) {
      nextMin = absoluteMin;
      nextMax = nextMin + nextRange;
    }

    if (nextMax > absoluteMax) {
      nextMax = absoluteMax;
      nextMin = nextMax - nextRange;
    }

    nextMin = Math.max(nextMin, absoluteMin);
    nextMax = Math.min(nextMax, absoluteMax);

    if (!(nextMax > nextMin)) return;

    chart.setScale("x", { min: nextMin, max: nextMax });
  };

  const resetZoom = () => {
    setVisibleRange(getInitialRange(selectedRun));
  };

  const addComparisonRun = async () => {
    if (!comparisonRunId || comparisonRuns.some((run) => run._id === comparisonRunId)) return;

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
    setSelectedSensorKeys((prev) => prev.filter((key) => !key.startsWith(`${runId}:`)));
    setSensorSyncOffsets((prev) =>
      Object.fromEntries(Object.entries(prev).filter(([key]) => !key.startsWith(`${runId}:`)))
    );
  };

  return (
    <div className="uplot-prototype">
      <div className="uplot-prototype__header">
        <div>
          <strong>Sensor Graph</strong>
        </div>
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={removeFunction}>
          Remove
        </button>
      </div>

      <div className="uplot-prototype__toolbar">
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={resetZoom}>
          Reset Zoom
        </button>
      </div>

      {(isPlotLoading || isRawLoading) && selectedSensorEntries.length > 0 && (
        <div className="alert alert-info py-2 px-3 mb-3">
            {isPlotLoading ? "Updating plot data..." : "Syncing sensor data..."}
          </div>
      )}

      <div className="plot-configuration">

      <details className="card mb-3 sensors-collapsible" open>
        <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
          <strong>Sensors</strong>
          <span className="badge bg-secondary">
            {selectedSensorKeys.length} / {availableSensorEntries.length}
          </span>
        </summary>
        <div className="card-body">
          <div className="list-group">
            {availableSensorEntries.length === 0 && <div className="text-muted small">No sensors available</div>}
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
                  <span className="form-check-label">{entry.runName} Sensor {entry.sensorId}</span>
                </div>
                <small className="text-muted">ID: {entry.sensorId}</small>
              </label>
            ))}
          </div>
          <div className="d-flex mt-3">
            <button
              type="button"
              className="btn btn-sm btn-outline-primary me-2 flex-fill"
              onClick={() => setSelectedSensorKeys(availableSensorEntries.map((entry) => entry.key))}
              disabled={availableSensorEntries.length === 0}
            >
              Select All
            </button>
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary flex-fill"
              onClick={() => setSelectedSensorKeys([])}
              disabled={availableSensorEntries.length === 0}
            >
              Clear All
            </button>
          </div>
        </div>
      </details>

      <details className="card mb-3 sync-collapsible">
        <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
          <strong>Synchronization</strong>
          <span className="badge bg-secondary">
            {selectedSensorEntries.filter((entry) => getSensorOffset(sensorSyncOffsets, entry.key) !== 0).length} shifted
          </span>
        </summary>
        <div className="card-body">
          <p className="text-muted small mb-3">
            Use the slider in this graph to inspect alignment, then adjust each sensor offset to match the unified timeline.
          </p>
          {selectedSensorEntries.length === 0 && <div className="text-muted small">Select at least one sensor to sync.</div>}
          {selectedSensorEntries.length > 0 && (
            <>
              <div className="sync-offset-list">
                {selectedSensorEntries.map((entry) => {
                  const offset = getSensorOffset(sensorSyncOffsets, entry.key);
                  return (
                    <div key={entry.key} className="sync-offset-row">
                      <div>
                        <strong>{entry.runName} Sensor {entry.sensorId}</strong>
                      </div>
                      <div className="sync-offset-controls">
                        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => nudgeSyncOffset(entry.key, -1)}>
                          -1
                        </button>
                        <input
                          type="number"
                          step="any"
                          className="form-control form-control-sm sync-offset-input"
                          value={offset}
                          onChange={(event) => handleSyncOffsetChange(entry.key, event.target.value)}
                        />
                        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => nudgeSyncOffset(entry.key, 1)}>
                          +1
                        </button>
                        <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => handleSyncOffsetChange(entry.key, "0")}>
                          Reset
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="d-flex justify-content-end mt-3">
                <button type="button" className="btn btn-sm btn-outline-danger" onClick={resetAllSyncOffsets}>
                  Reset All Offsets
                </button>
              </div>
            </>
          )}
        </div>
      </details>

      <details className="card mb-3 filters-collapsible">
        <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
          <strong>Filters</strong>
          <span className={`badge ${useFilteredData ? "bg-success" : "bg-secondary"}`}>
            {useFilteredData ? "Active" : "Inactive"} ({pendingFilters.length} selected)
          </span>
        </summary>
        <div className="card-body">
          {pendingFilters.length > 0 && (
            <>
              <div className="mb-3">
                <div className="d-flex justify-content-between align-items-center mb-2">
                  <small className="text-muted">
                    <strong>Filter Pipeline (Top -&gt; Bottom):</strong>
                  </small>
                  <small className="text-muted">Drag to reorder</small>
                </div>
                <div className="list-group">
                  {pendingFilters.map((filterId, index) => {
                    const filter = FILTERS.find((item) => item.id === filterId);
                    return (
                      <div
                        key={filterId}
                        className="list-group-item list-group-item-action d-flex justify-content-between align-items-center active"
                        draggable
                        onDragStart={(event) => handleDragStart(event, filterId)}
                        onDragOver={handleDragOver}
                        onDrop={(event) => handleDrop(event, filterId)}
                        onDragEnd={handleDragEnd}
                        style={{ cursor: "move", opacity: draggedFilter === filterId ? 0.5 : 1 }}
                      >
                        <div className="d-flex align-items-center">
                          <span className="badge bg-light text-dark me-2" style={{ fontSize: "0.8rem" }}>
                            ===
                          </span>
                          <span className="badge bg-primary me-2">{index + 1}</span>
                          <span>{filter?.label}</span>
                        </div>
                        <button
                          type="button"
                          className="btn btn-sm btn-close"
                          aria-label="Remove"
                          onClick={(event) => {
                            event.preventDefault();
                            toggleFilter(filterId);
                          }}
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
              <hr />
            </>
          )}

          <div className="mb-2">
            <small className="text-muted">
              <strong>Available Filters:</strong>
            </small>
          </div>
          <div className="list-group">
            {FILTERS.filter((filter) => !pendingFilters.includes(filter.id)).map((filter) => (
              <label key={filter.id} className="list-group-item list-group-item-action d-flex justify-content-between align-items-center">
                <div className="form-check d-flex align-items-center m-0">
                  <input className="form-check-input me-2" type="checkbox" checked={false} onChange={() => toggleFilter(filter.id)} />
                  <span className="form-check-label">{filter.label}</span>
                </div>
              </label>
            ))}
            {FILTERS.filter((filter) => !pendingFilters.includes(filter.id)).length === 0 && (
              <div className="text-muted small">All filters selected</div>
            )}
          </div>

          <div className="d-flex mt-3 gap-2">
            {useFilteredData ? (
              <button type="button" className="btn btn-sm btn-outline-danger flex-fill" onClick={disableFilters}>
                Disable Filters
              </button>
            ) : (
              <button type="button" className="btn btn-sm btn-outline-primary flex-fill" onClick={applyFilters} disabled={pendingFilters.length === 0}>
                Apply Filters
              </button>
            )}
          </div>

          {useFilteredData && selectedFilters.length > 0 && (
            <div className="alert alert-success mt-3 mb-0 py-2 px-3">
              <strong>Active filters:</strong>{" "}
              {selectedFilters
                .map((filterId) => FILTERS.find((item) => item.id === filterId)?.label)
                .join(" -> ")}
            </div>
          )}
        </div>
      </details>

      <details className="card mb-3">
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
                .filter((run) => run._id !== selectedRun?._id && !comparisonRuns.some((item) => item._id === run._id))
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

      <details className="card mb-3">
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
              onChange={(event) => setShowHighlightSections(event.target.checked)}
            />
            <span>Show green/red highlight sections</span>
          </label>
        </div>
      </details>

      {chartModel.series.length > 0 && (
        <details className="card mb-3 traces-collapsible">
          <summary className="card-header d-flex justify-content-between align-items-center" style={{ listStyle: "none", cursor: "pointer" }}>
            <strong>Traces</strong>
            <span className="badge bg-secondary">
              {chartModel.series.filter((seriesItem) => traceVisibility[seriesItem.label] ?? true).length} visible
            </span>
          </summary>
          <div className="card-body">
            <div className="list-group">
              {chartModel.series.map((seriesItem) => {
                const visible = traceVisibility[seriesItem.label] ?? true;
                return (
                  <label key={seriesItem.label} className={`list-group-item list-group-item-action d-flex align-items-center ${visible ? "" : "text-muted"}`}>
                    <input className="form-check-input me-2" type="checkbox" checked={visible} onChange={() => toggleTrace(seriesItem.label)} />
                    <span>{seriesItem.label}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </details>
    )}
</div>
      {sliderReadout.length > 0 && (
        <div className="uplot-prototype__readout">
          {sliderReadout.map((entry) => (
            <div key={entry.sensorId} className="uplot-prototype__readout-item">
              <strong>Sensor {entry.sensorId}</strong>
              <span>Timeline: {entry.timelineTimestamp}</span>
              <span>Sensor: {entry.sensorTimestamp}</span>
              {entry.shift !== 0 && <span>Shift: {entry.shift >= 0 ? "+" : ""}{entry.shift}</span>}
              {entry.axes.map((axis) => (
                <span
                  key={`${entry.sensorId}-${axis.name}`}
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

      <div className="uplot-prototype__chart-shell">
        <div ref={chartContainerRef} className="uplot-prototype__chart" />
        <div
          ref={interactionLayerRef}
          className="uplot-prototype__interaction-layer"
          onClick={handleChartClick}
          onMouseDown={handlePanStart}
          onMouseMove={handlePanMove}
          onMouseUp={handlePanEnd}
          onMouseLeave={handlePanEnd}
          onWheel={handleWheelZoom}
        >
        </div>
      </div>
    </div>
  );
};

export default UPlotGraph;
