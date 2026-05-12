import React, { useState, useEffect } from 'react';
import { updateRunMetadata } from './api';

const hasMetadata = (metadata) =>
  metadata && typeof metadata === 'object' && !Array.isArray(metadata) && Object.keys(metadata).length > 0;

const toDatetimeLocal = (dateStr) => {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return isNaN(d) ? '' : d.toISOString().slice(0, 16);
  } catch {
    return '';
  }
};

const InfoVisualizer = ({ selectedRun }) => {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [overrides, setOverrides] = useState({});

  const [formDescription, setFormDescription] = useState('');
  const [formWeather, setFormWeather] = useState('');
  const [formDate, setFormDate] = useState('');
  const [formMetadataText, setFormMetadataText] = useState('');

  useEffect(() => {
    setOverrides({});
    setEditing(false);
    setError(null);
  }, [selectedRun?._id]);

  const display = { ...selectedRun, ...overrides };

  const startEdit = () => {
    setFormDescription(display.description || '');
    setFormWeather(display.weather || '');
    setFormDate(toDatetimeLocal(display.date));
    setFormMetadataText(hasMetadata(display.metadata) ? JSON.stringify(display.metadata, null, 2) : '');
    setError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setError(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);

    let metadata = {};
    if (formMetadataText.trim()) {
      try {
        metadata = JSON.parse(formMetadataText);
      } catch {
        setError('Invalid JSON in metadata field.');
        setSaving(false);
        return;
      }
    }

    try {
      await updateRunMetadata(selectedRun._id, {
        description: formDescription,
        weather: formWeather,
        date: formDate || undefined,
        metadata,
      });

      setOverrides({
        description: formDescription,
        weather: formWeather,
        date: formDate ? new Date(formDate).toISOString() : display.date,
        metadata,
      });
      setEditing(false);
    } catch (err) {
      setError(err?.message || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <figure id="run-info">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <b>
            <figcaption id="run-info-title">Selected run: {selectedRun._id}</figcaption>
          </b>
          {!editing && (
            <button onClick={startEdit} className="btn btn-sm btn-outline-secondary">
              Edit
            </button>
          )}
        </div>

        {editing ? (
          <div className="run-info-edit-form mt-2">
            <div className="mb-2">
              <label className="form-label small mb-1">Description</label>
              <input
                type="text"
                className="form-control form-control-sm"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
              />
            </div>
            <div className="mb-2">
              <label className="form-label small mb-1">Weather</label>
              <input
                type="text"
                className="form-control form-control-sm"
                value={formWeather}
                onChange={(e) => setFormWeather(e.target.value)}
              />
            </div>
            <div className="mb-2">
              <label className="form-label small mb-1">Date</label>
              <input
                type="datetime-local"
                className="form-control form-control-sm"
                value={formDate}
                onChange={(e) => setFormDate(e.target.value)}
              />
            </div>
            <div className="mb-2">
              <label className="form-label small mb-1">Metadata (JSON)</label>
              <textarea
                className="form-control form-control-sm font-monospace"
                rows={5}
                value={formMetadataText}
                onChange={(e) => setFormMetadataText(e.target.value)}
              />
            </div>
            {error && <div className="text-danger small mb-2">{error}</div>}
            <div className="d-flex gap-2">
              <button className="btn btn-sm btn-primary" onClick={save} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button className="btn btn-sm btn-secondary" onClick={cancelEdit} disabled={saving}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <ul id="run-info-items">
              {display.date && <li>File Date: {display.date}</li>}
              {display.description && <li>Description: {display.description}</li>}
              {display.weather && <li>Weather: {display.weather}</li>}
              {display.time ? <li>Run Time: {display.time}</li> : null}
            </ul>
            {hasMetadata(display.metadata) && (
              <>
                <b>
                  <figcaption id="run-info-metadata-title">Run Metadata</figcaption>
                </b>
                <pre className="upload-format-block">{JSON.stringify(display.metadata, null, 2)}</pre>
              </>
            )}
          </>
        )}

        {selectedRun.Track && (
          <>
            <b>
              <figcaption id="run-info-track-title">Selected Track: {selectedRun.Track._id}</figcaption>
            </b>
            <ul id="run-info-track">
              {selectedRun.Track.name && <li>Track Name: {selectedRun.Track.name}</li>}
            </ul>
          </>
        )}
        {selectedRun.Driver && (
          <>
            <b>
              <figcaption id="run-info-driver-title">Selected Driver: {selectedRun.Driver._id}</figcaption>
            </b>
            <ul id="run-info-driver">
              {selectedRun.Driver.name && <li>Driver Name: {selectedRun.Driver.name}</li>}
              {selectedRun.Driver.surname && <li>Driver Surname: {selectedRun.Driver.surname}</li>}
            </ul>
          </>
        )}
      </figure>
    </>
  );
};

export default InfoVisualizer;
