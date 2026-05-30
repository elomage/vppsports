import { useState } from "react";
import { exportAprioriCsv, exportMultiRunCsv } from "./api";

const CSV_FIELD_GROUPS = [
  { key: "runId", label: "Run ID" },
  { key: "runName", label: "Run Name" },
  { key: "runDate", label: "Run Date" },
  { key: "context", label: "Context" },
  { key: "sensorId", label: "Sensor ID" },
  { key: "sensorType", label: "Sensor Type" },
  { key: "timestamp", label: "Timestamp" },
  { key: "sensorValues", label: "Sensor Values" },
  { key: "labels", label: "Labels" },
  { key: "labelStats", label: "Label Stats" },
];

const ALL_FIELDS_ON = Object.fromEntries(CSV_FIELD_GROUPS.map(({ key }) => [key, true]));
const ALL_FIELDS_OFF = Object.fromEntries(CSV_FIELD_GROUPS.map(({ key }) => [key, false]));

const MultiRunExport = ({ runs }) => {
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [isExporting, setIsExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState({ type: "idle", message: "" });
  const [csvFields, setCsvFields] = useState(() => ({ ...ALL_FIELDS_ON }));
  const [numBins, setNumBins] = useState(3);

  const toggleSelection = (runId, checked) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(runId);
      else next.delete(runId);
      return next;
    });
  };

  const toggleCsvField = (key) =>
    setCsvFields((prev) => ({ ...prev, [key]: !prev[key] }));

  const enabledCsvFields = CSV_FIELD_GROUPS.filter(({ key }) => csvFields[key]).map(({ key }) => key);

  const triggerDownload = (blob, fileName) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleExport = async () => {
    if (isExporting || selectedIds.size === 0) return;

    setIsExporting(true);
    setExportStatus({ type: "info", message: `Exporting ${selectedIds.size} run(s) as CSV...` });

    try {
      const { blob, fileName } = await exportMultiRunCsv([...selectedIds], enabledCsvFields);
      triggerDownload(blob, fileName);
      setExportStatus({ type: "success", message: `Exported ${selectedIds.size} run(s) as CSV.` });
    } catch (error) {
      setExportStatus({
        type: "error",
        message: error instanceof Error ? error.message : "CSV export failed.",
      });
    } finally {
      setIsExporting(false);
    }
  };

  const handleAprioriExport = async () => {
    if (isExporting || selectedIds.size === 0) return;

    setIsExporting(true);
    setExportStatus({
      type: "info",
      message: `Building Apriori CSV for ${selectedIds.size} run(s) with ${numBins} bins...`,
    });

    try {
      const { blob, fileName } = await exportAprioriCsv([...selectedIds], numBins);
      triggerDownload(blob, fileName);
      setExportStatus({
        type: "success",
        message: `Exported Apriori CSV (${numBins} bins, ${selectedIds.size} run(s)).`,
      });
    } catch (error) {
      setExportStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Apriori CSV export failed.",
      });
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="upload-card col m-2">
      <h3>Run export</h3>
      <div>
        <strong>Select runs to combine into a single CSV dataset</strong>
      </div>
      {runs.length === 0 ? (
        <div className="upload-status">No runs available.</div>
      ) : (
        <div
          style={{
            maxHeight: "240px",
            overflowY: "auto",
            border: "1px solid #dee2e6",
            borderRadius: "4px",
            padding: "6px",
          }}
        >
          {runs.map((run) => (
            <div
              key={run._id}
              style={{ display: "flex", alignItems: "center", gap: "8px", padding: "2px 0" }}
            >
              <input
                type="checkbox"
                id={`multi-run-${run._id}`}
                checked={selectedIds.has(run._id)}
                onChange={(e) => toggleSelection(run._id, e.target.checked)}
                disabled={isExporting}
              />
              <label
                htmlFor={`multi-run-${run._id}`}
                style={{ margin: 0, cursor: "pointer" }}
              >
                {run.name || run._id}
                {run.date ? ` — ${new Date(run.date).toLocaleDateString()}` : ""}
              </label>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: "10px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "4px",
          }}
        >
          <strong style={{ fontSize: "0.85em" }}>CSV fields</strong>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px" }}>
          {CSV_FIELD_GROUPS.map(({ key, label }) => (
            <label
              key={key}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "4px",
                fontSize: "0.85em",
                cursor: "pointer",
                userSelect: "none",
              }}
            >
              <input
                type="checkbox"
                checked={csvFields[key]}
                onChange={() => toggleCsvField(key)}
                disabled={isExporting}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <div className="upload-actions" style={{ marginTop: "8px" }}>
        <button
          className="btn btn-outline-primary"
          type="button"
          onClick={handleExport}
          disabled={isExporting || selectedIds.size === 0 || enabledCsvFields.length === 0}
        >
          {isExporting
            ? "Exporting..."
            : `Export CSV`}
        </button>
        {selectedIds.size > 0 && (
          <button
            className="btn btn-outline-secondary btn-sm"
            type="button"
            onClick={() => setSelectedIds(new Set())}
            disabled={isExporting}
          >
            Clear
          </button>
        )}
      </div>
        <button
          style={{ marginTop: "10px" }}
          className="btn btn-outline-success"
          type="button"
          onClick={handleAprioriExport}
          disabled={isExporting || selectedIds.size === 0}
        >
          {isExporting ? "Exporting..." : `Export discretized CSV`}
        </button>
      {exportStatus.message && (
        <div
          className={`upload-status ${exportStatus.type !== "idle" ? `is-${exportStatus.type}` : ""}`}
        >
          {exportStatus.message}
        </div>
      )}
    </div>
  );
};

export default MultiRunExport;
