#include "SDHandler.h"
#include "env.h"
#include "helper_funcs.h"

bool SDHandler::_initialized = false;
FATFS SDHandler::_sdFs;
std::string SDHandler::_currentRunName = "";
std::map<sensor_id, SDCardBuffer> SDHandler::_rideLogMap = {};

void SDHandler::Initialize() {
	logInfo("[SDHandler::Initialize]: Mounting SD card's filesystem");
	if (f_mount(&_sdFs, "", 1) != FR_OK)
		fatalError("[SDHandler::Initialize]: Failed to mount the SD card's filesystem");
	_initialized = true;
	logInfo("[SDHandler::Initialize]: SD card initialized");
}

void SDHandler::Stop() {
	StopRun();
	f_unmount("");
	_initialized = false;
	logInfo("[SDHandler::Stop]: Unmounted and deinitialized the filesystem");
}

void SDHandler::InitRun(abs_timestamp runStartTime, Sensor *relevantSensors, short sensorCount, RideConfig &rideConfig) {
	if (!_initialized) fatalError("[SDHandler::InitRun]: SDHandler isn't initialized");

	_currentRunName = "Run_" + std::to_string(runStartTime);
	logInfo("[SDHandler::InitRun]: Clearing any previous run with the same name");
	if (!recursivelyDeleteIfExists(_currentRunName.c_str()))
		fatalError("[SDHandler::InitRun]: Failed to clear identical run from SD card");
	logInfo("[SDHandler::InitRun]: Creating a directory for this run");
	if (f_mkdir(_currentRunName.c_str()) != FR_OK)
		fatalError("[SDHandler::InitRun]: Failed to initialize this run's directory");

	for (short sensor = 0; sensor < sensorCount; sensor++) {
		logInfo("[SDHandler::InitRun]: Initializing the new sensor(%d) log file", relevantSensors[sensor].ID);
		_rideLogMap.emplace(relevantSensors[sensor].ID, SD_CARD_SECTOR_SIZE);
		FIL file;
		if (f_open(&file, _getSensorLogFilePath(relevantSensors[sensor].ID).c_str(), FA_CREATE_ALWAYS | FA_WRITE) != FR_OK)
			fatalError("[SDHandler::InitRun]: Failed to create/open the new sensor log file");
		size_t bufferSize = relevantSensors[sensor].GetEncodedBufferSize();
		char buffer[bufferSize];
		relevantSensors[sensor].EncodeToBuffer(buffer);
		if (f_write(&file, buffer, sizeof(bufferSize), NULL) != FR_OK)
			fatalError("[SDHandler::InitRun]: Failed to write to the new sensor log file");
		if (f_close(&file) != FR_OK)
			fatalError("[SDHandler::InitRun]: Failed to close the file");
	}
	logInfo("[SDHandler::InitRun]: Run %s initialized", _currentRunName.c_str());
}

void SDHandler::_DumpSensorLogBuffer() {
	if (_currentRunName == "") fatalError("[SDHandler::_DumpSensorLogBuffer]: No current active run");

	for (decltype(_rideLogMap)::iterator it = _rideLogMap.begin(); it != _rideLogMap.end(); it++)
		_WriteSensorLogBufferToCard(_getSensorLogFilePath(it->first), it->second, true);
}

void SDHandler::_WriteSensorLogBufferToCard(const std::string filename, SDCardBuffer &logBuffer, const bool writeAll) {
	FIL file;
	if (f_open(&file, filename.c_str(), FA_OPEN_APPEND | FA_WRITE) != FR_OK)
		fatalError("[SDHandler::_WriteSensorLogBufferToCard]: Failed to open the log file");
	for (; writeAll ? (logBuffer.GetBufferSize() > 0) : logBuffer.IsBufferFull(); logBuffer.DiscardBuffer()) {
		if (f_write(&file, logBuffer.buffer, logBuffer.GetBufferSize(), NULL) != FR_OK)
			fatalError("[SDHandler::_WriteSensorLogBufferToCard]: Failed to write");
	}
	if (f_close(&file) != FR_OK)
		fatalError("[SDHandler::_WriteSensorLogBufferToCard");
}

void SDHandler::StoreLog(const sensor_id sensorID, const Log &log) {
	if (_currentRunName == "") fatalError("[SDHandler::StoreLog]: No currently active runs");

	decltype(_rideLogMap)::iterator rlmIt = _rideLogMap.find(sensorID);
	if (rlmIt == _rideLogMap.end()) fatalError("[SDHandler::StoreLog]: Invalid sensor ID");
	SDCardBuffer &logBuffer = rlmIt->second;

	char buffer[log.GetSmallEncodeBufferSize()];
	log.EncodeToBufferSmall(buffer);
	logBuffer.AddToBuffer(buffer, sizeof(buffer));
	
	if (logBuffer.IsBufferFull())
		_WriteSensorLogBufferToCard(_getSensorLogFilePath(sensorID), logBuffer, false);
}

void SDHandler::StopRun() {
	if (_currentRunName == "") return;

	logInfo("[SDHandler::StopRun]: Stopping run");
	_DumpSensorLogBuffer();
	_currentRunName = "";
	_rideLogMap.clear();
	logInfo("[SDHandler::StopRun]: Run stopped");
}

SettingsVC SDHandler::GetLocalConfig() {
	if (!_initialized) fatalError("[SDHandler::GetLocalConfig]: SDHandler is not initialized");

	FILINFO fileinfo;
	if (f_stat(CONFIG_FILENAME, &fileinfo) != FR_OK)
		fatalError("[SDHandler::GetLocalConfig]: No local config exists");

	FIL file;
	if (f_open(&file, CONFIG_FILENAME, FA_READ) != FR_OK)
		fatalError("[SDHandler::GetLocalConfig]: Failed to open file");

	UINT bytesToRead = sizeof(ver_id), bytesRead;
	ver_id versionID;
	if (f_read(&file, &versionID, bytesToRead, &bytesRead) != FR_OK)
		fatalError("[SDHandler::GetLocalConfig]: Failed to read");
	if (bytesToRead != bytesRead) {
		logError("[SDHandler::GetLocalConfig]: Requested bytes: %d | bytes read: %d", bytesToRead, bytesRead);
		fatalError("[SDHandler::GetLocalConfig]: Read invalid number of bytes");
	}

	logInfo("[SDHandler::GetLocalConfig]: Config version: %d", versionID);

	SettingsVC settings;

	if (versionID == 1) {
		char buffer[bytesToRead = (fileinfo.fsize - sizeof(ver_id))];
		if (f_read(&file, buffer, bytesToRead, &bytesRead) != FR_OK)
			fatalError("[SDHandler::GetLocalConfig]: Failed to read");
		if (bytesToRead != bytesRead) {
			logError("[SDHandler::GetLocalConfig]: Requested bytes: %d | bytes read: %d", bytesToRead, bytesRead);
			fatalError("[SDHandler::GetLocalConfig]: Read invalid number of bytes");
		}
		settings = SettingsVC(buffer);
	} else logError("[SDHandler::GetLocalConfig]: No valid decoder");
	
	if (f_close(&file) != FR_OK)
		fatalError("[SDHandler::GetLocalConfig]: Failed to close the file");
	return settings;
}

void SDHandler::SaveNewConfig(const Settings &settings) {
	if (!_initialized) fatalError("[SDHandler::SaveNewConfig]: SDHandler is not initialized");

	FIL file;
	if (f_open(&file, CONFIG_FILENAME, FA_CREATE_ALWAYS | FA_WRITE) != FR_OK)
		fatalError("[SDHandler::SaveNewConfig]: Failed to open file for writing");

	UINT bytesToWrite, bytesWritten;
	ver_id versionID = settings.GetVersionID();
	if (f_write(&file, &versionID, bytesToWrite = sizeof(ver_id), &bytesWritten) != FR_OK)
		fatalError("[SDHandler::SaveNewConfig]: Failed to write");
	if (bytesToWrite != bytesWritten) {
		logError("[SDHandler::SaveNewConfig]: Requested bytes: %d | bytes written: %d", bytesToWrite, bytesWritten);
		fatalError("[SDHandler::SaveNewConfig]: Wrote invalid number of bytes");
	}
	char buffer[settings.GetEncodedBufferSize()];
	settings.EncodeToBuffer(buffer);
	if (f_write(&file, buffer, bytesToWrite = sizeof(buffer), &bytesWritten) != FR_OK)
		fatalError("[SDHandler::SaveNewConfig]: Failed to write");
	if (bytesToWrite != bytesWritten) {
		logError("[SDHandler::SaveNewConfig]: Requested bytes: %d | bytes written: %d", bytesToWrite, bytesWritten);
		fatalError("[SDHandler::SaveNewConfig]: Wrote invalid number of bytes");
	}
	if (f_close(&file) != FR_OK)
		fatalError("[SDHandler::SaveNewConfig]: Failed to close the file");
	logInfo("[SDHandler::SaveNewConfig]: Saved the new config to the SD card");
}

