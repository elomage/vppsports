#include "LogKeeper.h"

#include <cstring>

#include "env.h"

template <typename T>
FullLog<T>::FullLog(log_timestamp timestamp, sensor_id sensorID, short measurementCount, T *measurements) {
	this->timestamp = timestamp;
	this->sensorID = sensorID;
	this->measurementCount = measurementCount;
	this->measurements = new char[measurementCount];
	for (short i = 0; i < measurementCount; i++)
		this.measurements[i] = measurements[i];
}

template <typename T>
FullLog<T>::~FullLog() {
	delete measurements;
}

Log::Log(log_timestamp timestamp, size_t measurementSize, short measurementCount, char *measurements) {
	this->timestamp = timestamp;
	this->measurementCount = measurementCount;
	this->measurementSize = measurementSize;
	this->measurements = new char[GetMeasurementBufferSizeInBytes()];
	std::memcpy(this->measurements, measurements, GetMeasurementBufferSizeInBytes());
}

Log::Log(size_t measurementSize, short measurementCount, char *buffer) {
	this->measurementSize = measurementSize;
	this->measurementCount = measurementCount;
	this->measurements = new char[GetMeasurementBufferSizeInBytes()];
	std::memcpy(&this->timestamp, buffer, sizeof(this->timestamp));
	std::memcpy(this->measurements, buffer + sizeof(this->timestamp), GetMeasurementBufferSizeInBytes());
}

Log::Log(char *buffer) {
	int pos = 0;
	std::memcpy(&this->timestamp, buffer + pos, sizeof(this->timestamp)); pos += sizeof(this->timestamp);
	std::memcpy(&this->measurementSize, buffer + pos, sizeof(this->measurementSize)); pos += sizeof(this->measurementSize);
	std::memcpy(&this->measurementCount, buffer + pos, sizeof(this->measurementCount)); pos += sizeof(this->measurementCount);
	this->measurements = new char[GetMeasurementBufferSizeInBytes()];
	std::memcpy(this->measurements, buffer + pos, GetMeasurementBufferSizeInBytes());
}

Log::Log(const Log &log) {
	this->timestamp = log.timestamp;
	this->measurementSize = log.measurementSize;
	this->measurementCount = log.measurementCount;
	this->measurements = new char[GetMeasurementBufferSizeInBytes()];
	std::memcpy(this->measurements, log.measurements, GetMeasurementBufferSizeInBytes());
}

Log& Log::operator=(const Log& log) {
	if (this != &log) {
		delete[] measurements;
		this->timestamp = log.timestamp;
		this->measurementSize = log.measurementSize;
		this->measurementCount = log.measurementCount;
		this->measurements = new char[GetMeasurementBufferSizeInBytes()];
		std::memcpy(this->measurements, log.measurements, GetMeasurementBufferSizeInBytes());
	}
	return *this;
}

Log::Log(Log&& log) {
	this->timestamp = log.timestamp;
	measurementSize = log.measurementSize;
	measurementCount = log.measurementCount;
	measurements = log.measurements;
	log.measurements = NULL;
}

Log& Log::operator=(Log&& log) {
	if (this != &log) {
		this->timestamp = log.timestamp;
		this->measurementSize = log.measurementSize;
		this->measurementCount = log.measurementCount;
		this->measurements = log.measurements;
		log.measurements = NULL;
	}
	return *this;
}

Log::~Log() { delete[] measurements; }

size_t Log::GetMeasurementBufferSizeInBytes() { return GetMeasurementBufferSizeInBytes(measurementSize, measurementCount); }
size_t Log::GetMeasurementBufferSizeInBytes(size_t measurementSize, short measurementCount) { return measurementSize * measurementCount; }
size_t Log::GetSmallEncodeBufferSize() { return GetSmallEncodeBufferSize(measurementSize, measurementCount); }
size_t Log::GetSmallEncodeBufferSize(size_t measurementSize, short measurementCount) { return sizeof(log_timestamp) + GetMeasurementBufferSizeInBytes(measurementSize, measurementCount); }
size_t Log::GetEncodeBufferSize() { return GetEncodeBufferSize(measurementSize, measurementCount); }
size_t Log::GetEncodeBufferSize(size_t measurementSize, short measurementCount) { return sizeof(log_timestamp) + sizeof(size_t) + sizeof(short) + GetMeasurementBufferSizeInBytes(measurementSize, measurementCount); }

void Log::EncodeToBuffer(char *buffer) {
	int pos = 0;
	std::memcpy(buffer + pos, &timestamp, sizeof(timestamp)); pos += sizeof(timestamp);
	std::memcpy(buffer + pos, &measurementSize, sizeof(measurementSize)); pos += sizeof(measurementSize);
	std::memcpy(buffer + pos, &measurementCount, sizeof(measurementCount)); pos += sizeof(measurementCount);
	std::memcpy(buffer + pos, measurements, GetMeasurementBufferSizeInBytes());
}

void Log::EncodeToBufferSmall(char *buffer) {
	int pos = 0;
	std::memcpy(buffer + pos, &timestamp, sizeof(timestamp)); pos += sizeof(timestamp);
	std::memcpy(buffer + pos, measurements, GetMeasurementBufferSizeInBytes());
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


static spi_t spi = {
    .hw_inst = SPI_SET,
    .miso_gpio = SPI_MISO_GPIO,
    .mosi_gpio = SPI_MOSI_GPIO,
    .sck_gpio = SPI_SCK_GPIO,
    .baud_rate = SPI_BAUD_RATE
};

static sd_spi_if_t spi_if = {
    .spi = &spi,
    .ss_gpio = SD_SPI_CS_GP
};

static sd_card_t sd_card = {
    .type = SD_IF_SPI,
    .spi_if_p = &spi_if
};


bool ImmediateLogger::_initialized = false;

void ImmediateLogger::Init(abs_timestamp absStartTime, Sensor *sensors, short sensorCount) {
	_runName = "Run_" + std::to_string(absStartTime);
	logInfo("[ImmediateLogger::Init]: Mounting SD card's filesystem");
	if (f_mount(&_sdFs, "", 1) != FR_OK)
		fatalError("[ImmediateLogger::Init]: Failed to mount the SD card's filesystem");
	logInfo("[ImmediateLogger::Init]: Clearing any previous run with the same name");
	if (!recursivelyDeleteIfExists(_runName.c_str()))
		fatalError("[ImmediateLogger::Init]: Failed to clear identical run from SD card");
	logInfo("[ImmediateLogger::Init]: Creating a directory for this run");
	if (f_mkdir(_runName.c_str()) != FR_OK)
		fatalError("[ImmediateLogger::Init]: Failed to initialize this run's directory");
	logInfo("[ImmediateLogger::Init]: SD card logger initialized");

	for (short sensor = 0; sensor < sensorCount; sensor++) {
		logInfo("[ImmediateLogger::Init]: Initializing the new sensor(%d) log file", sensors[sensor].ID);
		_logMap.emplace(sensors[sensor].ID, SD_CARD_SECTOR_SIZE);
		FIL file;
		if (f_open(&file, _getFilePath(sensors[sensor].ID).c_str(), FA_CREATE_ALWAYS | FA_WRITE) != FR_OK)
			fatalError("[ImmediateLogger::Init]: Failed to create/open the new sensor log file");
		size_t bufferSize = sensors[sensor].GetEncodedBufferSize();
		char buffer[bufferSize];
		sensors[sensor].EncodeToBuffer(buffer);
		if (f_write(&file, buffer, sizeof(bufferSize), NULL) != FR_OK)
			fatalError("[ImmediateLogger::Init]: Failed to write to the new sensor log file");
		f_close(&file);
	}
	logInfo("[ImmediateLogger::Init]: All sensor logfile initialized");
	_initialized = true;
}

void ImmediateLogger::_dumpBuffer() {
	if (!_initialized) fatalError("[ImmediateLogger::_dumpBuffer]: ImmediateLogger has not been initialized");
	for (std::map<sensor_id, SDCardBuffer>::iterator it = _logMap.begin(); it != _logMap.end(); it++) {
		for (;it->second.IsBufferFull(); it->second.DiscardBuffer()) {
			FIL file;
			if (f_open(&file, _getFilePath(it->first).c_str(), FA_OPEN_APPEND | FA_WRITE) != FR_OK)
				fatalError("[ImmediateLogger::_dumpBuffer]: Failed to open the file");
			for (; it->second.GetBufferSize() != 0; it->second.DiscardBuffer()) {
				if (f_write(&file, it->second.buffer, it->second.GetBufferSize(), NULL) != FR_OK)
					fatalError("[ImmediateLogger::_dumpBuffer]: Failed to write");
			}
			f_close(&file);
		}
	}
}

std::string ImmediateLogger::_getFilePath(sensor_id sensorID) {
	return _runName + "/Log_" + std::to_string(sensorID) + ".bin";
}

void ImmediateLogger::StoreLog(sensor_id id, Log log) {
	if (!_initialized) fatalError("[ImmediateLogger::StoreLog]: ImmediateLogger has not been initialized");
	if (_logMap.find(id) == _logMap.end()) return;
	char buffer[log.GetSmallEncodeBufferSize()];
	log.EncodeToBufferSmall(buffer);
	_logMap.at(id).AddToBuffer(buffer, sizeof(buffer));
}

void ImmediateLogger::Stop() {
	logInfo("[ImmediateLogger::Stop]: Stopping ImmediateLogger");
	_dumpBuffer();
	_initialized = false;
	f_unmount("");
	_logMap.clear();
	_runName = "";
	logInfo("[ImmediateLogger::Stop]: ImmediateLogger deinitialized");
}

