const express = require("express");
const path = require("path");
const fs = require("fs");
const { pipeline } = require("stream");
const router = express.Router();

router.get("/:videoName", (req, res) => {
  const videoName = req.params.videoName;
  // const videoDir = path.resolve(
  //   "C:/Users/Reinis/Documents/VPPSport/VijolesVideo/"
  // );
  const videoDir = path.resolve("C:/Users/Reinis/Documents/VPPSport/video/");

  const videoPath = path.join(videoDir, videoName, `${videoName}.mp4`);

  fs.stat(videoPath, (err, stats) => {
    if (err || !stats.isFile()) {
      console.error(err);
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
