const sensorService = require("../services/sensorService");

const getSensor = async (sensorId) => {
  try {
    const sensor = await sensorService.getSensor(sensorId);
    return sensor;
  } catch (error) {
    throw new Error(error.message);
  }
};

module.exports = {
  getSensor,
};
