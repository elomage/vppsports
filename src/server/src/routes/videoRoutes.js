const express = require("express");
const fs = require("fs");
const { pipeline } = require("stream");
const { connectDB, getCollection } = require("../config/db");
const { ObjectId } = require("mongodb");
const {
  VIDEO_STORAGE_ROOT,
  getRunVideoDirectory,
  getRunVideoPath,
} = require("../utils/videoStorage");
const router = express.Router();

const normalizeContext = (value) => {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  return normalized || null;
};

const isGlobalAdmin = (user) => user?.role === "admin";

const getUserContexts = (user) =>
  Array.isArray(user?.contexts)
    ? user.contexts
        .map((context) => normalizeContext(context?.name))
        .filter(Boolean)
    : [];

const getUserContextIds = (user) =>
  Array.isArray(user?.contexts)
    ? user.contexts
        .map((context) =>
          ObjectId.isValid(context?.id) ? new ObjectId(context.id) : null
        )
        .filter(Boolean)
    : [];

const buildRunAccessQuery = (user) => {
  if (isGlobalAdmin(user)) {
    return {};
  }

  const contexts = getUserContexts(user);
  const contextIds = getUserContextIds(user);
  if (contexts.length === 0 && contextIds.length === 0) {
    return { _id: { $exists: false } };
  }

  const filters = [];
  if (contexts.length > 0) {
    filters.push({ context: { $in: contexts } });
  }
  if (contextIds.length > 0) {
    filters.push({ contextId: { $in: contextIds } });
  }

  return filters.length === 1 ? filters[0] : { $or: filters };
};

const ONE_GB = 1024 * 1024 * 1024;

router.post("/upload", async (req, res) => {
  const runId = String(req.query.runId || "").trim();
  if (!ObjectId.isValid(runId)) {
    return res.status(400).json({ message: "A valid runId is required." });
  }

  let db, run;
  try {
    db = await connectDB();
    const runsColl = await getCollection(db, "runs");
    run = await runsColl.findOne({
      _id: new ObjectId(runId),
      ...buildRunAccessQuery(req.user),
    });
  } catch (error) {
    return res.status(500).json({ message: "Database error.", error: error.message });
  }

  if (!run) {
    return res.status(404).json({ message: "Run not found." });
  }

  const videoDirectory = getRunVideoDirectory(runId);
  const videoPath = getRunVideoPath(runId);

  try {
    await fs.promises.mkdir(videoDirectory, { recursive: true });
  } catch (error) {
    return res.status(500).json({ message: "Failed to create video directory.", error: error.message });
  }

  const writeStream = fs.createWriteStream(videoPath);
  let bytesReceived = 0;
  let sizeLimitExceeded = false;

  await new Promise((resolve, reject) => {
    req.on("data", (chunk) => {
      bytesReceived += chunk.length;
      if (!sizeLimitExceeded && bytesReceived > ONE_GB) {
        sizeLimitExceeded = true;
        req.destroy(new Error("File exceeds 1 GB limit"));
        writeStream.destroy();
      }
    });

    req.pipe(writeStream);
    writeStream.on("finish", resolve);
    writeStream.on("error", reject);
    req.on("error", reject);
  }).then(() => {
    return res.status(201).json({
      message: "Video uploaded successfully.",
      runId,
      path: videoPath,
      storageRoot: VIDEO_STORAGE_ROOT,
    });
  }).catch(async (error) => {
    // Clean up partial file on error
    try { await fs.promises.unlink(videoPath); } catch (_) { /* ignore */ }

    if (sizeLimitExceeded || error.message === "File exceeds 1 GB limit") {
      return res.status(413).json({ message: "File exceeds 1 GB limit." });
    }
    return res.status(500).json({ message: "Error uploading video.", error: error.message });
  });
});

router.get("/:videoName", (req, res) => {
  const videoName = req.params.videoName;

  const videoPath = getRunVideoPath(videoName);

  fs.stat(videoPath, (err, stats) => {
    if (err || !stats.isFile()) {
      return res.status(404).send("Video not found");
    }

    const fileSize = stats.size;
    const range = req.headers.range;

    if (range) {
      const parts = range.replace(/bytes=/, "").split("-");
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;

      if (isNaN(start) || isNaN(end) || start > end || start >= fileSize) {
        return res.status(416).send("Requested range not satisfiable");
      }

      const chunkSize = end - start + 1;
      const file = fs.createReadStream(videoPath, { start, end });
      const head = {
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Accept-Ranges": "bytes",
        "Content-Length": chunkSize,
        "Content-Type": "video/mp4",
        "Cache-Control": "public, max-age=31536000",
      };
      res.writeHead(206, head);
      pipeline(file, res, (err) => {
        if (err) {
          console.error("Stream error:", err);
          res.sendStatus(500);
        }
      });
    } else {
      res.sendFile(videoPath, {
        headers: {
          "Content-Length": fileSize,
          "Content-Type": "video/mp4",
          "Cache-Control": "public, max-age=31536000",
        },
      });
    }
  });
});

module.exports = router;
