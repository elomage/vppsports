const driverService = require("../services/driverService");

const getAllDrivers = async (req, res) => {
  try {
    const drivers = await driverService.getAllDrivers();
    return drivers;
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const getSingleDriver = async (driverid) => {
  try {
    const driver = await driverService.getSingleDriver(driverid);
    return driver;
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

const createDriver = async (req, res) => {
  try {
    const driver = await driverService.createDriver(req.body);
    res.status(201).json({ id: driver._id });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
};

module.exports = {
  getAllDrivers,
  getSingleDriver,
  createDriver,
};
