import React, { useMemo, useState } from 'react';
import './UploadSensorData.css';
import { uploadSensorDataBin } from './api';

const UploadSensorData = ({ currentUser, runs, onRunCreated }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadMode, setUploadMode] = useState('existing');
  const [existingRunId, setExistingRunId] = useState('');
  const [runName, setRunName] = useState('');
  const [context, setContext] = useState('');
  const [sensorType, setSensorType] = useState('accelerometer');
  const [status, setStatus] = useState({ type: 'idle', message: '' });
  const [isUploading, setIsUploading] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  const availableContexts = useMemo(
    () =>
      Array.isArray(currentUser?.contextRoles)
        ? [...new Set(currentUser.contextRoles.map(({ context }) => String(context || '').trim().toLowerCase()).filter(Boolean))]
        : [],
    [currentUser]
  );

  const visibleRuns = useMemo(
    () => (Array.isArray(runs) ? runs : []),
    [runs]
  );

  const canTypeCustomContext = currentUser?.role === 'admin';

  const handleFileChange = (event) => {
    const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
    setStatus({ type: 'idle', message: '' });

    if (!file) {
      setSelectedFile(null);
      return;
    }

    if (!file.name.toLowerCase().endsWith('.bin')) {
      setSelectedFile(null);
      setStatus({ type: 'error', message: 'Please select a .BIN file.' });
      setInputKey((prev) => prev + 1);
      return;
    }

    setSelectedFile(file);
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!selectedFile) {
      setStatus({ type: 'error', message: 'Choose a .BIN file before uploading.' });
      return;
    }

    const trimmedRunName = runName.trim();
    const trimmedExistingRunId = existingRunId.trim();
    if (uploadMode === 'existing' && !trimmedExistingRunId) {
      setStatus({ type: 'error', message: 'Enter an existing run ID before uploading.' });
      return;
    }
    if (uploadMode === 'new' && !trimmedRunName) {
      setStatus({ type: 'error', message: 'Enter a run name before uploading.' });
      return;
    }
    if (uploadMode === 'new' && !context.trim()) {
      setStatus({ type: 'error', message: 'Choose a context before uploading.' });
      return;
    }

    setIsUploading(true);
    setStatus({ type: 'info', message: 'Uploading file...' });

    try {
      const uploadOptions =
        uploadMode === 'existing'
          ? { runId: trimmedExistingRunId, sensorType }
          : { name: trimmedRunName, sensorType, context: context.trim().toLowerCase() };
      const response = await uploadSensorDataBin(selectedFile, uploadOptions);
      setStatus({
        type: 'success',
        message:
          uploadMode === 'existing'
            ? 'Upload complete. Sensor data was added to the existing run.'
            : 'Upload complete. New run created and data uploaded.',
      });
      setSelectedFile(null);
      setRunName('');
      setExistingRunId('');
      setContext('');
      setInputKey((prev) => prev + 1);
      if (response?.createdRun) {
        onRunCreated?.(response);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed. Please try again.';
      setStatus({ type: 'error', message });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="upload-view">
      <div className="upload-card">
        <h2>Upload Sensor Data</h2>
        <p className="upload-hint">
          Upload a sensor export in .BIN format to either create a new run or append data to an existing run.
          Existing runs are limited to the contexts assigned to your account.
        </p>
        <form className="upload-form" onSubmit={handleUpload}>
          <div className="upload-mode-toggle">
            <label className="upload-mode-option">
              <input
                type="radio"
                name="upload-mode"
                value="existing"
                checked={uploadMode === 'existing'}
                onChange={() => {
                  setUploadMode('existing');
                  setStatus({ type: 'idle', message: '' });
                }}
              />
              Add to existing run
            </label>
            <label className="upload-mode-option">
              <input
                type="radio"
                name="upload-mode"
                value="new"
                checked={uploadMode === 'new'}
                onChange={() => {
                  setUploadMode('new');
                  setStatus({ type: 'idle', message: '' });
                }}
              />
              Create new run
            </label>
          </div>
          {uploadMode === 'existing' ? (
            <select
              className="form-control"
              value={existingRunId}
              onChange={(event) => setExistingRunId(event.target.value)}
            >
              <option value="">Select existing run</option>
              {visibleRuns.map((run) => (
                <option key={run._id} value={run._id}>
                  {run.name || `Run ${run._id}`}{run.context ? ` (${run.context})` : ''}
                </option>
              ))}
            </select>
          ) : (
          <>
            <input
              className="form-control"
              type="text"
              value={runName}
              maxLength={120}
              onChange={(event) => setRunName(event.target.value)}
              placeholder="Run name"
            />
            {canTypeCustomContext ? (
              <input
                className="form-control"
                type="text"
                list="upload-context-options"
                value={context}
                maxLength={64}
                onChange={(event) => setContext(event.target.value)}
                placeholder="Context"
              />
            ) : (
              <select
                className="form-control"
                value={context}
                onChange={(event) => setContext(event.target.value)}
              >
                <option value="">Select context</option>
                {availableContexts.map((entry) => (
                  <option key={entry} value={entry}>
                    {entry}
                  </option>
                ))}
              </select>
            )}
            {canTypeCustomContext && availableContexts.length > 0 && (
              <datalist id="upload-context-options">
                {availableContexts.map((entry) => (
                  <option key={entry} value={entry} />
                ))}
              </datalist>
            )}
          </>
          )}
          <select
            className="form-control"
            value={sensorType}
            onChange={(event) => setSensorType(event.target.value)}
          >
            <option value="accelerometer">Accelerometer</option>
            <option value="strainGauge">Strain Gauge</option>
            <option value="gps">GPS</option>
          </select>
          <input
            key={inputKey}
            className="form-control"
            type="file"
            accept=".bin"
            onChange={handleFileChange}
          />
          {selectedFile && (
            <div className="upload-file-meta">
              Selected: {selectedFile.name} ({Math.round(selectedFile.size / 1024)} KB)
            </div>
          )}
          <div className="upload-actions">
            <button
              className="btn btn-primary"
              type="submit"
              disabled={
                !selectedFile ||
                isUploading ||
                (uploadMode === 'existing' ? !existingRunId.trim() : (!runName.trim() || !context.trim()))
              }
            >
              {isUploading ? 'Uploading...' : 'Upload'}
            </button>
            <button
              className="btn btn-outline-danger btn-sm"
              type="button"
              onClick={() => {
                setSelectedFile(null);
                setRunName('');
                setExistingRunId('');
                setContext('');
                setStatus({ type: 'idle', message: '' });
                setInputKey((prev) => prev + 1);
              }}
              disabled={isUploading}
            >
              Clear
            </button>
          </div>
          {status.message && (
            <div className={`upload-status ${status.type !== 'idle' ? `is-${status.type}` : ''}`} aria-live="polite">
              {status.message}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};

export default UploadSensorData;
