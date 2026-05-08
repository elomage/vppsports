import React, { useEffect, useState, useRef } from 'react';
import { fetchRunVideo, fetchRunViewState, saveVideoSyncOffset } from './api';

// ── Timestamp binary search ──────────────────────────────────────────────────

const findClosestTimestampIndex = (timestamps, target) => {
  if (!Array.isArray(timestamps) || timestamps.length === 0) return 0;

  let lo = 0;
  let hi = timestamps.length - 1;

  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (timestamps[mid] < target) lo = mid + 1;
    else hi = mid;
  }

  if (lo === 0) return 0;
  const cur = timestamps[lo];
  const prev = timestamps[lo - 1];
  if (!Number.isFinite(cur)) return lo - 1;
  return Math.abs(cur - target) < Math.abs(prev - target) ? lo : lo - 1;
};

// ── Sync-offset persistence ──────────────────────────────────────────────────

const OFFSET_KEY_PREFIX = 'vppsports_sync_offset_';

const loadOffset = (runId) => {
  if (!runId) return 0;
  const stored = localStorage.getItem(`${OFFSET_KEY_PREFIX}${runId}`);
  const n = parseFloat(stored);
  return Number.isFinite(n) ? n : 0;
};

const saveOffset = (runId, offset) => {
  if (!runId) return;
  localStorage.setItem(`${OFFSET_KEY_PREFIX}${runId}`, String(offset));
};

// ── Common frame rates ────────────────────────────────────────────────────────

const FRAME_RATE_OPTIONS = [
  { label: '24 fps', value: 24 },
  { label: '25 fps', value: 25 },
  { label: '29.97 fps', value: 29.97 },
  { label: '30 fps', value: 30 },
  { label: '50 fps', value: 50 },
  { label: '60 fps', value: 60 },
];

const DEFAULT_FRAME_RATE = 30;

// ── Component ────────────────────────────────────────────────────────────────

const VideoVisualizer = ({ selectedRun, effectiveTimestamps, sliderValue, setSliderValue, removeFunction }) => {
  const videoName = selectedRun?._id;

  const [videoUrl, setVideoUrl]       = useState('');
  const [videoError, setVideoError]   = useState(null);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [frameRate, setFrameRate]     = useState(DEFAULT_FRAME_RATE);

  // frameDuration is derived — not stored in state to avoid stale closures.
  const frameDuration = 1 / frameRate;

  // Sync offset: seconds to add to videoEl.currentTime to get the matching
  // sensor timestamp.  Loaded from localStorage per run, adjustable via UI.
  const [startOffset, setStartOffset] = useState(() => loadOffset(videoName));

  // Raw string for the number input so the user can type freely.
  const [offsetInput, setOffsetInput] = useState(() => String(loadOffset(videoName)));

  const videoRef = useRef(null);

  // ── Load offset when run changes — prefer DB, fall back to localStorage ───
  useEffect(() => {
    // Immediately apply the localStorage value so the UI isn't stuck at 0.
    const localVal = loadOffset(videoName);
    setStartOffset(localVal);
    setOffsetInput(String(localVal));

    if (!videoName) return;

    let cancelled = false;
    fetchRunViewState(videoName)
      .then((data) => {
        if (cancelled) return;
        if (typeof data?.videoSyncOffset === "number" && Number.isFinite(data.videoSyncOffset)) {
          setStartOffset(data.videoSyncOffset);
          setOffsetInput(String(data.videoSyncOffset));
          saveOffset(videoName, data.videoSyncOffset);
        }
      })
      .catch(() => { /* non-fatal — keep localStorage value */ });

    return () => { cancelled = true; };
  }, [videoName]);

  // ── Offset update helpers ─────────────────────────────────────────────────

  const applyOffset = (value) => {
    const clamped = parseFloat(value.toFixed(4));
    setStartOffset(clamped);
    setOffsetInput(String(clamped));
    saveOffset(videoName, clamped);
    if (videoName) {
      saveVideoSyncOffset(videoName, clamped).catch(() => { /* non-fatal */ });
    }
  };

  const adjustOffset = (delta) => applyOffset(startOffset + delta);

  // "Sync here": compute offset so that the current video frame aligns with
  // the sensor-data timestamp at the current slider position.
  //
  //   sensorTimestamp = videoTime + startOffset
  //   → startOffset = sensorTimestamp − videoTime
  const handleSyncHere = () => {
    if (!videoRef.current) return;
    const timestamps = effectiveTimestamps ?? selectedRun?.totalTimestamps;
    if (!Array.isArray(timestamps)) return;
    const videoTime       = videoRef.current.currentTime;
    const sensorTimestamp = timestamps[sliderValue];
    if (!Number.isFinite(sensorTimestamp)) return;
    applyOffset(sensorTimestamp - videoTime);
  };

  const handleOffsetInputChange = (e) => {
    setOffsetInput(e.target.value);
  };

  const handleOffsetInputCommit = () => {
    const n = parseFloat(offsetInput);
    if (Number.isFinite(n)) applyOffset(n);
    else setOffsetInput(String(startOffset)); // revert invalid input
  };

  // ── Fetch video blob ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!videoName) {
      setVideoUrl('');
      setVideoError('No video available for this run');
      return undefined;
    }

    let objectUrl = null;
    let isCancelled = false;

    async function getVideo() {
      try {
        setVideoError(null);
        const response = await fetchRunVideo(videoName);
        const videoBlob = await response.blob();
        objectUrl = URL.createObjectURL(videoBlob);
        if (!isCancelled) setVideoUrl(objectUrl);
      } catch (error) {
        if (isCancelled) return;
        setVideoUrl('');
        setVideoError(error.message);
      }
    }
    getVideo();

    return () => {
      isCancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [videoName]);

  // ── Drive slider from video playback (rAF polling loop) ───────────────────
  //
  // `timeupdate` only fires ~4 times/second — far too coarse for frame-accurate
  // sync.  Instead we poll videoEl.currentTime on every animation frame (~60 Hz)
  // and only call setSliderValue when the nearest sensor index actually changes.
  //
  // We search in `effectiveTimestamps` (the same array PlaybackControl and
  // EChartGraph use) rather than `selectedRun.totalTimestamps`.  When sensors
  // are selected in EChartGraph those two arrays can differ in density (e.g.
  // one 100 Hz sensor vs. all sensors combined at 250 entries/sec), which
  // would cause a proportional scaling error in the sync.
  useEffect(() => {
    const videoEl       = videoRef.current;
    const sensorReadings = effectiveTimestamps ?? selectedRun?.totalTimestamps;

    if (!videoEl || !Array.isArray(sensorReadings) || sensorReadings.length === 0) {
      return undefined;
    }

    let rafId = null;
    let lastIndex = -1;

    const tick = () => {
      const videoTargetTime = videoEl.currentTime + startOffset;
      const closestIndex    = findClosestTimestampIndex(sensorReadings, videoTargetTime);
      if (closestIndex !== lastIndex) {
        lastIndex = closestIndex;
        setSliderValue(closestIndex);
      }
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [setSliderValue, effectiveTimestamps, selectedRun?.totalTimestamps, startOffset, videoUrl]);

  // ── Playback speed ────────────────────────────────────────────────────────
  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = playbackSpeed;
  }, [playbackSpeed]);

  // ── Frame stepping ────────────────────────────────────────────────────────
  const moveOneFrameBack = () => {
    if (videoRef.current)
      videoRef.current.currentTime = Math.max(0, videoRef.current.currentTime - frameDuration);
  };

  const moveOneFrameForward = () => {
    if (videoRef.current)
      videoRef.current.currentTime = videoRef.current.currentTime + frameDuration;
  };

  // ── Render ────────────────────────────────────────────────────────────────

  const btnSm = { margin: '0 2px' };

  return (
    <>
      <div className="uplot-prototype__header">
        <div><strong>Video</strong></div>
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={removeFunction}>
          Remove
        </button>
      </div>

      {videoUrl && !videoError ? (
        <>
          <video ref={videoRef} controls src={videoUrl} style={{ width: '100%' }}>
            Your browser does not support the video tag.
          </video>

          {/* ── Video playback controls ── */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
            <button className="btn btn-sm btn-outline-primary" style={btnSm} onClick={moveOneFrameBack}>
              ◀ Frame
            </button>
            <button className="btn btn-sm btn-outline-primary" style={btnSm} onClick={moveOneFrameForward}>
              Frame ▶
            </button>
            <button className="btn btn-sm btn-outline-secondary" style={btnSm} onClick={() => setPlaybackSpeed((s) => Math.max(0.25, s - 0.25))}>
              Slower
            </button>
            <span style={{ fontSize: '0.85em', minWidth: '70px', textAlign: 'center' }}>
              {playbackSpeed.toFixed(2)}×
            </span>
            <button className="btn btn-sm btn-outline-secondary" style={btnSm} onClick={() => setPlaybackSpeed((s) => s + 0.25)}>
              Faster
            </button>
            <select
              className="form-select form-select-sm"
              value={frameRate}
              onChange={(e) => setFrameRate(Number(e.target.value))}
              style={{ width: 'auto', fontSize: '0.85em' }}
              title="Video frame rate — affects frame-step size and ±1 frame offset buttons"
            >
              {FRAME_RATE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* ── Sync offset controls ── */}
          <div style={{ marginTop: '10px', padding: '8px', background: '#f8f9fa', borderRadius: '6px', fontSize: '0.82em' }}>
            <div style={{ fontWeight: 600, marginBottom: '6px' }}>
              Video sync offset
              <span style={{ fontWeight: 400, color: '#666', marginLeft: '6px' }}>
                — sensor_time = video_time + offset
              </span>
            </div>

            {/* Coarse / fine / frame-precise buttons */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap', marginBottom: '6px' }}>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => adjustOffset(-1)}>−1 s</button>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => adjustOffset(-0.1)}>−0.1 s</button>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => adjustOffset(-frameDuration)}>−1 f</button>

              <input
                type="number"
                step="0.1"
                value={offsetInput}
                onChange={handleOffsetInputChange}
                onBlur={handleOffsetInputCommit}
                onKeyDown={(e) => e.key === 'Enter' && handleOffsetInputCommit()}
                style={{ width: '90px', textAlign: 'center', padding: '2px 4px', fontSize: '0.95em' }}
                className="form-control form-control-sm"
                title="Offset in seconds — edit directly or use buttons"
              />
              <span style={{ color: '#666' }}>s</span>

              <button className="btn btn-sm btn-outline-secondary" onClick={() => adjustOffset(frameDuration)}>+1 f</button>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => adjustOffset(0.1)}>+0.1 s</button>
              <button className="btn btn-sm btn-outline-secondary" onClick={() => adjustOffset(1)}>+1 s</button>
            </div>

            {/* Sync here + reset */}
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <button
                className="btn btn-sm btn-primary"
                onClick={handleSyncHere}
                title="Pause the video and move the data slider to the matching moment, then click this"
              >
                Sync here
              </button>
              <button
                className="btn btn-sm btn-outline-danger"
                onClick={() => applyOffset(0)}
                title="Reset offset to 0"
              >
                Reset offset
              </button>
              <span style={{ color: '#888', alignSelf: 'center' }}>
                Pause video &amp; data slider at the same real-world moment, then click Sync here.
              </span>
            </div>
          </div>
        </>
      ) : (
        <p>{videoError ? `Error loading video: ${videoError}` : 'Loading video…'}</p>
      )}
    </>
  );
};

export default VideoVisualizer;
