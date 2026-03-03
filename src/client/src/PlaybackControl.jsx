import React, { useState, useEffect, useRef, useCallback } from 'react';
import './PlaybackControl.css';

const PlaybackControl = ({ selectedRun, setSliderValue }) => {
    const [sliderValue, setLocalSliderValue] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    // const [currentTime, setCurrentTime] = useState(selectedRun.data[0].readings[0].timestamp);
    const [currentTime, setCurrentTime] = useState(selectedRun.totalTimestamps[0]);
    const animationFrameRef = useRef(null);
    const pendingSliderValueRef = useRef(0);

    const flushSliderValue = useCallback(() => {
        animationFrameRef.current = null;
        setSliderValue(pendingSliderValueRef.current);
    }, [setSliderValue]);

    const scheduleSliderUpdate = useCallback((value) => {
        pendingSliderValueRef.current = value;
        if (animationFrameRef.current !== null) return;
        animationFrameRef.current = requestAnimationFrame(flushSliderValue);
    }, [flushSliderValue]);

    const handleInput = (event) => {
        const value = parseInt(event.target.value, 10);
        setLocalSliderValue(value);
        scheduleSliderUpdate(value);
        setIsPlaying(false);
        setCurrentTime(selectedRun.totalTimestamps[value]);

    };

    const pausePlayback = () => {
        setIsPlaying(false);
    };
    
    const startPlayback = () => {
        setIsPlaying(true);
    };

    const resetPlayback = () => {
        setLocalSliderValue(0);
        scheduleSliderUpdate(0);
        setIsPlaying(false);
        setCurrentTime(selectedRun.totalTimestamps[0]);
    };

    const prevFrame = () => {
        setLocalSliderValue((prevValue) => {
            const newValue = Math.max(prevValue - 1, 0);
            scheduleSliderUpdate(newValue);
            // setCurrentTime(selectedRun.data[0].readings[newValue].timestamp);
            setCurrentTime(selectedRun.totalTimestamps[newValue]);
            return newValue;
        });

    };

    const nextFrame = () => {
        setLocalSliderValue((prevValue) => {
            const newValue = Math.min(prevValue + 1, selectedRun.totalTimestamps.length - 1);
            scheduleSliderUpdate(newValue);
            setCurrentTime(selectedRun.totalTimestamps[newValue]);
            return newValue;
        });

    };

    useEffect(() => {
        let interval;
        if (isPlaying) {
            const speed = 100; //This needs to be propotional to the sample rate
            interval = setInterval(() => {
                setLocalSliderValue((prevValue) => {
                    const newValue = Math.min(prevValue + speed, selectedRun.totalTimestamps.length - 1);
                    scheduleSliderUpdate(newValue);
                    setCurrentTime(selectedRun.totalTimestamps[newValue]);
                    return newValue;
                });
            }, 100);
        } else {
            clearInterval(interval);
        }
        return () => clearInterval(interval);
    }, [isPlaying, selectedRun.totalTimestamps.length, scheduleSliderUpdate]);

    useEffect(() => {
        if (!isPlaying) {
            setLocalSliderValue(sliderValue);
            setCurrentTime(selectedRun.totalTimestamps[sliderValue]);
        }
    }, [sliderValue, isPlaying, selectedRun.orientationData]);

    useEffect(() => () => {
        if (animationFrameRef.current !== null) {
            cancelAnimationFrame(animationFrameRef.current);
        }
    }, []);

    // const formatTime = (timeInSeconds) => {
    //     const ms = Math.floor(timeInSeconds * 1000);
    //     const hours = Math.floor(ms / 3600000);
    //     const minutes = Math.floor((ms % 3600000) / 60000);
    //     const seconds = Math.floor((ms % 60000) / 1000);
    //     const milliseconds = ms % 1000;
  
    //     const formatUnit = (unit) => String(unit).padStart(2, '0');
    //     return `${formatUnit(hours)}:${formatUnit(minutes)}:${formatUnit(seconds)}:${String(milliseconds).padStart(3, '0')}`;
    //   };

    const formatTime = (timeInNanoseconds) => {
    // Convert nanoseconds to milliseconds
    const ms = Math.floor(timeInNanoseconds / 1e6)
    const hours = Math.floor(ms / 3600000)
    const minutes = Math.floor((ms % 3600000) / 60000)
    const seconds = Math.floor((ms % 60000) / 1000)
    const milliseconds = ms % 1000
    const formatUnit = (unit) => String(unit).padStart(2, '0')
        return `${formatUnit(hours)}:${formatUnit(minutes)}:${formatUnit(seconds)}:${String(milliseconds).padStart(3, '0')}`
    };

    return (
        <div className="playback-controls d-flex">
            <input
                type="range"
                min="0"
                max={selectedRun.totalTimestamps.length - 1}
                value={sliderValue}
                className="p-2 w-100"
                id="time-slider"
                onInput={handleInput}
            />
            <div className="btn-group">
                <button id="prev-frame-button" type="button" className="btn btn-outline-success" onClick={prevFrame}>
                    <i className="fas fa-step-backward"></i>
                </button>
                <button id="start-button" type="button" className="btn btn-success" onClick={startPlayback}>
                    <i className="fas fa-play"></i>
                </button>
                <button id="pause-button" type="button" className="btn btn-outline-success" onClick={pausePlayback}>
                    <i className="fas fa-pause"></i>
                </button>
                <button id="next-frame-button" type="button" className="btn btn-outline-success" onClick={nextFrame}>
                    <i className="fas fa-step-forward"></i>
                </button>
                <button id="reset-button" type="button" className="btn btn-outline-danger" onClick={resetPlayback}>
                    <i className="fas fa-undo"></i>
                </button>
            </div>
            <h3 id="run-time">
                {/* {formatTime(currentTime)} */}
                {currentTime}
            </h3>
        </div>
    );
};

export default PlaybackControl;
