const runService = require("../services/runService");
const sensorService = require("../services/sensorService");
const { toRadians } = require("../utils/units");

const getAllRuns = async () => {
  try {
    const runs = await runService.getAllRuns();
    runs.forEach((run) => {
      if (run.date) {
        run.date = run.date.toGMTString();
      } else {
      }
    });
    return runs;
  } catch (error) {
    throw new Error(error.message);
  }
};

const getSingleRun = async (runid) => {
  try {
    const run = await runService.getSingleRun(runid);

    const sensorData = await runService.getRunSensorReadings(runid);
    run.orientationData = [];

    var pitch = 0;
    var roll = 0;
    var yaw = 0;

    sensorData
      .find((item) => item._id === "gyroscope")
      .readings.forEach((element) => {
        pitch += element.data[1] / 6;
        roll += element.data[0] / 6;
        yaw += element.data[2] / 6;

        run.orientationData.push([element.timestamp, roll, yaw, pitch]);
      });
    run.data = sensorData;

    return run;
  } catch (error) {
    throw new Error(error.message);
  }
};

const filterRunsByDate = async (dateFrom, dateTo) => {
  try {
    if (dateTo === undefined) {
      dateTo = new Date();
    }
    if (dateFrom === undefined) {
      dateFrom = new Date(0);
    }
    var includeDateTo = new Date(dateTo);
    includeDateTo.setDate(includeDateTo.getDate() + 1);
    const runs = await runService.filterRunsByDate(dateFrom, includeDateTo);
    runs.forEach((run) => {
      run.date = run.date.toGMTString();
    });
    return runs;
  } catch (error) {
    throw new Error(error.message);
  }
};

const createRun = async (run) => {
  try {
    const newRun = await runService.createRun(run);
    return newRun;
  } catch (error) {
    throw new Error(error.message);
  }
};

module.exports = {
  getAllRuns,
  getSingleRun,
  filterRunsByDate,
  createRun,
};
