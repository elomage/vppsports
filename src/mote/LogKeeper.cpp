#include "LogKeeper.h"

#include <cstring>

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

void Log::EncodeToBuffer(char *buffer) const {
	int pos = 0;
	std::memcpy(buffer + pos, &timestamp, sizeof(timestamp)); pos += sizeof(timestamp);
	std::memcpy(buffer + pos, &measurementSize, sizeof(measurementSize)); pos += sizeof(measurementSize);
	std::memcpy(buffer + pos, &measurementCount, sizeof(measurementCount)); pos += sizeof(measurementCount);
	std::memcpy(buffer + pos, measurements, GetMeasurementBufferSizeInBytes());
}

void Log::EncodeToBufferSmall(char *buffer) const {
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

