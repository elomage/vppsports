import React, { useState, useEffect } from 'react';
import { fetchRuns, fetchSelectedRun } from './api';
import './Runcontrol.css';


const RunControl = ({ setSelectedRun }) => {
  const [runs, setRuns] = useState([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');


  //// Comment the following to fetch runs on filter button click
  useEffect(() => {
    fetchRuns(dateFrom, dateTo).then(setRuns);
  }, [dateFrom, dateTo]);

  const handleRunChange = async (event) => {
    const runId = event.target.value;
    if (runId !== 'null') {
      const runData = await fetchSelectedRun(runId);
      setSelectedRun(runData);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    fetchRuns(dateFrom, dateTo).then(setRuns);
  };

  return (
    <>
      <form method='get' action='/run' onSubmit={handleSubmit}>
        <label>From:</label>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <label>To:</label>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        {/* <button type="submit">Filter Runs</button> */}
      </form>
      <select onChange={handleRunChange}>
        <option value="null">Select Run</option>
        {runs.map((run) => (
          <option key={run._id} value={run._id}>{run.date}</option>
        ))}
      </select>
    </>
  );
};

export default RunControl;
