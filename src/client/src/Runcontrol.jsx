import React, { useState, useEffect, useRef } from 'react';
import { fetchRuns, fetchSelectedRun, fetchSelectedRunFiltered } from './api';
import './Runcontrol.css';

const RunControl = ({ setSelectedRun, runs: externalRuns }) => {
  const [runs, setRuns] = useState([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const formRef = useRef(null);
  const [loadingRun, setLoadingRun] = useState(false); // add

  useEffect(() => {
    if (Array.isArray(externalRuns)) {
      setRuns(externalRuns);
      return;
    }

    fetchRuns(dateFrom, dateTo)
      .then(setRuns)
      .catch((err) => {
        console.error('Failed to fetch runs', err);
        setRuns([]);
      });
  }, [dateFrom, dateTo, externalRuns]);

  const handleRunChange = async (event) => {
    const runId = event.target.value;
    if (runId === 'null') {
      setSelectedRun(null);
      return;
    }
    setLoadingRun(true);
    try {
      const [runData, filtered] = await Promise.all([
        fetchSelectedRun(runId),
        fetchSelectedRunFiltered(runId),
      ]);
      runData.filteredRunData = filtered; // FIXME kept as-is
      setSelectedRun(runData);
    } catch (err) {
      console.error('Failed to load run data', err);
    } finally {
      setLoadingRun(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    fetchRuns(dateFrom, dateTo)
      .then(setRuns)
      .catch((err) => {
        console.error('Failed to fetch runs', err);
        setRuns([]);
      });
  };

  return (
    <div className="run-control-container">
      {/* <form ref={formRef} method='get' action='/run' onSubmit={handleSubmit} className="run-control-form">
        <label>From:</label>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <label>To:</label>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
      </form> */}
      <select
        className='run-select'
        onChange={handleRunChange}
        disabled={loadingRun}
        style={{ width: formRef.current ? formRef.current.offsetWidth : 'auto' }}
      >
        <option value="null">Select Run</option>
        {runs.map((run) => (
          <option key={run._id} value={run._id}>
            {run.name || `Run ${run._id}`}
          </option>
        ))}
      </select>

      {loadingRun && (
        <div aria-live="polite" style={{ marginTop: 8 }}>
          Loading run data…
        </div>
      )}
    </div>
  );
};

export default RunControl;
