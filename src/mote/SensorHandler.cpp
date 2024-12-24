#include "SensorHandler.h"

#include <list>

#include "pico/rand.h"

#include "helper_funcs.h"
#include "TimeKeeper.h"
#include "SDHandler.h"

static SensorHandler* createHandler(const SensorVC &sensor) {
	switch(sensor.type) {
		case SensorType::testing_sensor_random: return new RandomSensor(sensor);
		default: fatalError("[SensorHandler::createHandler]: no apropriate handler found");
	}
	return new RandomSensor(sensor);
}

void runSensorLogger(const SettingsVC &settings, std::function<RunState()> getRunState, RideConfigVC rideConfig) {
	logInfo("[runSensorLogger]: Running sensor logger");
	std::list<SensorHandler*> sensorHandlers;
	std::list<SensorVC> usedSensors;
	for (short sensor; sensor < settings.sensorCount; sensor++) {
		if (!settings.sensors[sensor].subNodeConType.isNull) continue;
		sensorHandlers.push_back(createHandler(settings.sensors[sensor]));
		usedSensors.push_back(settings.sensors[sensor]);
	}

	logInfo("[runSensorLogger]: Starting run");
	rideConfig.startTime = TimeKeeper::GetCurrentTimeStamp();
	SDHandler::InitRun(usedSensors, rideConfig);
	while (getRunState() == RunState::awaitingStart);
	TimeKeeper::Reset();

	while (getRunState() == RunState::started) {
		for (SensorHandler* sensorHandler : sensorHandlers) {
			Log log;
			if (!sensorHandler->GetSensorData(log))
				continue;
			SDHandler::StoreLog(sensorHandler->GetSensorID(), log);
		}
	}
	SDHandler::StopRun();

	for (SensorHandler *sensorHandler : sensorHandlers)
		delete sensorHandler;
	sensorHandlers.clear();
	logInfo("[runSensorLogger]: Finished");
}

MeasurementDataType RandomSensor::GetMeasurementDataType() const { return _measurementDataType; }
SensorType RandomSensor::GetSensorType() const { return SensorType::testing_sensor_random; }

bool RandomSensor::GetSensorData(Log &log) {
	if (_lastMeasurementTime + _msBetweenMeasurements > TimeKeeper::GetRecordingTimeStamp() && _firstMeasurementTaken)
		return false;

	size_t measurementSize = getMeasurementDataSize(_measurementDataType);
	char buffer[measurementSize * _measurementCountPerLog];
	for (long long measurement = 0, buffPosition = 0, rand = get_rand_64(); measurement < _measurementCountPerLog; measurement++, buffPosition += measurementSize, rand = get_rand_64())
		std::memcpy(buffer + buffPosition, &rand, measurementSize);

	log = Log(_lastMeasurementTime = TimeKeeper::GetRecordingTimeStamp(), measurementSize, _measurementCountPerLog, buffer);
	return _firstMeasurementTaken = true;
}

