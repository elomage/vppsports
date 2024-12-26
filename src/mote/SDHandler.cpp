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

void SDHandler::InitRun(std::list<SensorVC> relevantSensors, RideConfigVC &rideConfig) {
	if (!_initialized) fatalError("[SDHandler::InitRun]: SDHandler isn't initialized");

	_currentRunName = "Run_" + std::to_string(rideConfig.startTime);
	logInfo("[SDHandler::InitRun]: Clearing any previous run with the same name");
	if (!_RecursivelyDeleteIfExists(_currentRunName.c_str()))
		fatalError("[SDHandler::InitRun]: Failed to clear identical run from SD card");
	logInfo("[SDHandler::InitRun]: Creating a directory for this run");
	if (f_mkdir(_currentRunName.c_str()) != FR_OK)
		fatalError("[SDHandler::InitRun]: Failed to initialize this run's directory");

	logInfo("[SDHandler::InitRun]: Writing run info");
	FIL file;
	if (f_open(&file, (_currentRunName + "/RunInfo.bin").c_str(), FA_CREATE_ALWAYS | FA_WRITE) != FR_OK)
		fatalError("[SDHandler::InitRun]: Failed to create/open the new run info file");
	ver_id versionID = rideConfig.GetVersionID();
	if (f_write(&file, &versionID, sizeof(versionID), NULL) != FR_OK)
		fatalError("[SDHandler::InitRun]: Failed to write ride config version ID");
	char rideConfigBuffer[rideConfig.GetEncodedBufferSize()];
	rideConfig.EncodeToBuffer(rideConfigBuffer);
	if (f_write(&file, rideConfigBuffer, rideConfig.GetEncodedBufferSize(), NULL) != FR_OK)
		fatalError("[SDHandler::InitRun]: Failed to write runConfig");
	if (f_close(&file) != FR_OK)
		fatalError("[SDHandler::InitRun]: Failed to close the file");

	for (SensorVC sensor : relevantSensors) {
		logInfo("[SDHandler::InitRun]: Initializing the new sensor(%d) log file", sensor.ID);
		_rideLogMap.emplace(sensor.ID, SD_CARD_SECTOR_SIZE);
		if (f_open(&file, _GetSensorLogFilePath(sensor.ID).c_str(), FA_CREATE_ALWAYS | FA_WRITE) != FR_OK)
			fatalError("[SDHandler::InitRun]: Failed to create/open the new sensor log file");
		size_t bufferSize = sensor.GetEncodedBufferSize();
		char buffer[bufferSize];
		sensor.EncodeToBuffer(buffer);
		if (f_write(&file, buffer, sizeof(bufferSize), NULL) != FR_OK)
			fatalError("[SDHandler::InitRun]: Failed to write to the new sensor log file");
		if (f_close(&file) != FR_OK)
			fatalError("[SDHandler::InitRun]: Failed to close the file");
	}
	logInfo("[SDHandler::InitRun]: Run %s initialized", _currentRunName.c_str());
}

bool SDHandler::_RecursivelyDeleteIfExists(const TCHAR *path) {
	logInfo("[SDHandler::_RecursivelyDeleteIfExists]: Delete called on %s", path);
	FILINFO fileInfo;
	if (f_stat(path, &fileInfo) != FR_OK)
		return true;

	if (fileInfo.fattrib == AM_DIR) {
		DIR dirObj;
		if (f_opendir(&dirObj, path) != FR_OK)
			return false;
		for (FRESULT result = f_findfirst(&dirObj, &fileInfo, path, "*"); result == FR_OK && fileInfo.fname[0]; result = f_findnext(&dirObj, &fileInfo)) {
			TCHAR currFilePath[FF_LFN_BUF + 1];
			snprintf(currFilePath, FF_LFN_BUF + 1, "%s/%s", path, fileInfo.fname);
			if (!_RecursivelyDeleteIfExists(currFilePath))
				return false;
		}
		if (f_closedir(&dirObj) != FR_OK)
			return false;
		return f_unlink(path) == FR_OK;
	} else return f_unlink(path) == FR_OK;
	return false;
}

void SDHandler::_DumpSensorLogBuffer() {
	if (_currentRunName == "") fatalError("[SDHandler::_DumpSensorLogBuffer]: No current active run");

	for (decltype(_rideLogMap)::iterator it = _rideLogMap.begin(); it != _rideLogMap.end(); it++)
		_WriteSensorLogBufferToCard(_GetSensorLogFilePath(it->first), it->second, true);
}

void SDHandler::_WriteSensorLogBufferToCard(const std::string filename, SDCardBuffer &logBuffer, const bool writeAll) {
	FIL file;
	if (f_open(&file, filename.c_str(), FA_OPEN_APPEND | FA_WRITE) != FR_OK)
		fatalError("[SDHandler::_WriteSensorLogBufferToCard]: Failed to open the log file");
	for (; writeAll ? (logBuffer.GetBufferSize() > 0) : logBuffer.IsBufferFull(); logBuffer.DiscardBuffer()) {
		UINT bytesWritten, bytesToWrite = logBuffer.GetBufferSize();
		if (f_write(&file, logBuffer.buffer, logBuffer.GetBufferSize(), &bytesWritten) != FR_OK)
			fatalError("[SDHandler::_WriteSensorLogBufferToCard]: Failed to write");
		if (bytesWritten != bytesToWrite)
			fatalError("[SDHandler::_WriteSensorLogBufferToCard]: Wrote invalid number of bytes");
	}
	if (f_close(&file) != FR_OK)
		fatalError("[SDHandler::_WriteSensorLogBufferToCard]: Failed to close the file");
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
		_WriteSensorLogBufferToCard(_GetSensorLogFilePath(sensorID), logBuffer, false);
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


SDCardBuffer::SDCardBuffer(int overrunBufferSize) {
	this->_bufferOverrunData = new char[this->_bufferOverrunSize = overrunBufferSize];
}

SDCardBuffer::SDCardBuffer(const SDCardBuffer &other) {
	this->_bufferPosition = other._bufferPosition;
	this->_bufferOverrunSize = other._bufferOverrunSize;
	this->_bufferOverrunPosition = other._bufferOverrunPosition;
	this->_bufferOverrunData = new char[this->_bufferOverrunSize];
	std::memcpy(this->_bufferOverrunData, other._bufferOverrunData, this->_bufferOverrunSize);
	std::memcpy(this->buffer, other.buffer, SD_CARD_SECTOR_SIZE);
}

SDCardBuffer& SDCardBuffer::operator=(const SDCardBuffer &other) {
	if (this != &other) {
		delete[] this->_bufferOverrunData;
		this->_bufferPosition = other._bufferPosition;
		this->_bufferOverrunSize = other._bufferOverrunSize;
		this->_bufferOverrunPosition = other._bufferOverrunPosition;
		this->_bufferOverrunData = new char[this->_bufferOverrunSize];
		std::memcpy(this->_bufferOverrunData, other._bufferOverrunData, this->_bufferOverrunSize);
		std::memcpy(this->buffer, other.buffer, SD_CARD_SECTOR_SIZE);
	}
	return *this;
}

SDCardBuffer::SDCardBuffer(SDCardBuffer &&other) {
	this->_bufferPosition = other._bufferPosition;
	this->_bufferOverrunSize = other._bufferOverrunSize;
	this->_bufferOverrunPosition = other._bufferOverrunPosition;
	this->_bufferOverrunData = other._bufferOverrunData;
	other._bufferOverrunData = NULL;
	std::memcpy(this->buffer, other.buffer, SD_CARD_SECTOR_SIZE);
}

SDCardBuffer& SDCardBuffer::operator=(SDCardBuffer &&other) {
	if (this != &other) {
		this->_bufferPosition = other._bufferPosition;
		this->_bufferOverrunSize = other._bufferOverrunSize;
		this->_bufferOverrunPosition = other._bufferOverrunPosition;
		this->_bufferOverrunData = other._bufferOverrunData;
		other._bufferOverrunData = NULL;
		std::memcpy(this->buffer, other.buffer, SD_CARD_SECTOR_SIZE);
	}
	return *this;
}

SDCardBuffer::~SDCardBuffer() {
	delete[] _bufferOverrunData;
}

bool SDCardBuffer::_AddToOverrunBuffer(char *data, short size) {
	if (_bufferOverrunPosition + size > _bufferOverrunSize) {
		logWarning("[SDCardBuffer::_AddToOverrunBuffer]: Not appending data to overrun buffer, since all of it can't be stored");
		return false;
	}
	std::memcpy(_bufferOverrunData + _bufferOverrunPosition, data, size);
	_bufferOverrunPosition += size;
	return true;
}

inline short SDCardBuffer::_GetFreeSpaceInBuffer() const { return SD_CARD_SECTOR_SIZE - _bufferPosition; }
inline short SDCardBuffer::_GetFreeSpaceInOverrunBuffer() const { return _bufferOverrunSize - _bufferOverrunPosition; }
short SDCardBuffer::GetBufferSize() const { return _bufferPosition; }

bool SDCardBuffer::AddToBuffer(char *data, short size) {
	if (_GetFreeSpaceInBuffer() + _GetFreeSpaceInOverrunBuffer() < size) {
		logWarning("[SDCardBuffer::AddToBuffer]: Not appending data to buffer, since all of it can't be stored");
		return false;
	}
	short dataWrittenInRegularBuffer = _bufferPosition + size > SD_CARD_SECTOR_SIZE ? SD_CARD_SECTOR_SIZE - _bufferPosition : size;
	std::memcpy(buffer + _bufferPosition, data, dataWrittenInRegularBuffer);
	_bufferPosition += dataWrittenInRegularBuffer;
	return _AddToOverrunBuffer(data + dataWrittenInRegularBuffer, size - dataWrittenInRegularBuffer);
}

bool SDCardBuffer::IsBufferFull() const { return _bufferPosition >= SD_CARD_SECTOR_SIZE; }

short SDCardBuffer::DiscardBuffer() {
	_bufferPosition = _bufferOverrunPosition > SD_CARD_SECTOR_SIZE ? SD_CARD_SECTOR_SIZE : _bufferOverrunPosition;
	std::memcpy(buffer, _bufferOverrunData, _bufferPosition);
	std::memcpy(_bufferOverrunData, _bufferOverrunData + _bufferPosition, _bufferOverrunPosition -= _bufferPosition);
	return GetBufferSize();
}

