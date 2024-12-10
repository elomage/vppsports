#include "Config.h"

#include <cstring>

#include "TimeKeeper.h"

RideConfigVC GenerateRideConfig() {
	return RideConfigVC(
		Nullable<uint16_t>(true, 0),
		Nullable<double>(true, 0),
		Nullable<double>(true, 0),
		TimeKeeper::GetCurrentTimeStamp()
	);
}

SensorV1::SensorV1(char *buff) {
	std::memcpy(&ID, buff, sizeof(ID)); buff += sizeof(ID);
	std::memcpy(&type, buff, sizeof(type)); buff += sizeof(type);
	std::memcpy(sensorPins, buff, sizeof(sensorPins)); buff += sizeof(sensorPins);//This might cause problems, if compiler doesn't pack arrays
	std::memcpy(&targetedFrequency, buff, sizeof(targetedFrequency)); buff += sizeof(targetedFrequency);
	subNodeConType = Nullable<NodeConType>(buff); buff += subNodeConType.GetEncodedBufferSize();
	std::memcpy(subNodeConPins, buff, sizeof(subNodeConPins)); buff += sizeof(subNodeConPins);
	std::memcpy(&measurementType, buff, sizeof(measurementType)); buff += sizeof(measurementType);
	std::memcpy(&measurementCountPerLog, buff, sizeof(measurementCountPerLog));
}

size_t SensorV1::GetEncodedBufferSize() const {
	return GetEncodedBufferSizeV1();
}

size_t SensorV1::GetEncodedBufferSizeV1() {
	return sizeof(ID)
		+ sizeof(type)
		+ sizeof(sensorPins)
		+ sizeof(targetedFrequency)
		+ decltype(subNodeConType)::GetEncodedBufferSize()
		+ sizeof(subNodeConPins)
		+ sizeof(measurementType)
		+ sizeof(measurementCountPerLog);
}

void SensorV1::EncodeToBuffer(char *buff) const {
	std::memcpy(buff, &ID, sizeof(ID)); buff += sizeof(ID);
	std::memcpy(buff, &type, sizeof(type)); buff += sizeof(type);
	std::memcpy(buff, sensorPins, sizeof(sensorPins)); buff += sizeof(sensorPins);
	std::memcpy(buff, &targetedFrequency, sizeof(targetedFrequency)); buff += sizeof(targetedFrequency);
	subNodeConType.EncodeToBuffer(buff); buff += subNodeConType.GetEncodedBufferSize();
	std::memcpy(buff, subNodeConPins, sizeof(subNodeConPins)); buff += sizeof(subNodeConPins);
	std::memcpy(buff, &measurementType, sizeof(measurementType)); buff += sizeof(measurementType);
	std::memcpy(buff, &measurementCountPerLog, sizeof(measurementCountPerLog));
}

ver_id SensorV1::GetVersionID() const { return 1; }


RideConfigV1::RideConfigV1(char *buffer) {
	driverID = decltype(driverID)(buffer); buffer += driverID.GetEncodedBufferSize();
	startLocationLat = decltype(startLocationLat)(buffer); buffer += startLocationLat.GetEncodedBufferSize();
	startLocationLon = decltype(startLocationLon)(buffer); buffer += startLocationLon.GetEncodedBufferSize();
	std::memcpy(&startTime, buffer, sizeof(startTime));
}

ver_id RideConfigV1::GetVersionID() const { return 1; }

void RideConfigV1::EncodeToBuffer(char *buffer) const {
	driverID.EncodeToBuffer(buffer); buffer += driverID.GetEncodedBufferSize();
	startLocationLat.EncodeToBuffer(buffer); buffer += startLocationLat.GetEncodedBufferSize();
	startLocationLon.EncodeToBuffer(buffer); buffer += startLocationLon.GetEncodedBufferSize();
	std::memcpy(buffer, &startTime, sizeof(startTime));
}

size_t RideConfigV1::GetEncodedBufferSize() const {
	return driverID.GetEncodedBufferSize()
		+ startLocationLat.GetEncodedBufferSize()
		+ startLocationLon.GetEncodedBufferSize()
		+ sizeof(startTime);
}


SettingsV1::SettingsV1(char *buffer) {
	std::memcpy(&sensorCount, buffer, sizeof(sensorCount)); buffer += sizeof(sensorCount);
	sensors = new SensorV1[sensorCount];
	for (int sensor = 0; sensor < sensorCount; sensor++, buffer += SensorV1::GetEncodedBufferSizeV1())
		sensors[sensor] = SensorV1(buffer);
}

SettingsV1::SettingsV1(uint8_t sensorCount, SensorV1 *sensors) {
	this->sensorCount = sensorCount;
	this->sensors = new SensorV1[this->sensorCount];
	for (int sensor = 0; sensor < this->sensorCount; sensor++)
		this->sensors[sensor] = sensors[sensor];
}

SettingsV1::~SettingsV1() {
	delete[] sensors;
}

SettingsV1::SettingsV1(const SettingsV1 &other) {
	this->sensorCount = other.sensorCount;
	this->sensors = new SensorV1[this->sensorCount];
	for (int sensor = 0; sensor < this->sensorCount; sensor++)
		this->sensors[sensor] = other.sensors[sensor];
}

SettingsV1& SettingsV1::operator=(const SettingsV1 &other) {
	if (this != &other) {
		delete[] this->sensors;
		this->sensorCount = other.sensorCount;
		this->sensors = new SensorV1[this->sensorCount];
		for (int sensor = 0; sensor < this->sensorCount; sensor++)
			this->sensors[sensor] = other.sensors[sensor];
	}
	return *this;
}

SettingsV1::SettingsV1(SettingsV1 &&other) {
	this->sensorCount = other.sensorCount;
	this->sensors = other.sensors;
	other.sensors = NULL;
}

SettingsV1& SettingsV1::operator=(SettingsV1 &&other) {
	if (this != &other) {
		this->sensorCount = other.sensorCount;
		this->sensors = other.sensors;
		other.sensors = NULL;
	}
	return *this;
}

void SettingsV1::EncodeToBuffer(char *buffer) const {
	std::memcpy(buffer, &sensorCount, sizeof(sensorCount)); buffer += sizeof(sensorCount);
	for (int sensor = 0; sensor < sensorCount; buffer += sensors[sensor++].GetEncodedBufferSize())
		sensors[sensor].EncodeToBuffer(buffer);
}

size_t SettingsV1::GetEncodedBufferSize() const {
	size_t size = sizeof(sensorCount);
	for (int sensor = 0; sensor < sensorCount; sensor++)
		size += sensors[sensor].GetEncodedBufferSize();
	return size;
}

ver_id SettingsV1::GetVersionID() const { return 1; }

