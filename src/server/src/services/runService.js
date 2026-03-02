const { connectDB, getCollection } = require("../config/db");
const { ObjectId } = require("mongodb");
const { MongoClient } = require("mongodb");
const { default: mongoose } = require("mongoose");

const runSchema = new mongoose.Schema({
  name: { type: String, required: true, default: "" },
  date: { type: Date, required: true, default: Date.now },
  sensorCount: { type: Number, default: 0 },
  description: { type: String, default: "" },
  driverid: {
    type: mongoose.Schema.Types.ObjectId,
    ref: "Driver",
    required: true,
  },
  trackid: {
    type: mongoose.Schema.Types.ObjectId,
    ref: "Track",
    required: true,
  },
  weather: { type: String, default: "" },
});

const sensorReadingSchema = new mongoose.Schema({
  sensorId: {
    type: Number,
    required: true,
  },
  timestamp: { type: Number, required: true },
  data: {
    type: [Number],
    required: true,
  },
  runId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: "Run",
    required: true,
  },
});

const Run = mongoose.model("Run", runSchema);
const SensorReading = mongoose.model(
  "SensorReading",
  sensorReadingSchema,
  "sensor_readings"
);

const fs = require("fs").promises;
const path = require("path");
// const folderPath = "C:/Users/Reinis/Documents/VPPSport/Code/SensorTextFiles";

const folderPath = "C:/Users/Reinis/Documents/VPPSport/VijolesVideo";

const getAllRuns = async () => {
  try {
    const files = await fs.readdir(folderPath);
    const result = files.map((file) => ({ _id: file }));
    return result;
  } catch (error) {
    console.error("Error reading folder:", error);
    throw error;
  }
};

// const getSingleRun = async (runid) => {
//   const filePath = path.join(folderPath, `${runid}`);

//   try {
//     const fileContents = await fs.readFile(filePath, "utf-8");
//     return fileContents;
//   } catch (error) {
//     console.error("Error reading file:", error);
//     throw error;
//   }
// };
const getSingleRun = async (runid) => {
  const faultOffset = 64300;

  const offsetTimestampArray = [];

  const filePath = path.join(
    folderPath,
    `${runid}`,
    `${runid}` + "Accelerometer.txt"
  );

  const gyroscopeFilePath = path.join(
    folderPath,
    `${runid}`,
    `${runid}` + "Gyroscope.txt"
  );

  const magnetometerFilePath = path.join(
    folderPath,
    `${runid}`,
    `${runid}` + "Magnetometer.txt"
  );

  const faultAccelerometerFilePath = path.join(
    folderPath,
    `${runid}`,
    `${runid}` + "AccelerometerIncorrect.txt"
  );

  const faultGyroscopeFilePath = path.join(
    folderPath,
    `${runid}`,
    `${runid}` + "GyroscopeIncorrect.txt"
  );

  try {
    const fileContents = await fs.readFile(filePath, "utf-8");
    const fileStats = await fs.stat(filePath);
    const lines = fileContents.split("\n").filter((line) => line.trim() !== "");

    const data = lines.map((line) => {
      const [timestamp, ...values] = line.split(",").map(Number);
      return {
        sensorId: 3,
        timestamp,
        data: values,
        sensorDetails: {
          _id: "66f54a206e1033335199a3b7",
          type: "accelerometer",
          location: "body",
          vehicleId: null,
          dataAxis: 3,
          id: 3,
        },
      };
    });

    for (let i = 0; i < faultOffset; i++) {
      offsetTimestampArray.push({
        sensorId: 4,
        timestamp: data[i].timestamp,
        data: [0, 0, 0],
        sensorDetails: {
          _id: "66f54a206e1033335199a3b7",
          type: "fault",
          location: "body",
          vehicleId: null,
          dataAxis: 3,
          id: 4,
        },
      });
    }

    const result = {
      _id: runid,
      date: fileStats.birthtime,
      data: [
        data.length > 0
          ? {
              _id: "accelerometer",
              dataAxis: 3,
              readings: data,
            }
          : null,
      ].filter(Boolean), // Remove null entries
    };

    try {
      const faultfileContents = await fs.readFile(
        faultAccelerometerFilePath,
        "utf-8"
      );
      const lines = faultfileContents
        .split("\n")
        .filter((line) => line.trim() !== "");

      // Assuming "offset" is defined in the outer scope or passed as a parameter.
      const faultdata = lines.map((line) => {
        const [timestamp, ...values] = line.split(",").map(Number);
        return {
          sensorId: 4,
          timestamp:
            timestamp +
            offsetTimestampArray[offsetTimestampArray.length - 1].timestamp,
          data: values,
          sensorDetails: {
            _id: "66f54a206e1033335199a3b7",
            type: "fault",
            location: "body",
            vehicleId: null,
            dataAxis: 3,
            id: 4,
          },
        };
      });

      const combinedFaultReadings = offsetTimestampArray.concat(faultdata);

      result.data.push({
        _id: "fault",
        dataAxis: 3,
        readings: combinedFaultReadings,
      });
    } catch (error) {
      console.warn("Error reading fault_accelerometer file:", error.message);
    }

    try {
      const faultGyrofileContents = await fs.readFile(
        faultGyroscopeFilePath,
        "utf-8"
      );
      const lines = faultGyrofileContents
        .split("\n")
        .filter((line) => line.trim() !== "");

      // Assuming "offset" is defined in the outer scope or passed as a parameter.
      const faultdata = lines.map((line) => {
        const [timestamp, ...values] = line.split(",").map(Number);
        return {
          sensorId: 4,
          timestamp:
            timestamp +
            offsetTimestampArray[offsetTimestampArray.length - 1].timestamp,
          data: values,
          sensorDetails: {
            _id: "66f54a206e1033335199a3b7",
            type: "fault",
            location: "body",
            vehicleId: null,
            dataAxis: 3,
            id: 4,
          },
        };
      });

      const combinedFaultReadings = offsetTimestampArray.concat(faultdata);

      result.data.push({
        _id: "faultGyro",
        dataAxis: 3,
        readings: combinedFaultReadings,
      });
    } catch (error) {
      console.warn("Error reading fault_accelerometer file:", error.message);
    }

    try {
      const gyrofileContents = await fs.readFile(gyroscopeFilePath, "utf-8");
      const gyrolines = gyrofileContents
        .split("\n")
        .filter((line) => line.trim() !== "");

      const gyrodata = gyrolines.map((line) => {
        const [timestamp, ...values] = line.split(",").map(Number);
        return {
          sensorId: 2,
          timestamp,
          data: values,
          sensorDetails: {
            _id: "66f54a206e1033335199a3b7",
            type: "gyroscope",
            location: "body",
            vehicleId: null,
            dataAxis: 3,
            id: 2,
          },
        };
      });

      result.data.push({
        _id: "gyroscope",
        dataAxis: 3,
        readings: gyrodata,
      });
    } catch (error) {
      console.warn("Error reading gyroscope file:", error.message);
    }

    try {
      const magfileContents = await fs.readFile(magnetometerFilePath, "utf-8");
      const maglines = magfileContents
        .split("\n")
        .filter((line) => line.trim() !== "");

      const magdata = maglines.map((line) => {
        const [timestamp, ...values] = line.split(",").map(Number);
        return {
          sensorId: 1,
          timestamp,
          data: values,
          sensorDetails: {
            _id: "66f54a206e1033335199a3b7",
            type: "magnetometer",
            location: "body",
            vehicleId: null,
            dataAxis: 3,
            id: 1,
          },
        };
      });

      result.data.push({
        _id: "magnetometer",
        dataAxis: 3,
        readings: magdata,
      });
    } catch (error) {
      console.warn("Error reading magnetometer file:", error.message);
    }

    return result;
  } catch (error) {
    if (error.code === "ENOENT") {
      console.error("File not found:", error);
      throw new Error(`File not found: ${error.path}`);
    } else {
      console.error("Error reading file:", error);
      throw error;
    }
  }
};

/**
 * Retrieves all runs from the 'Run' collection in the database.
 *
 * This function connects to the database, accesses the 'Run' collection,
 * and retrieves all documents.
 *
 * @async
 * @returns {Promise<Array>} A promise that resolves to an array of run documents.
 */
const getAllRunsDB = async () => {
  // const db = await connectDB();
  // const coll = await getCollection(db, "Run");
  // const result = await coll
  //   .find({}, { projection: { _id: 1, date: 1 } })
  //   .sort({ date: -1 })
  //   .toArray();
  // return result;

  // return await Run.find({});
  const runs = await Run.find({}, { _id: 1, date: 1, name: 1 }).sort({
    date: -1,
  });
  return runs.map(withRunName);
};

/**
 * Retrieves a single run document from the database by its ID.
 *
 * @param {string} runid - The ID of the run to retrieve.
 * @returns {Promise<Object|null>} A promise that resolves to the run document if found, or null if not found.
 */
const getSingleRunDB = async (runid) => {
  // const db = await connectDB();
  // const coll = await getCollection(db, "Run");
  // const objectId = new ObjectId(String(runid));
  // const result = await coll.findOne({ _id: objectId });

  const run = await Run.findById(runid);
  return withRunName(run);
};

/**
 * Filters runs by a date range.
 *
 * @param {string} dateFrom - The start date of the range in ISO format.
 * @param {string} dateTo - The end date of the range in ISO format.
 * @returns {Promise<Array>} A promise that resolves to an array of runs within the specified date range.
 */
const filterRunsByDateDB = async (dateFrom, dateTo) => {
  const db = await connectDB();
  const coll = await getCollection(db, "runs");
  const result = await coll
    .find(
      {
        date: {
          $gte: new Date(dateFrom),
          $lte: new Date(dateTo),
        },
      },
      { projection: { _id: 1, date: 1, name: 1 } }
    )
    .sort({ date: -1 })
    .toArray();
  return result.map(withRunName);
};

/**
 * Filters runs by a date range.
 *
 * @param {string} dateFrom - The start date of the range in ISO format.
 * @param {string} dateTo - The end date of the range in ISO format.
 * @returns {Promise<Array>} A promise that resolves to an array of runs within the specified date range.
 */
const filterRunsByDate = async (dateFrom, dateTo) => {
  return filterRunsByDateDB(dateFrom, dateTo);
};

const getRunSensorReadingsAll = async (runid) => {
  // const db = await connectDB();
  // const sensorDataColl = await getCollection(db, "SensorReading");

  const objectId = new ObjectId(String(runid));

  //ALERTNATIVE QUERY

  // const sensorData = await sensorDataColl.aggregate([
  //   {
  //     $match: { batchId: objectId }
  //   },
  //   {
  //     $lookup: {
  //       from: 'Sensor',
  //       localField: 'sensorId',
  //       foreignField: '_id',
  //       as: 'sensorDetails'
  //     }
  //   },
  //   {
  //     $unwind: '$sensorDetails'
  //   },
  //   {
  //     $group: {
  //       _id: '$sensorDetails.type',
  //       dataAxis: { $first: '$sensorDetails.dataAxis' },
  //       readings: { $push: '$$ROOT' }
  //     }
  //   }
  // ]).toArray();

  // const sensorData = await sensorDataColl
  //   .aggregate([
  //     {
  //       $match: { batchId: objectId },
  //     },
  //     {
  //       $lookup: {
  //         from: "Sensor",
  //         localField: "sensorId",
  //         foreignField: "id",
  //         as: "sensorDetails",
  //       },
  //     },
  //     {
  //       $unwind: "$sensorDetails",
  //     },
  //     {
  //       $group: {
  //         _id: "$sensorDetails.type",
  //         dataAxis: { $first: "$sensorDetails.dataAxis" },
  //         readings: { $push: "$$ROOT" },
  //       },
  //     },
  //   ])
  //   .toArray();

  // const sensorData = await sensorDataColl
  //   .aggregate([
  //     {
  //       $match: { batchId: objectId },
  //     },
  //     {
  //       $lookup: {
  //         from: "Sensor",
  //         localField: "sensorId",
  //         foreignField: "id",
  //         as: "sensorDetails",
  //       },
  //     },
  //   ])
  //   .toArray();

  // const sensorData = await SensorReading.aggregate([
  //   {
  //     $match: { runId: objectId },
  //   },
  //   {
  //     $lookup: {
  //       from: "sensors",
  //       localField: "sensorId",
  //       foreignField: "id",
  //       as: "sensorDetails",
  //     },
  //   },
  //   {
  //     $unwind: "$sensorDetails",
  //   },
  //   {
  //     $group: {
  //       _id: "$sensorId",
  //       sensorType: { $first: "$sensorDetails.type" },
  //       dataAxis: { $first: "$sensorDetails.dataAxis" },
  //       readings: { $push: "$$ROOT" },
  //     },
  //   },
  // ]);

  const sensorData = await SensorReading.aggregate([
    {
      $match: { runId: objectId },
    },
    {
      $lookup: {
        from: "sensors",
        localField: "sensorId",
        foreignField: "id",
        as: "sensorDetails",
      },
    },
  ]);

  // const sensorData = await SensorReading.find({ runId: objectId });
  return sensorData;
};

const getRunSensorReadings = async (runid, sensorid) => {
  const sensorData = await SensorReading.find({
    runId: runid,
    sensorId: sensorid,
  });
  return sensorData;
};

const getRunOrientationData = async (runid, gyroscopeSensorId) => {
  let result = [];

  let gyroReadings = await SensorReading.find({
    runId: runid,
    sensorId: gyroscopeSensorId,
  });

  let pitch = 0;
  let roll = 0;
  let yaw = 0;

  gyroReadings.forEach((element) => {
    pitch += element.data[1] / 6;
    roll += element.data[0] / 6;
    yaw += element.data[2] / 6;

    result.push([element.timestamp, roll, yaw, pitch]);
  });
  return result;
};

const getTotalTimestamps = async (runid) => {
  const timestamps = await SensorReading.find({ runId: runid })
    .select({ timestamp: 1 })
    .exec();

  return [...new Set(timestamps.map((entry) => entry.timestamp))].sort(
    (a, b) => a - b
  );
};

const getSensor = async (sensorId) => {
  const db = await connectDB();
  const sensorColl = await getCollection(db, "Sensor");
  const objectId = new ObjectId(String(sensorId));
  const sensor = await sensorColl.findOne({ _id: objectId });
  return sensor;
};

const createRun = async (run) => {
  const client = new MongoClient(process.env.MONGODB_URI);

  var runId1 = null;

  try {
    await client.connect();
    const session = client.startSession();

    const db = client.db();
    const sensorReadingColl = await getCollection(db, "SensorReading");
    const runColl = await getCollection(db, "Run");

    session.startTransaction();

    try {
      const runDocument = { name: "Unnamed Run", date: new Date() };
      const runResult = await runColl.insertOne(runDocument);
      const runId = runResult.insertedId;

      runId1 = runId;

      for (const SensorData of run.SensorData) {
        for (const measurement of SensorData.Measurements) {
          const sensorReading = {
            batchId: runId,
            sensorId: SensorData.SensorID,
            timestamp: measurement.TimeFromStartInus,
            data: measurement.Measurements,
          };

          await sensorReadingColl.insertOne(sensorReading);
        }
      }

      await session.commitTransaction();
    } catch (error) {
      await session.abortTransaction();
      throw error;
    } finally {
      session.endSession();
    }
  } finally {
    await client.close();
  }
  return runId1;
};

const getRunSensors = async (runid) => {
  try {
    const sensors = await SensorReading.distinct("sensorId", { runId: runid });
    return sensors;
  } catch (err) {
    throw new Error(err.message);
  }
};

module.exports = {
  getAllRunsDB,
  getSingleRunDB,
  filterRunsByDateDB,
  getAllRuns,
  getSingleRun,
  filterRunsByDate,
  createRun,
  getRunOrientationData,
  getTotalTimestamps,
  getRunSensorReadings,
  getRunSensorReadingsAll,
  getRunSensors,
};
const withRunName = (run) => {
  if (!run) return run;
  const normalized =
    typeof run.toObject === "function" ? run.toObject() : { ...run };
  const fallbackId =
    normalized && normalized._id ? String(normalized._id) : "Unknown";
  normalized.name =
    normalized.name && String(normalized.name).trim()
      ? String(normalized.name).trim()
      : `Run ${fallbackId}`;
  return normalized;
};
