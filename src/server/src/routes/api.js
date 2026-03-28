const express = require("express");
const router = express.Router();
const driverController = require("../controllers/driverController");
const { parseApiDataObject } = require("../controllers/sensorDataController");
const runController = require("../controllers/runController");

router.get("/drivers", async (req, res) => {
  try {
    const drivers = await driverController.getAllDrivers();
    res.json(drivers);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching drivers", error: error.message });
  }
});

// struct SensorRecord {
//     uint32_t timestamp_us;
//     int32_t x;
//     int32_t y;
//     int32_t z;
// };

//Test endpoint for receiving data from the API
router.post("/data/V1", (req, res) => {
  const data = Buffer.from(req.body);

  console.log(data);
  console.log(data.length);
  console.log(parseApiDataObject(data));

  res.status(200).json({ message: "Data received" });
});

router.get("/runs", async (req, res) => {
  try {
    const runs = await runController.getAllRuns();
    const visibleRuns =
      req.user?.role === "admin"
        ? runs
        : runs.filter((run) =>
            (req.user?.contexts || []).some(
              (context) =>
                String(context?.id || "") === String(run.contextId || "") ||
                String(context?.name || "").trim().toLowerCase() ===
                  String(run.context || "").trim().toLowerCase()
            )
          );
    res.json(visibleRuns);
  } catch (error) {
    res
      .status(500)
      .json({ message: "Error fetching runs", error: error.message });
  }
});

router.post("/drivers", async (req, res) => {
  const newDriver = await driverController.createDriver(req, res);
  res.json(newDriver);
});

module.exports = router;
