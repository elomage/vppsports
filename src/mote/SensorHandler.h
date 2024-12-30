#ifndef __SENSORHANDLER_H__
#define __SENSORHANDLER_H__

#include <functional>

#include "constants.h"
#include "Config.h"
#include "Log.h"

/**
 * Initializes the sensors, calibrates them, then starts the run
 *
 * @param settings The sensor configuration
 * @param getRunState The function to query, in order to find out the current run state
 * @param rideConfig The run config
 */
void runSensorLogger(const SettingsVC &settings, std::function<RunState()> getRunState, RideConfigVC rideConfig);

/**
 * An abstract sensor handler class
 * All sensors types have their own sensor handler to simplify recording.
 *
 * Handlers that must use a shared object to communicate with the required sensors, should keep these objects
 * within the scope of the file (static) std::map<used pin hash, communication object>.
 * E.g. a sensor package contains an accelerometer, gyroscope and a magnetometer, and the communication is handled by a
 * single object, with the appropriate methods (get_acc(), ,,,). As such, the handling logic shall be structured as follows:
 * 	1) All 3 sensors get a handler class that inherits from this(SensorHandler) class, following the naming convention
 * 		detailed in constants.h
 * 	2) The communication object is created and initialized by the first sensor handler to be initialized
 * 	3) The shared communication object is stored in a std::map object, using the relevant pin/address bytes
 * 		from SensorVC.sensorPins, to create a hash key
 * 	4) The communication object is deinitialized and removed from the std::map by the first handler to be destructed
 */
class SensorHandler {
protected:
	const sensor_id _sensorID;
	const int _msBetweenMeasurements;
	log_timestamp _lastMeasurementTime = 0;
	bool _firstMeasurementTaken = false;

public:
	SensorHandler(const SensorVC &sensor) : _msBetweenMeasurements(1000 / sensor.targetedFrequency), _sensorID(sensor.ID) {}

	inline sensor_id GetSensorID() const { return _sensorID; }

	/**
	 * Calibrates the sensor, if required
	 *
	 * @return True, if calibration was successful
	 */
	virtual bool Calibrate() = 0;

	/**
	 * Returns the datatype used to store measurements
	 *
	 * return The measurement data type
	 */
	virtual MeasurementDataType GetMeasurementDataType() const = 0;

	/**
	 * Returns the sensor type, that this handler is for
	 *
	 * return The sensor type
	 */
	virtual SensorType GetSensorType() const = 0;

	/**
	 * Takes the current measurement data, and writes it to the buffer, if it is time to take the next measurements
	 *
	 * @param log The created log
	 * return Returns true, if enough time has passed since the last measurement. Otherwise, false is returned and nothing is written to the buffer.
	 */
	virtual bool GetSensorData(Log &log) = 0;

	/**
	 * Returns an error string, if any errors were encountered
	 *
	 * return If the string is empty, no errors were encountered
	 */
	virtual std::string GetSensorStatus() const = 0;
};

class EmptySensor final : public SensorHandler {
public:
	EmptySensor(const SensorVC &sensor) : SensorHandler(sensor) {}

	virtual bool Calibrate() override final { return true; }
	virtual MeasurementDataType GetMeasurementDataType() const override final { return MeasurementDataType::int8; }
	virtual SensorType GetSensorType() const override final { return SensorType::testing_sensor_random; }
	virtual bool GetSensorData(Log &log) override final { return false; }
	virtual std::string GetSensorStatus() const override final { return ""; }
};

class RandomSensor final : public SensorHandler {
	const enum MeasurementDataType _measurementDataType;
	const int _measurementCountPerLog;

public:
	RandomSensor(const SensorVC &sensor) : SensorHandler(sensor), _measurementDataType(sensor.measurementType), _measurementCountPerLog(sensor.measurementCountPerLog) {}

	virtual bool Calibrate() override final { return true; }
	virtual MeasurementDataType GetMeasurementDataType() const override final;
	virtual SensorType GetSensorType() const override final;
	virtual bool GetSensorData(Log &log) override final;
	virtual std::string GetSensorStatus() const override final { return ""; }
};

#endif

