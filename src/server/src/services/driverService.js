const { connectDB, getCollection} = require('../config/db');
const { ObjectId } = require('mongodb');  

const getAllDrivers = async () => {
    const db = await connectDB();
    const coll = await getCollection(db, 'Driver');
    const result = await coll.find({}).toArray();
    return result;
};

const getSingleDriver = async(driverid) => {
  const db = await connectDB();
  const coll = await getCollection(db, 'Driver');
  const objectId = new ObjectId(String(driverid));
  const result = await coll.findOne({ _id: objectId });
  return result;
};

module.exports = {
  getAllDrivers,
  getSingleDriver,
};