const express = require("express");
const router = express.Router();
const runController = require("../controllers/runController");
const trackController = require("../controllers/trackController");
const driverController = require("../controllers/driverController");
const { parseApiDataObject } = require("../controllers/sensorDataController");

router.get("/", async (req, res) => {
  try {
    const runs = await runController.getAllRuns();
    res.json(runs);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching drivers", error: error.message });
  }
});

router.get("/:runid", async (req, res) => {
  try {
    const { dateFrom, dateTo } = req.query;
    const runid = req.params.runid;
    var runs = null;
    if (dateFrom && dateTo) {
      runs = await runController.filterRunsByDate(dateFrom, dateTo);
    } else {
      runs = await runController.getAllRuns();
    }
    const selectedRun = await runController.getSingleRun(runid);

    const runTrack = await trackController.getSingleTrack(selectedRun.trackid);
    const runDriver = await driverController.getSingleDriver(
      selectedRun.driverid
    );

    selectedRun.Track = runTrack;
    selectedRun.Driver = runDriver;

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

module.exports = router;
