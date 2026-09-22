const express = require("express");
const path = require("path");
const bodyParser = require("body-parser");
const cookieParser = require("cookie-parser");
const app = express();
const cors = require("cors");
const mongoose = require("mongoose");
const { authenticateAccessToken } = require("./middleware/authenticate");

mongoose.connect(process.env.MONGODB_URI);

const allowedOrigins = process.env.ALLOWED_ORIGINS
  ? process.env.ALLOWED_ORIGINS.split(",").map((origin) => origin.trim())
  : [];

app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin || allowedOrigins.includes(origin)) {
        return callback(null, true);
      }
      return callback(new Error("Not allowed by CORS"));
    },
    credentials: true,
    methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
  })
);

app.use(express.static(path.join(__dirname, "public")));

// Video uploads are streamed directly to disk in videoRoutes — exclude them
// from body-buffering middleware to avoid loading 1 GB into RAM.
app.use((req, res, next) => {
  if (req.method === "POST" && req.path === "/video/upload") return next();
  bodyParser.raw({ type: "application/octet-stream", limit: "50mb" })(req, res, next);
});
app.use(
  bodyParser.text({
    type: ["text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"],
    limit: "50mb",
  })
);

app.use(cookieParser());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.set("views", path.join(__dirname, "views"));

const apiRoutes = require("./routes/api");
const runRoutes = require("./routes/runRoutes");
const sensorRoutes = require("./routes/sensorRoutes");
const videoRoutes = require("./routes/videoRoutes");
const authRoutes = require("./routes/authRoutes");
const contextRoutes = require("./routes/contextRoutes");
const filterRoutes = require("./routes/filterRoutes");
const pluginRoutes = require("./routes/pluginRoutes");

app.use("/auth", authRoutes);
app.use(authenticateAccessToken);
app.use("/api", apiRoutes);
app.use("/context", contextRoutes);
app.use("/run", runRoutes);
app.use("/sensor", sensorRoutes);
app.use("/video", videoRoutes);
app.use("/filters", filterRoutes);
app.use("/plugins", pluginRoutes);

module.exports = app;
