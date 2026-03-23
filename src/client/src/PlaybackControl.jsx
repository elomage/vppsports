import React, { useState, useEffect, useRef, useCallback } from 'react';
import './PlaybackControl.css';

const PlaybackControl = ({ selectedRun, sliderValue, setSliderValue }) => {
    const [localSliderValue, setLocalSliderValue] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const animationFrameRef = useRef(null);
    const pendingSliderValueRef = useRef(0);
    const timestamps = selectedRun?.totalTimestamps ?? [];
    const maxSliderIndex = Math.max(timestamps.length - 1, 0);
    const currentTimestamp = timestamps[localSliderValue] ?? timestamps[0] ?? 0;
    const timelineStart = timestamps[0] ?? 0;
    const currentTimelineTime = Math.max(currentTimestamp - timelineStart, 0);

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
    };

    const prevFrame = () => {
        setLocalSliderValue((prevValue) => {
            const newValue = Math.max(prevValue - 1, 0);
            scheduleSliderUpdate(newValue);
            return newValue;
        });

    };

    const nextFrame = () => {
        setLocalSliderValue((prevValue) => {
            const newValue = Math.min(prevValue + 1, maxSliderIndex);
            scheduleSliderUpdate(newValue);
            return newValue;
        });

    };

    useEffect(() => {
        let interval;
        if (isPlaying) {
            const speed = 100; //This needs to be propotional to the sample rate
            interval = setInterval(() => {
                setLocalSliderValue((prevValue) => {
                    const newValue = Math.min(prevValue + speed, maxSliderIndex);
                    scheduleSliderUpdate(newValue);
                    if (newValue >= maxSliderIndex) {
                        setIsPlaying(false);
                    }
                    return newValue;
                });
            }, 100);
        } else {
            clearInterval(interval);
        }
        return () => clearInterval(interval);
    }, [isPlaying, maxSliderIndex, scheduleSliderUpdate]);

    useEffect(() => {
        if (!isPlaying) {
            setLocalSliderValue(sliderValue);
        }
    }, [sliderValue, isPlaying]);

    useEffect(() => () => {
        if (animationFrameRef.current !== null) {
            cancelAnimationFrame(animationFrameRef.current);
        }
    }, []);

    const formatTime = (timelineValue) => {
    let ms = 0

    if (!Number.isFinite(timelineValue) || timelineValue <= 0) {
        ms = 0
    } else if (timelineValue >= 1e15) {
        ms = Math.floor(timelineValue / 1e6)
    } else if (timelineValue >= 1e12) {
        ms = Math.floor(timelineValue / 1e3)
    } else if (timelineValue >= 1e9) {
        ms = Math.floor(timelineValue / 1e6)
    } else if (timelineValue >= 1e6) {
        ms = Math.floor(timelineValue / 1e3)
    } else {
        ms = Math.floor(timelineValue * 1000)
    }

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
                max={maxSliderIndex}
                value={localSliderValue}
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
                {formatTime(currentTimelineTime)}
            </h3>
        </div>
    );
};

export default PlaybackControl;
