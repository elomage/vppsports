import React from 'react';
import './PlaybackControl.css';

const PlaybackControl = ({ selectedRun, setSliderValue }) => {
    const [sliderValue, setLocalSliderValue] = React.useState(0);
    const [isPlaying, setIsPlaying] = React.useState(false);

    const handleInput = (event) => {
        const value = event.target.value;
        console.log('Input event:', value);
        setLocalSliderValue(value);
        setSliderValue(value);
    };

    const handleClick = (event) => {
        console.log('Click event:', event.target.id);
    };

    const resetPlayback = () => {
        setLocalSliderValue(0);
        setSliderValue(0);
    };

    return (
        <div className="playback-controls d-flex">
            <input
                type="range"
                min="0"
                max={selectedRun.orientationData.length}
                value={sliderValue}
                defaultValue="1"
                className="p-2 w-100"
                id="time-slider"
                onInput={handleInput}
                onClick={handleClick}
            />
            <div className="btn-group">
                <button id="start-button" type="button" className="btn btn-success" onClick={handleClick}>
                    <i className="fas fa-play"></i>
                </button>
                <button id="pause-button" type="button" className="btn btn-outline-success" onClick={handleClick}>
                    <i className="fas fa-pause"></i>
                </button>
                <button id="reset-button" type="button" className="btn btn-outline-danger" onClick={resetPlayback}>
                    <i className="fas fa-undo"></i>
                </button>
            </div>
            <h3 id="run-time">
                {selectedRun.orientationData[0][0]}s
            </h3>
        </div>
    );
};

export default PlaybackControl;