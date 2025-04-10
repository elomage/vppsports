import React, { useState, useEffect } from 'react';
import './PlaybackControl.css';

const PlaybackControl = ({ selectedRun, setSliderValue }) => {
    const [sliderValue, setLocalSliderValue] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(selectedRun.data[0].readings[0].timestamp);

    const handleInput = (event) => {
        const value = parseInt(event.target.value, 10);
        setLocalSliderValue(value);
        setSliderValue(value);
        setIsPlaying(false);
        setCurrentTime(selectedRun.data[0].readings[value].timestamp);
    };

    const pausePlayback = () => {
        setIsPlaying(false);
    };
    
    const startPlayback = () => {
        console.log(sliderValue);
        setIsPlaying(true);
    };

    const resetPlayback = () => {
        setLocalSliderValue(0);
        setSliderValue(0);
        setIsPlaying(false);
        setCurrentTime(selectedRun.data[0].readings[0].timestamp);
    };

    const prevFrame = () => {
        setLocalSliderValue((prevValue) => {
            const newValue = Math.max(prevValue - 1, 0);
            setSliderValue(newValue);
            setCurrentTime(selectedRun.data[0].readings[newValue].timestamp);
            return newValue;
        });
    };

    const nextFrame = () => {
        setLocalSliderValue((prevValue) => {
            const newValue = Math.min(prevValue + 1, selectedRun.data[0].readings.length - 1);
            setSliderValue(newValue);
            setCurrentTime(selectedRun.data[0].readings[newValue].timestamp);
            return newValue;
        });
    };

    useEffect(() => {
        let interval;
        if (isPlaying) {
            const speed = 1;
            interval = setInterval(() => {
                setLocalSliderValue((prevValue) => {
                    const newValue = Math.min(prevValue + speed, selectedRun.data[0].readings.length - 1);
                    setSliderValue(newValue);
                    setCurrentTime(selectedRun.data[0].readings[newValue].timestamp);
                    return newValue;
                });
            }, 100);
        } else {
            clearInterval(interval);
        }
        return () => clearInterval(interval);
    }, [isPlaying, selectedRun.data[0].readings.length, setSliderValue]);

    useEffect(() => {
        if (!isPlaying) {
            setLocalSliderValue(sliderValue);
            setCurrentTime(selectedRun.data[0].readings[sliderValue].timestamp);
        }
    }, [sliderValue, isPlaying, selectedRun.orientationData]);

    const formatTime = (timeInSeconds) => {
        const ms = Math.floor(timeInSeconds * 1000);
        const hours = Math.floor(ms / 3600000);
        const minutes = Math.floor((ms % 3600000) / 60000);
        const seconds = Math.floor((ms % 60000) / 1000);
        const milliseconds = ms % 1000;
  
        const formatUnit = (unit) => String(unit).padStart(2, '0');
        return `${formatUnit(hours)}:${formatUnit(minutes)}:${formatUnit(seconds)}:${String(milliseconds).padStart(3, '0')}`;
      };

    return (
        <div className="playback-controls d-flex">
            <input
                type="range"
                min="0"
                max={selectedRun.data[0].readings.length - 1}
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
                {formatTime(currentTime)}
            </h3>
        </div>
    );
};

export default PlaybackControl;