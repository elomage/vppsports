#include "LogKeeper.h"

#include <cstring>

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


bool ImmediateLogger::_initialized = false;

void ImmediateLogger::Init() {
	//TODO
	_initialized = true;
}

void ImmediateLogger::DumpBuffer() {
	for (std::map<sensor_id, char[SD_CARD_SECTOR_SIZE]>::iterator it = _logMap.begin(); it != _logMap.end(); it++) {
		//TODO
	}
}

void ImmediateLogger::StoreLog(sensor_id id, Log log) {
	//TODO
	//TODO
}


volatile bool LogKeeper::_stopCalled = false;

void LogKeeper::_dumpAll() {
	//TODO
}

bool LogKeeper::AddSensorLog(sensor_id id, Log log) {
	if (_logMap.find(id) == _logMap.end())
		_logMap.emplace(id, SENSOR_BUFFER_IN_MEMORY);
	return _logMap.at(id).Push(log);
}

void LogKeeper::RunLogDumper() {
	while (!_stopCalled) {
		_dumpAll();
	}
	_dumpAll();
}

void LogKeeper::Stop() { _stopCalled = true; }

