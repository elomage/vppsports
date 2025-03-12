import React, { useState, useEffect } from 'react';
import RunControl from './Runcontrol';
import './Dashboard.css';
import VisualizationSelection from './Visualizationselection';
import PlaybackControl from './Playbackcontrol';

const Dashboard = () => {
    const [selectedRun, setSelectedRun] = useState(null);
    const [sliderValue, setSliderValue] = useState(0);

    useEffect(() => {
      console.log(selectedRun);
      
    }, [selectedRun]);

    return (
      <div className="d-flex w-100">
        {selectedRun && <PlaybackControl selectedRun={selectedRun} setSliderValue={setSliderValue} />}
        <div className="main-content flex-grow-1 w-100" id="dashboard-wrapper">
          <h1><a href="">Dashboard</a></h1>
          <RunControl setSelectedRun={setSelectedRun} />
                   
          {selectedRun && (
            <>
              {/* <h1>Selected Run ID: {selectedRun._id}</h1> */}
              <VisualizationSelection selectedRun={selectedRun} sliderValue={sliderValue} />
            </>
          )}
        </div>
      </div>
    );
};

export default Dashboard;