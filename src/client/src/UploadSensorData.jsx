import React, { useMemo, useState } from 'react';
import './UploadSensorData.css';
import { uploadRunVideo, uploadSensorDataBin, uploadSensorDataCsv } from './api';

const CSV_FORMATS = {
  accelerometer: {
    columns: ['timestamp', 'x', 'y', 'z'],
    example: ['0.000000', '0.014', '-0.021', '1.032'],
    notes: 'Values are imported exactly as provided. Use seconds from run start for timestamps.',
  },
  gyroscope: {
    columns: ['timestamp', 'x', 'y', 'z'],
    example: ['0.000000', '0.125', '-0.083', '0.041'],
    notes: 'Provide angular-rate readings per axis. Use seconds from run start for timestamps.',
  },
  strainGauge: {
    columns: ['timestamp', 'ch1', 'ch2', 'ch3', 'ch4', 'ch5', 'ch6', 'ch7', 'ch8'],
    example: ['0.000000', '124', '118', '121', '119', '115', '111', '109', '113'],
    notes: 'Provide one numeric channel value per column. Use seconds from run start for timestamps.',
  },
  gps: {
    columns: ['timestamp', 'x', 'y', 'z'],
    example: ['0.000000', '56.9496', '24.1052', '14.2'],
    notes: 'Preferred mapping is x=latitude, y=longitude, z=altitude. Use seconds from run start for timestamps.',
  },
};

const UploadSensorData = ({ currentUser, runs, onRunCreated }) => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadMode, setUploadMode] = useState('existing');
  const [existingRunId, setExistingRunId] = useState('');
  const [runName, setRunName] = useState('');
  const [selectedContextId, setSelectedContextId] = useState('');
  const [metadataJson, setMetadataJson] = useState('');
  const [sensorType, setSensorType] = useState('accelerometer');
  const [sensorName, setSensorName] = useState('');
  const [selectedFileType, setSelectedFileType] = useState('');
  const [status, setStatus] = useState({ type: 'idle', message: '' });
  const [isUploading, setIsUploading] = useState(false);
  const [inputKey, setInputKey] = useState(0);
  const [selectedVideoFile, setSelectedVideoFile] = useState(null);
  const [selectedVideoRunId, setSelectedVideoRunId] = useState('');
  const [videoStatus, setVideoStatus] = useState({ type: 'idle', message: '' });
  const [isVideoUploading, setIsVideoUploading] = useState(false);
  const [videoInputKey, setVideoInputKey] = useState(0);

  const availableContexts = useMemo(
    () =>
      Array.isArray(currentUser?.contexts)
        ? currentUser.contexts.filter((entry) => entry?.id && entry?.name)
        : [],
    [currentUser]
  );

  const visibleRuns = useMemo(
    () => (Array.isArray(runs) ? runs : []),
    [runs]
  );

  const csvFormat = CSV_FORMATS[sensorType];
  const selectedFileExtension = selectedFileType === 'csv' ? '.CSV' : '.BIN';

  const handleFileChange = (event) => {
    const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
    setStatus({ type: 'idle', message: '' });

    if (!file) {
      setSelectedFile(null);
      setSelectedFileType('');
      return;
    }

    const lowerName = file.name.toLowerCase();
    const nextFileType = lowerName.endsWith('.csv')
      ? 'csv'
      : lowerName.endsWith('.bin')
        ? 'bin'
        : '';

    if (!nextFileType) {
      setSelectedFile(null);
      setSelectedFileType('');
      setStatus({ type: 'error', message: 'Please select a .BIN or .CSV file.' });
      setInputKey((prev) => prev + 1);
      return;
    }

    setSelectedFile(file);
    setSelectedFileType(nextFileType);
  };

  const handleVideoFileChange = (event) => {
    const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
    setVideoStatus({ type: 'idle', message: '' });

    if (!file) {
      setSelectedVideoFile(null);
      return;
    }

    if (!file.name.toLowerCase().endsWith('.mp4')) {
      setSelectedVideoFile(null);
      setVideoStatus({ type: 'error', message: 'Please select an .MP4 video file.' });
      setVideoInputKey((prev) => prev + 1);
      return;
    }

    setSelectedVideoFile(file);
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!selectedFile) {
      setStatus({ type: 'error', message: 'Choose a .BIN or .CSV file before uploading.' });
      return;
    }

    const trimmedRunName = runName.trim();
    const trimmedExistingRunId = existingRunId.trim();
    const trimmedMetadataJson = metadataJson.trim();
    if (uploadMode === 'existing' && !trimmedExistingRunId) {
      setStatus({ type: 'error', message: 'Enter an existing run ID before uploading.' });
      return;
    }
    if (uploadMode === 'new' && !trimmedRunName) {
      setStatus({ type: 'error', message: 'Enter a run name before uploading.' });
      return;
    }
    if (uploadMode === 'new' && !selectedContextId.trim()) {
      setStatus({ type: 'error', message: 'Choose a context before uploading.' });
      return;
    }
    if (trimmedMetadataJson) {
      try {
        const parsedMetadata = JSON.parse(trimmedMetadataJson);
        if (!parsedMetadata || Array.isArray(parsedMetadata) || typeof parsedMetadata !== 'object') {
          throw new Error('Metadata JSON must be an object.');
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Metadata JSON is invalid.';
        setStatus({ type: 'error', message });
        return;
      }
    }

    setIsUploading(true);
    setStatus({ type: 'info', message: 'Uploading file...' });

    try {
      const uploadOptions =
        uploadMode === 'existing'
          ? { runId: trimmedExistingRunId, sensorType, sensorName: sensorName.trim(), metadata: trimmedMetadataJson }
          : { name: trimmedRunName, sensorType, sensorName: sensorName.trim(), contextId: selectedContextId.trim(), metadata: trimmedMetadataJson };
      const response =
        selectedFileType === 'csv'
          ? await uploadSensorDataCsv(selectedFile, uploadOptions)
          : await uploadSensorDataBin(selectedFile, uploadOptions);
      setStatus({
        type: 'success',
        message:
          uploadMode === 'existing'
            ? `Upload complete. ${selectedFileExtension} sensor data was added to the existing run.`
            : `Upload complete. New run created and ${selectedFileExtension} data uploaded.`,
      });
      setSelectedFile(null);
      setSelectedFileType('');
      setRunName('');
      setExistingRunId('');
      setSelectedContextId('');
      setMetadataJson('');
      setSensorName('');
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

  const handleVideoUpload = async (event) => {
    event.preventDefault();

    if (!selectedVideoRunId.trim()) {
      setVideoStatus({ type: 'error', message: 'Select an existing run before uploading a video.' });
      return;
    }

    if (!selectedVideoFile) {
      setVideoStatus({ type: 'error', message: 'Choose an .MP4 file before uploading.' });
      return;
    }

    setIsVideoUploading(true);
    setVideoStatus({ type: 'info', message: 'Uploading video...' });

    try {
      await uploadRunVideo(selectedVideoFile, selectedVideoRunId.trim());
      setVideoStatus({ type: 'success', message: 'Video uploaded and linked to the selected run.' });
      setSelectedVideoFile(null);
      setSelectedVideoRunId('');
      setVideoInputKey((prev) => prev + 1);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Video upload failed. Please try again.';
      setVideoStatus({ type: 'error', message });
    } finally {
      setIsVideoUploading(false);
    }
  };

  return (
    <div className="upload-view">
      <div className="upload-card">
        <h2>Upload Sensor Data</h2>
        <p className="upload-hint">
          Upload a sensor export in `.BIN` or `.CSV` format to either create a new run or append data to an existing run.
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
            <div className="upload-file-meta">Select one context</div>
            {availableContexts.map((entry) => (
              <label
                key={entry.id}
                className="form-control d-flex align-items-center gap-2"
              >
                <input
                  type="checkbox"
                  checked={selectedContextId === entry.id}
                  onChange={(event) =>
                    setSelectedContextId(event.target.checked ? entry.id : '')
                  }
                />
                <span>{entry.name}</span>
              </label>
            ))}
          </>
          )}
          <div className="upload-file-meta">Optional run metadata JSON</div>
          <textarea
            className="form-control"
            rows={8}
            value={metadataJson}
            onChange={(event) => setMetadataJson(event.target.value)}
            placeholder={`{\n  "discipline": "luge",\n  "athlete": "Name",\n  "track": "Track",\n  "weather": {\n    "airTempC": -3\n  }\n}`}
          />
          <select
            className="form-control"
            value={sensorType}
            onChange={(event) => setSensorType(event.target.value)}
          >
            <option value="accelerometer">Accelerometer</option>
            <option value="gyroscope">Gyroscope</option>
            <option value="strainGauge">Strain Gauge</option>
            <option value="gps">GPS</option>
          </select>
          <input
            className="form-control"
            type="text"
            value={sensorName}
            maxLength={80}
            onChange={(event) => setSensorName(event.target.value)}
            placeholder="Sensor name — optional (e.g. front, rear, left arm)"
          />
          <input
            key={inputKey}
            className="form-control"
            type="file"
            accept=".bin,.csv,text/csv"
            onChange={handleFileChange}
          />
          {selectedFile && (
            <div className="upload-file-meta">
              Selected: {selectedFile.name} ({Math.round(selectedFile.size / 1024)} KB)
            </div>
          )}
          <div className="upload-file-meta">Accepted CSV header for {sensorType}:</div>
          <pre className="upload-format-block">
            {csvFormat.columns.join(',')}
            {'\n'}
            {csvFormat.example.join(',')}
          </pre>
          <div className="upload-file-meta">{csvFormat.notes}</div>
          <div className="upload-file-meta">
            Alternate timestamp columns also accepted: `timestamp_ms` and `timestamp_us`.
          </div>
          <div className="upload-actions">
            <button
              className="btn btn-primary"
              type="submit"
              disabled={
                !selectedFile ||
                isUploading ||
                (uploadMode === 'existing'
                  ? !existingRunId.trim()
                  : (!runName.trim() || !selectedContextId.trim()))
              }
            >
              {isUploading ? 'Uploading...' : 'Upload'}
            </button>
            <button
              className="btn btn-outline-danger btn-sm"
              type="button"
              onClick={() => {
                setSelectedFile(null);
                setSelectedFileType('');
                setRunName('');
                setExistingRunId('');
                setSelectedContextId('');
                setMetadataJson('');
                setSensorName('');
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
      <div className="upload-card">
        <h2>Upload Run Video</h2>
        <p className="upload-hint">
          Upload an `.mp4` file for an existing run. Videos are stored in the server workspace and served from there.
        </p>
        <form className="upload-form" onSubmit={handleVideoUpload}>
          <select
            className="form-control"
            value={selectedVideoRunId}
            onChange={(event) => setSelectedVideoRunId(event.target.value)}
          >
            <option value="">Select existing run</option>
            {visibleRuns.map((run) => (
              <option key={run._id} value={run._id}>
                {run.name || `Run ${run._id}`}{run.context ? ` (${run.context})` : ''}
              </option>
            ))}
          </select>
          <input
            key={videoInputKey}
            className="form-control"
            type="file"
            accept="video/mp4,.mp4"
            onChange={handleVideoFileChange}
          />
          {selectedVideoFile && (
            <div className="upload-file-meta">
              Selected: {selectedVideoFile.name} ({Math.round(selectedVideoFile.size / 1024)} KB)
            </div>
          )}
          <div className="upload-actions">
            <button
              className="btn btn-primary"
              type="submit"
              disabled={!selectedVideoFile || !selectedVideoRunId.trim() || isVideoUploading}
            >
              {isVideoUploading ? 'Uploading...' : 'Upload video'}
            </button>
            <button
              className="btn btn-outline-danger btn-sm"
              type="button"
              onClick={() => {
                setSelectedVideoFile(null);
                setSelectedVideoRunId('');
                setVideoStatus({ type: 'idle', message: '' });
                setVideoInputKey((prev) => prev + 1);
              }}
              disabled={isVideoUploading}
            >
              Clear
            </button>
          </div>
          {videoStatus.message && (
            <div className={`upload-status ${videoStatus.type !== 'idle' ? `is-${videoStatus.type}` : ''}`} aria-live="polite">
              {videoStatus.message}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};

export default UploadSensorData;
