const { default: mongoose } = require("mongoose");
const { connectDB, getCollection } = require("../config/db");
const { ObjectId } = require("mongodb");

const driverSchema = new mongoose.Schema({
  name: { type: String, required: true },
  age: { type: Number, required: true },
  licenseNumber: { type: String, required: true, unique: true },
});

const Driver = mongoose.model("Driver", driverSchema);

const getAllDrivers = async () => {
  // const db = await connectDB();
  // const coll = await getCollection(db, "Driver");
  // const result = await coll.find({}).toArray();
  // return result;
  return await Driver.find({});
};

const getSingleDriver = async (driverid) => {
  // const db = await connectDB();
  // const coll = await getCollection(db, "Driver");
  // const objectId = new ObjectId(String(driverid));
  // const result = await coll.findOne({ _id: objectId });
  // return result;
  return await Driver.findById(driverid);
};

const createDriver = async (driverData) => {
  const newDriver = new Driver(driverData);
  const result = await newDriver.save();
  return result;
};

module.exports = {
  getAllDrivers,
  getSingleDriver,
  createDriver,
};
