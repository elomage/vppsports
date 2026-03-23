import React, { useState, useEffect } from 'react';
import './Dashboard.css';
import VisualizationSelection from './Visualizationselection';
import PlaybackControl from './PlaybackControl';

const Dashboard = ({ selectedRun }) => {
    const [sliderValue, setSliderValue] = useState(0);
    
    useEffect(() => {
      setSliderValue(0);
    }, [selectedRun]);

    return (
      <div className="dashboard-container w-100">
        <div className="main-content flex-grow-1 w-100" id="dashboard-wrapper">
          {selectedRun && (
            <>
              <div className="playback-control-container">
                <PlaybackControl
                  selectedRun={selectedRun}
                  sliderValue={sliderValue}
                  setSliderValue={setSliderValue}
                />
              </div>
              <VisualizationSelection
                selectedRun={selectedRun}
                sliderValue={sliderValue}
                setSliderValue={setSliderValue}
              />
            </>
          )}
          {!selectedRun && (
            <div className="no-run-selected">
              <p>Please select a run from the dropdown above to view visualizations.</p>
            </div>
          )}
        </div>
      </div>
    );
};

export default Dashboard;
