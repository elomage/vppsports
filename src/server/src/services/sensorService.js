const { connectDB, getCollection } = require('../config/db');
const { ObjectId } = require('mongodb');

const getSensor = async (sensorId) => {
    const db = await connectDB();
    const sensorColl = await getCollection(db, 'Sensor');
    const sensor = await sensorColl.findOne({ id: parseInt(sensorId) });
    return sensor;
}

module.exports = {
    getSensor,
};