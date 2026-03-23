import React, { useEffect, useState, useRef } from 'react';
import { fetchRunVideo } from './api'; // Adjust the path as needed

const findClosestTimestampIndex = (timestamps, target) => {
  if (!Array.isArray(timestamps) || timestamps.length === 0) return 0;

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

const VideoVisualizer = ({ selectedRun, sliderValue, setSliderValue }) => {
  const [videoUrl, setVideoUrl] = useState('');
  const [videoError, setVideoError] = useState(null);

  // const videoName = 'sample.mp4'; // Change this to your desired video file name
  // const videoName = 'VijoleSample.mp4'; // Change this to your desired video file name


  const videoName = selectedRun?._id; // Change this to your desired video file name

  const videoRef = useRef(null);

  const sampleRate = 504; // Sensor samples per second
  // const sampleRate = 555; // Sensor samples per second

  // const startOffset = 89; // Start offset in seconds
  // const startOffset = 80; // Start offset in seconds

  const startOffset = 97.5; // Start offset in seconds Luge
  // const startOffset = 26.5; // Start offset in seconds ViolinTest

  // const startOffset = 15; // Start offset in seconds Violin Rebeka2
  // const startOffset = 22; // Start offset in seconds Violin Rebeka1

  // const startOffset = 1013.5; // Start offset in seconds Violin ReinisPareizi

  // const startOffset = 12.5; // Start offset violin ReinisNepareizi

  // const startOffset = 86; // Start offset in seconds Violin ReinisPareizi 2

  // const startOffset = 0; // Start offset in seconds Violin ReinisNepareizi 2

  const frameRate = 24; // Frames per second (assumed)
  const frameDuration = 1 / frameRate; // Duration of one frame in seconds

  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const videoSliderFrameRef = useRef(null);
  const pendingVideoSliderValueRef = useRef(0);

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
        if (!isCancelled) {
          setVideoUrl(objectUrl);
        }
      } catch (error) {
        if (isCancelled) return;
        console.error('Error fetching video:', error);
        setVideoUrl('');
        setVideoError(error.message);
      }
    }
    getVideo();

    return () => {
      isCancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [videoName]);

  //Update video position based on sliderValue and sampleRate.

  // useEffect(() => {
  //   if (videoRef.current && typeof sliderValue === 'number') {
  //     const videoTime = sliderValue / sampleRate;
  //     if (Math.abs(videoRef.current.currentTime - videoTime) > 0.1) {
  //       videoRef.current.currentTime = videoTime;
  //     }
  //   }
  // }, [sliderValue, sampleRate]);

  //   // Throttle slider updates from video playback.
  // const throttledUpdate = useCallback(
  //   throttle((currentTime) => {
  //     setSliderValue(Math.ceil(currentTime * sampleRate));
  //   }, 100),
  //   [sampleRate, setSliderValue]
  // );


  useEffect(() => {
    const flushSliderValue = () => {
      videoSliderFrameRef.current = null;
      setSliderValue(pendingVideoSliderValueRef.current);
    };

    const scheduleSliderValue = (value) => {
      pendingVideoSliderValueRef.current = value;
      if (videoSliderFrameRef.current !== null) return;
      videoSliderFrameRef.current = requestAnimationFrame(flushSliderValue);
    };

    const videoEl = videoRef.current;
    const sensorReadings = selectedRun?.totalTimestamps;

    if (videoEl && Array.isArray(sensorReadings) && sensorReadings.length > 0) {
        const handleTimeUpdate = () => {
          const videoTargetTime = videoEl.currentTime + startOffset;
          const closestIndex = findClosestTimestampIndex(sensorReadings, videoTargetTime);
          scheduleSliderValue(closestIndex);
        };

        videoEl.addEventListener('timeupdate', handleTimeUpdate);
        return () => {
          videoEl.removeEventListener('timeupdate', handleTimeUpdate);
          if (videoSliderFrameRef.current !== null) {
            cancelAnimationFrame(videoSliderFrameRef.current);
            videoSliderFrameRef.current = null;
          }
        };
    }

    return undefined;
  }, [setSliderValue, selectedRun?.totalTimestamps, startOffset, videoUrl]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.playbackRate = playbackSpeed;
    }
  }, [playbackSpeed]);

  // Function to move one frame back.
  const moveOneFrameBack = () => {
    if (videoRef.current) {
      const newTime = Math.max(0, videoRef.current.currentTime - frameDuration);
      videoRef.current.currentTime = newTime;
      console.log('Moved one frame back. New currentTime:', newTime);
    }
  };

  // Function to move one frame forward.
  const moveOneFrameForward = () => {
    if (videoRef.current) {
      const newTime = videoRef.current.currentTime + frameDuration;
      videoRef.current.currentTime = newTime;
      console.log('Moved one frame forward. New currentTime:', newTime);
    }
  };

  const decreaseSpeed = () => {
  setPlaybackSpeed((prevSpeed) => Math.max(0.25, prevSpeed - 0.25));
  };

  const increaseSpeed = () => {
  setPlaybackSpeed((prevSpeed) => prevSpeed + 0.25);
  };

  return (
    <>
      {videoUrl && !videoError ? (
        <>
          <video ref={videoRef} controls src={videoUrl}>
            Your browser does not support the video tag.
          </video>
          <div className="control-wrapper" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', marginTop: '10px' }}>
          <div style={{ marginTop: '10px', marginBottom: '10px'}}>
            <button className="btn btn-outline-primary" onClick={moveOneFrameBack}>
              Previous Frame
            </button>
            <button className="btn btn-outline-primary" onClick={moveOneFrameForward} style={{ marginLeft: '10px' }}>
              Next Frame
            </button>
          </div>
          <div style={{ marginTop: '10px', marginBottom: '10px' }}>
            <button className="btn btn-outline-secondary" onClick={decreaseSpeed} style={{marginLeft: '10px'}}>
              Slower
            </button>
            <span style={{ margin: '0 10px' }}>Speed: {playbackSpeed.toFixed(2)}x</span>
            <button className="btn btn-outline-secondary" onClick={increaseSpeed}>
              Faster
            </button>
            </div>
          </div>
        </>
      ) : (
        <p>{videoError ? `Error loading video: ${videoError}` : "Loading video..."}</p>
      )}
      </>
  );
};

export default VideoVisualizer;
