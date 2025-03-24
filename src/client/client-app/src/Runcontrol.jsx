import React, { useState, useEffect, useRef } from 'react';
import { fetchRuns, fetchSelectedRun, fetchSelectedRunFiltered } from './api';
import './Runcontrol.css';

const RunControl = ({ setSelectedRun }) => {
  const [runs, setRuns] = useState([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const formRef = useRef(null);

  useEffect(() => {
    fetchRuns(dateFrom, dateTo).then(setRuns);
  }, [dateFrom, dateTo]);

  const handleRunChange = async (event) => {
    const runId = event.target.value;
    if (runId !== 'null') {
      const runData = await fetchSelectedRun(runId);

      //FIXME
      runData.filteredRunData = await fetchSelectedRunFiltered(runId);
      
      setSelectedRun(runData);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    fetchRuns(dateFrom, dateTo).then(setRuns);
  };

  return (
    <div className="run-control-container">
      {/* <form ref={formRef} method='get' action='/run' onSubmit={handleSubmit} className="run-control-form">
        <label>From:</label>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <label>To:</label>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
      </form> */}
      <select className='run-select' onChange={handleRunChange} style={{ width: formRef.current ? formRef.current.offsetWidth : 'auto' }}>
        <option value="null">Select Run</option>
        {runs.map((run) => (
          <option key={run._id} value={run._id}>{run._id}</option>
        ))}
      </select>
    </div>
  );
};

export default RunControl;