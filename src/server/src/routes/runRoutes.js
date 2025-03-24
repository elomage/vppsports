const express = require("express");
const router = express.Router();
const runController = require("../controllers/runController");
const trackController = require("../controllers/trackController");
const driverController = require("../controllers/driverController");
const { parseApiDataObject } = require("../controllers/sensorDataController");

router.get("/", async (req, res) => {
  try {
    const { dateFrom: dateFrom, dateTo: dateTo } = req.query;
    if (dateFrom || dateTo) {
      const runs = await runController.filterRunsByDate(dateFrom, dateTo);
      res.json(runs);
    } else {
      const runs = await runController.getAllRuns();
      res.json(runs);
    }
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching drivers", error: error.message });
  }
});

router.get("/:runid", async (req, res) => {
  try {
    const { dateFrom, dateTo } = req.query;

    const { filterData } = req.query;
    const runid = req.params.runid;
    var runs = null;
    if (dateFrom && dateTo) {
      runs = await runController.filterRunsByDate(dateFrom, dateTo);
    } else {
      runs = await runController.getAllRuns();
    }

    var selectedRun = null;
    if (filterData == "true") {
      selectedRun = await runController.getSingleRunKalmanFilter(runid);
    } else {
      selectedRun = await runController.getSingleRun(runid);
    }

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

router.post("/", async (req, res) => {
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

router.post("/filter-runs", async (req, res) => {
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

module.exports = router;
