import React, { useEffect, useState, useRef, useCallback } from 'react';
import { fetchRunVideo } from './api'; // Adjust the path as needed
import throttle from 'lodash/throttle';

const VideoVisualizer = ({ selectedRun, sliderValue, setSliderValue }) => {
  const [videoUrl, setVideoUrl] = useState('');
  const videoName = 'sample.mp4'; // Change this to your desired video file name
  const videoRef = useRef(null);
  const sampleRate = 504; // Sensor samples per second

  const startOffset = 89; // Start offset in seconds

  const frameRate = 24; // Frames per second (assumed)
  const frameDuration = 1 / frameRate; // Duration of one frame in seconds

  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  useEffect(() => {
    async function getVideo() {
      try {
        const response = await fetchRunVideo(videoName);
        const videoBlob = await response.blob();
        const url = URL.createObjectURL(videoBlob);
        setVideoUrl(url);
      } catch (error) {
        console.error('Error fetching video:', error);
      }
    }
    getVideo();
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


  // Update slider value during video playback using timeupdate event.
useEffect(() => {
    const videoEl = videoRef.current;
    if (videoEl) {
        const handleTimeUpdate = () => {
            setSliderValue(Math.ceil((videoEl.currentTime + startOffset) * sampleRate));
        };

        videoEl.addEventListener('timeupdate', handleTimeUpdate);
        return () => videoEl.removeEventListener('timeupdate', handleTimeUpdate);
    }
}, [videoUrl, sampleRate, setSliderValue]);

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
      {videoUrl ? (
        <>
          <video ref={videoRef} controls width="100%" src={videoUrl}>
            Your browser does not support the video tag.
          </video>
          <div className="control-wrapper" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', marginTop: '10px' }}>
          <div style={{ marginTop: '10px'}}>
            <button className="btn btn-outline-primary" onClick={moveOneFrameBack}>
              Previous Frame
            </button>
            <button className="btn btn-outline-primary" onClick={moveOneFrameForward} style={{ marginLeft: '10px' }}>
              Next Frame
            </button>
          </div>
          <div style={{ marginTop: '10px' }}>
            <button className="btn btn-outline-secondary" onClick={decreaseSpeed}>
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
        <p>Loading video...</p>
      )}
      </>
  );
};

export default VideoVisualizer;