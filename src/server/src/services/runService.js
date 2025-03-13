const { connectDB, getCollection } = require("../config/db");
const { ObjectId } = require("mongodb");
const { MongoClient } = require("mongodb");

const fs = require("fs").promises;
const path = require("path");
const folderPath = "C:/Users/Reinis/Documents/VPPSport/Code/SensorTextFiles";

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
  const filePath = path.join(folderPath, `${runid}`);

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

    const result = {
      _id: runid,
      // date: new Date(), // Assuming the date is the current date, you can modify this as needed
      date: fileStats.birthtime,
      data: [
        {
          _id: "accelerometer",
          dataAxis: 3,
          readings: data,
        },
      ],
    };

    return result;
  } catch (error) {
    console.error("Error reading file:", error);
    throw error;
  }
};

/**
 * Filters runs by a date range.
 *
 * @param {string} dateFrom - The start date of the range in ISO format.
 * @param {string} dateTo - The end date of the range in ISO format.
 * @returns {Promise<Array>} A promise that resolves to an array of runs within the specified date range.
 */
const filterRunsByDate = async (dateFrom, dateTo) => {
  const db = await connectDB();
  const coll = await getCollection(db, "Run");
  const result = await coll
    .find(
      {
        date: {
          $gte: new Date(dateFrom),
          $lte: new Date(dateTo),
        },
      },
      { projection: { _id: 1, date: 1 } }
    )
    .toArray();
  return result;
};

const getRunSensorReadings = async (runid) => {
  const db = await connectDB();
  const sensorDataColl = await getCollection(db, "SensorReading");
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

  const sensorData = await sensorDataColl
    .aggregate([
      {
        $match: { batchId: objectId },
      },
      {
        $lookup: {
          from: "Sensor",
          localField: "sensorId",
          foreignField: "id",
          as: "sensorDetails",
        },
      },
      {
        $unwind: "$sensorDetails",
      },
      {
        $group: {
          _id: "$sensorDetails.type",
          dataAxis: { $first: "$sensorDetails.dataAxis" },
          readings: { $push: "$$ROOT" },
        },
      },
    ])
    .toArray();

  return sensorData;
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
      const runDocument = { date: new Date() };
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

module.exports = {
  getAllRuns,
  getSingleRun,
  filterRunsByDate,
  getRunSensorReadings,
  createRun,
};
