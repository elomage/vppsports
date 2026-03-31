const path = require("path");

const VIDEO_STORAGE_ROOT = path.resolve(__dirname, "..", "..", "storage", "videos");

const getRunVideoDirectory = (runId) => {
  return path.join(VIDEO_STORAGE_ROOT, String(runId || "").trim());
};

const getRunVideoPath = (runId) => {
  const normalizedRunId = String(runId || "").trim();
  return path.join(getRunVideoDirectory(normalizedRunId), `${normalizedRunId}.mp4`);
};

module.exports = {
  VIDEO_STORAGE_ROOT,
  getRunVideoDirectory,
  getRunVideoPath,
};
