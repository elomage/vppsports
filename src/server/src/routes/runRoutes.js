const express = require("express");
const runRouter = express.Router();
const sensorRouter = express.Router({ mergeParams: true });
const sensorDataRouter = express.Router({ mergeParams: true });

const runController = require("../controllers/runController");
const trackController = require("../controllers/trackController");
const driverController = require("../controllers/driverController");
const { parseApiDataObject } = require("../controllers/sensorDataController");

runRouter.use("/:runid/sensor", sensorRouter);
sensorRouter.use("/:sensorid", sensorDataRouter);

runRouter.get("/", async (req, res) => {
  try {
    const { dateFrom: dateFrom, dateTo: dateTo } = req.query;
    if (dateFrom || dateTo) {
      const runs = await runController.filterRunsByDate(dateFrom, dateTo);
      res.json(runs);
    } else {
      const runs = await runController.getAllRuns();
      // const runs = await runController.getAllRunsDB();
      res.json(runs);
    }
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching drivers", error: error.message });
  }
});

runRouter.get("/:runid", async (req, res) => {
  try {
    // const { dateFrom, dateTo } = req.query;

    // const { filterData } = req.query;
    const runid = req.params.runid;
    // var runs = null;
    // if (dateFrom && dateTo) {
    //   runs = await runController.filterRunsByDate(dateFrom, dateTo);
    // } else {
    //   runs = await runController.getAllRuns();
    // }

    let selectedRun = null;
    // if (filterData == "true") {
    //   // selectedRun = await runController.getSingleRunKalmanFilter(runid);
    //   selectedRun = await runController.getSingleRunMovingAverage(runid);
    //   // selectedRun = await runController.getSingleRunSavitzkyGolayFilter(runid);
    // } else {
    //   selectedRun = await runController.getSingleRunDB(runid);
    // }

    selectedRun = await runController.getSingleRunDB(runid);

    // const selectedRun = await runController.getSingleRun(runid);
    // const runTrack = await trackController.getSingleTrack(selectedRun.trackid);
    // const runDriver = await driverController.getSingleDriver(
    //   selectedRun.driverid
    // );

    // selectedRun.Track = runTrack;
    // selectedRun.Driver = runDriver;

    res.json(selectedRun);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching run", error: error.message });
  }
});

runRouter.post("/", async (req, res) => {
  try {
    const message = JSON.parse(data.toString());
    console.log(message.type);

    const data = Buffer.from(req.body);
    var parsedData = parseApiDataObject(data);

    // const newRun = await runController.createRun(parsedData);

    res.json(newRun);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error creating run", error: error.message });
  }
});

runRouter.post("/filter-runs", async (req, res) => {
  try {
    const { "date-from": dateFrom, "date-to": dateTo } = req.body;
    const filteredRuns = await runController.filterRunsByDate(dateFrom, dateTo);
    // res.render("dashboard", {
    //   title: "Runs",
    //   runs: filteredRuns,
    //   selectedRun: null,
    //   dateFrom: dateFrom,
    //   dateTo: dateTo,
    // });
    return res.json(filteredRuns);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error filtering runs", error: error.message });
  }
});

sensorRouter.get("/", async (req, res) => {
  try {
    const runid = req.params.runid;
    const sensors = await runController.getRunSensors(runid);
    res.json(sensors);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching sensors", error: error.message });
  }
});

sensorRouter.get("/orientation", async (req, res) => {
  try {
    const runid = req.params.runid;
    const { accelerometerid, gyroscopeid, magnetometerid } = req.query;

    const orientationData = await runController.getRunSensorOrientationData(
      runid,
      accelerometerid,
      gyroscopeid,
      magnetometerid
    );

    return res.json(orientationData);
  } catch (err) {
    res.status(500).json({
      message: "Error fetching sensor orientation",
      error: err.message,
    });
  }
});

sensorRouter.get("/:sensorid", async (req, res) => {
  try {
    const runid = req.params.runid;
    const sensorid = req.params.sensorid;
    const sensorData = await runController.getRunSensorData(runid, sensorid);
    res.json(sensorData);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching sensor data", error: error.message });
  }
});

//TODO: Implement the filtering passing and array of filters to use and recieving filtered data
sensorDataRouter.get("/data", async (req, res) => {
  try {
    const { filters } = req.query;
    const runid = req.params.runid;
    const sensorid = req.params.sensorid;
    const sensorData = await runController.getRunSensorData(runid, sensorid);

    const filteredSensorData = runController.filterSensorData(
      sensorData,
      filters
    );

    res.json(filteredSensorData);
  } catch (err) {
    res.status(500).json({
      message: "Error fetching sensor data",
      error: err.message,
    });
  }
});

module.exports = runRouter;
