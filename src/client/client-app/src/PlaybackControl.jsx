import React, { useState, useEffect } from 'react';
import './PlaybackControl.css';

const PlaybackControl = ({ selectedRun, setSliderValue }) => {
    const [sliderValue, setLocalSliderValue] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(selectedRun.orientationData[0][0] - selectedRun.orientationData[0][0]);

    const handleInput = (event) => {
        const value = parseInt(event.target.value, 10);
        console.log('Input event:', value);
        setLocalSliderValue(value);
        setSliderValue(value);
        setIsPlaying(false);
        setCurrentTime(selectedRun.orientationData[value][0] - selectedRun.orientationData[0][0]);
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
        setCurrentTime(selectedRun.orientationData[0][0] - selectedRun.orientationData[0][0]);
    };

    useEffect(() => {
        let interval;
        if (isPlaying) {
            interval = setInterval(() => {
                setLocalSliderValue((prevValue) => {
                    const newValue = Math.min(prevValue + 1, selectedRun.orientationData.length - 1);
                    setSliderValue(newValue);
                    setCurrentTime(selectedRun.orientationData[newValue][0] - selectedRun.orientationData[0][0]);
                    return newValue;
                });
            }, 100);
        } else {
            clearInterval(interval);
        }
        return () => clearInterval(interval);
    }, [isPlaying, selectedRun.orientationData.length, setSliderValue]);

    useEffect(() => {
        if (!isPlaying) {
            setLocalSliderValue(sliderValue);
            setCurrentTime(selectedRun.orientationData[sliderValue][0] - selectedRun.orientationData[0][0]);
        }
    }, [sliderValue, isPlaying, selectedRun.orientationData]);

    function convertNanosecondsToTime(nanoseconds) {
        const msInNano = 1e6;
        const ms = Math.floor(nanoseconds / msInNano);
  
        const hours = Math.floor(ms / 3600000);
        const minutes = Math.floor((ms % 3600000) / 60000);
        const seconds = Math.floor((ms % 60000) / 1000);
        const milliseconds = ms % 1000;
  
        const formatTime = (unit) => String(unit).padStart(2, '0');
        return `${formatTime(hours)}:${formatTime(minutes)}:${formatTime(seconds)}:${String(milliseconds).padStart(3, '0')}`;
    }

    return (
        <div className="playback-controls d-flex">
            <input
                type="range"
                min="0"
                max={selectedRun.orientationData.length - 1}
                value={sliderValue}
                className="p-2 w-100"
                id="time-slider"
                onInput={handleInput}
            />
            <div className="btn-group">
                <button id="start-button" type="button" className="btn btn-success" onClick={startPlayback}>
                    <i className="fas fa-play"></i>
                </button>
                <button id="pause-button" type="button" className="btn btn-outline-success" onClick={pausePlayback}>
                    <i className="fas fa-pause"></i>
                </button>
                <button id="reset-button" type="button" className="btn btn-outline-danger" onClick={resetPlayback}>
                    <i className="fas fa-undo"></i>
                </button>
            </div>
            <h3 id="run-time">
                {convertNanosecondsToTime(currentTime)}
            </h3>
        </div>
    );
};

export default PlaybackControl;