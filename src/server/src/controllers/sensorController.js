const sensorService = require('../services/sensorService');

const getSensor = async (sensorId) => {
  try {
    const sensor = await sensorService.getSensor(sensorId);
    return sensor;
  } catch (error) {
    throw new Error(error.message);
  }
};

/**
 * Calculate the orientation data from the sensor data
 * @param {Object} sensorData - The sensor data object. Array of readings
 * @returns {Object} - The sensor data object with orientation data
 */
const calculateOrientationData = async (sensorData) => {
    try {
        sensorData.orientationData = [];
    
        var pitch = 0;
        var roll = 0;
        var yaw = 0;
        
        sensorData.data.forEach(element => {
            pitch += toRadians((element.gyro[0]+1)/100);
            roll += toRadians((element.gyro[1]+1)/100);
            yaw += toRadians((element.gyro[2]+1)/100);
          
            response.orientationData.push([element.time, roll, yaw, pitch]);
        });

        return sensorData;

    } catch (err) {
        throw new Error(err.message);
    }

};

module.exports = {
  getSensor,
};
