import React, { useState } from 'react';
import './UploadSensorData.css';
import { uploadSensorDataBin } from './api';

const UploadSensorData = () => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [status, setStatus] = useState({ type: 'idle', message: '' });
  const [isUploading, setIsUploading] = useState(false);
  const [inputKey, setInputKey] = useState(0);

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

    setIsUploading(true);
    setStatus({ type: 'info', message: 'Uploading file...' });

    try {
      await uploadSensorDataBin(selectedFile);
      setStatus({ type: 'success', message: 'Upload complete. The backend will ingest the data when available.' });
      setSelectedFile(null);
      setInputKey((prev) => prev + 1);
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
          Upload a sensor export in .BIN format. The backend endpoint is not ready yet, so you may see a temporary error.
        </p>
        <form className="upload-form" onSubmit={handleUpload}>
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
            <button className="btn btn-primary" type="submit" disabled={!selectedFile || isUploading}>
              {isUploading ? 'Uploading...' : 'Upload'}
            </button>
            <button
              className="btn btn-outline-danger btn-sm"
              type="button"
              onClick={() => {
                setSelectedFile(null);
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
