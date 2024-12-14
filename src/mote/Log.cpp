#include "Log.h"

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

