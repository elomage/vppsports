#ifndef __SDGandler_h__
#define __SDGandler_h__

#include "f_util.h"
#include "ff.h"

#include "constants.h"
#include "Config.h"
#include "LogKeeper.h"

class SDHandler {
	static bool _initialized;
	static std::string _currentRunName;
	static std::map<sensor_id, SDCardBuffer> _rideLogMap;

	inline static std::string _getSensorLogFilePath(sensor_id sensorID);

	/**
	 * Dumps all of the unwritten logs from the current ride
	 */
	static void _DumpSensorLogBuffer();

	/**
	 * Appends the given sensor log buffer to the apropriate log file
	 *
	 * @param filename The sensor filename as generated by _getSensorLogFilePath
	 * @param logBuffer The apropriate buffer object
	 * @param writeAll If true, all of the stored data will be written out, otherwise, the write will stop once the active buffer is not full
	 */
	static void _WriteSensorLogBufferToCard(const std::string filename, SDCardBuffer &logBuffer, const bool writeAll);

public:
	/**
	 * Initializes the handler. Must be called before any operations.
	 */
	static void Initialize(/*FATFS *_sdFs*/);

	/**
	 * Dumps any unwritten data, unmounts the SD card and deinitializes this class
	 */
	static void Stop();

	/**
	 * Initializes the run file structure
	 *
	 * @param runStartTime Run start time
	 * @param relevantSensors Sensors that exist on this mote
	 * @param rideConfig Ride configuration
	 */
	static void InitRun(abs_timestamp runStartTime, Sensor *relevantSensors, short sensorCount, RideConfig &rideConfig);

	/**
	 * Stores the given log from a sensor to a buffer, then writes out the buffer, if it is full
	 *
	 * @param sensorID ID of the sensor
	 * @param log sensor log to be stored
	 */
	static void StoreLog(const sensor_id sensorID, const Log &log);

	/**
	 * Dumps all unwritten run data and deinitializes the current run
	 */
	static void StopRun();

	inline static bool IsConfigLocallyStored() {
		if(!_initialized) fatalError("[SDHandler::IsConfigLocallyStored]: SDHandler is not initialized");
		return f_stat(CONFIG_FILENAME, NULL) == FR_OK;
	}

	/**
	 * Gets localy stored settings
	 *
	 * return Localy stored setting object
	 */
	static SettingsVC GetLocalConfig();

	/**
	 * Saves new settings localy
	 *
	 * @param settings The new SettingsVC object
	 */
	static void SaveNewConfig(const SettingsVC &settings);
};

#endif

