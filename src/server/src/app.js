const express = require("express");
const path = require("path");
const bodyParser = require("body-parser");
const app = express();
const cors = require("cors");

// Configure CORS middleware
// const allowedOrigins = process.env.ALLOWED_ORIGINS
//   ? process.env.ALLOWED_ORIGINS.split(",")
//   : [];

// app.use(
//   cors({
//     origin: (origin, callback) => {
//       if (!origin) return callback(null, true);
//       if (allowedOrigins.includes(origin)) {
//         return callback(null, true);
//       } else {
//         return callback(new Error("Not allowed by CORS"));
//       }
//     },
//     methods: ["GET", "POST"],
//   })
// );

app.use(cors());

app.use(express.static(path.join(__dirname, "public")));

app.use(bodyParser.raw({ type: "application/octet-stream" }));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.set("views", path.join(__dirname, "views"));

const apiRoutes = require("./routes/api");
const runRoutes = require("./routes/runRoutes");
const sensorRoutes = require("./routes/sensorRoutes");
const videoRoutes = require("./routes/videoRoutes");

app.use("/api", apiRoutes);
app.use("/run", runRoutes);
app.use("/sensor", sensorRoutes);
app.use("/video", videoRoutes);

module.exports = app;
