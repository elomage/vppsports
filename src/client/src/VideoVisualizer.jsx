import React, { useEffect, useState, useRef } from 'react';
import { fetchRunVideo, fetchRunViewState, saveVideoSyncOffset } from './api';

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

const DEFAULT_FRAME_DURATION = 1 / 30;

const VideoVisualizer = ({ selectedRun, effectiveTimestamps, sliderValue, setSliderValue, removeFunction }) => {
  const videoName = selectedRun?._id;

  const [videoUrl, setVideoUrl]       = useState('');
  const [videoError, setVideoError]   = useState(null);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  const [startOffset, setStartOffset] = useState(() => loadOffset(videoName));

  const [offsetInput, setOffsetInput] = useState(() => String(loadOffset(videoName)));

  const videoRef = useRef(null);

  useEffect(() => {
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
      .catch(() => {});

    return () => { cancelled = true; };
  }, [videoName]);

  const applyOffset = (value) => {
    const clamped = parseFloat(value.toFixed(4));
    setStartOffset(clamped);
    setOffsetInput(String(clamped));
    saveOffset(videoName, clamped);
    if (videoName) {
      saveVideoSyncOffset(videoName, clamped).catch(() => {});
    }
  };

  const adjustOffset = (delta) => applyOffset(startOffset + delta);

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
    else setOffsetInput(String(startOffset));
  };

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

  useEffect(() => {
    const videoEl       = videoRef.current;
    const sensorReadings = effectiveTimestamps ?? selectedRun?.totalTimestamps;

    if (!videoEl || !Array.isArray(sensorReadings) || sensorReadings.length === 0) {
      return undefined;
    }

    let rafId = null;
    let lastIndex = -1;
    let lastUpdateTime = 0;
    const UPDATE_INTERVAL_MS = 50;

    const tick = (now) => {
      const videoTargetTime = videoEl.currentTime + startOffset;
      const closestIndex    = findClosestTimestampIndex(sensorReadings, videoTargetTime);
      if (closestIndex !== lastIndex && now - lastUpdateTime >= UPDATE_INTERVAL_MS) {
        lastIndex = closestIndex;
        lastUpdateTime = now;
        setSliderValue(closestIndex);
      }
      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [setSliderValue, effectiveTimestamps, selectedRun?.totalTimestamps, startOffset, videoUrl]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.playbackRate = playbackSpeed;
  }, [playbackSpeed]);

  const moveOneFrameBack = () => {
    if (videoRef.current)
      videoRef.current.currentTime = Math.max(0, videoRef.current.currentTime - DEFAULT_FRAME_DURATION);
  };

  const moveOneFrameForward = () => {
    if (videoRef.current)
      videoRef.current.currentTime = videoRef.current.currentTime + DEFAULT_FRAME_DURATION;
  };

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

          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
            <button className="btn btn-sm btn-outline-primary" style={btnSm} onClick={moveOneFrameBack}>
              &lt; Frame
            </button>
            <button className="btn btn-sm btn-outline-primary" style={btnSm} onClick={moveOneFrameForward}>
              Frame &gt;
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
          </div>

          <div style={{ marginTop: '10px', padding: '8px', background: '#f8f9fa', borderRadius: '6px', fontSize: '0.82em' }}>
            <div style={{ fontWeight: 600, marginBottom: '6px' }}>
              Video sync offset
              <span style={{ fontWeight: 400, color: '#666', marginLeft: '6px' }}>
                video_time + offset
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap', marginBottom: '6px' }}>
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
            </div>

            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <button
                className="btn btn-sm btn-primary"
                onClick={handleSyncHere}
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
