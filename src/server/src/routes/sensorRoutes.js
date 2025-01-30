const express = require('express');
const router = express.Router();

const sensorController = require('../controllers/sensorController');

router.get('/:sensorid', async (req, res) => {
    try {
        const sensorid = req.params.sensorid;
        const selectedSensor = await sensorController.getSensor(sensorid);
        res.json(selectedSensor);

    } catch (error) {
        res.status(500).json({ message: 'Error fetching run', error: error.message });
    }
});
module.exports = router;