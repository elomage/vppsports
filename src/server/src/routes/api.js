const express = require('express');
const router = express.Router();
const driverController = require('../controllers/driverController');
const { parseApiDataObject } = require('../controllers/sensorDataController');
const runController = require('../controllers/runController');

router.get('/drivers', async (req, res) => {
    try {
        const drivers = await driverController.getAllDrivers();
        res.json(drivers);
    } catch (error) {
        res.status(500).json({ message: 'Error fetching drivers', error: error.message });
    }
});

//Test endpoint for receiving data from the API
router.post('/data/V1', (req, res) => {

    const data = Buffer.from(req.body);

    console.log(data);
    console.log(data.length);
    console.log(parseApiDataObject(data));
    
    res.status(200).json({ message: 'Data received' });
});

router.get('/runs', async(req, res) => {
    try {
        const runs = await runController.getAllRuns();
        res.json(runs);
    } catch (error) {
        res.status(500).json({ message: 'Error fetching runs', error: error.message });
    }
});

module.exports = router;