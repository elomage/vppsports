#ifndef __CONFIG_H__
#define __CONFIG_H__

#include "constants.h"
#include "helper_funcs.h"

struct Sensor {
	sensor_id ID;

	Sensor(){}
	Sensor(char *buff);

	virtual size_t GetEncodedBufferSize() = 0;
	virtual void EncodeToBuffer(char *buff) = 0;
	virtual ver_id GetVersionID() = 0;
};

struct SensorV1 : public Sensor {
	static const int maxPinsInDefinition = 20;//The buffer is this large to accommodate addresses, if they are needed

	enum SensorType type;
	uint8_t sensorPins[maxPinsInDefinition];
	uint16_t targetedFrequency;
	Nullable<NodeConType> subNodeConType;//null, if the sensor is on this node
	uint8_t subNodeConPins[maxPinsInDefinition];//Ignore, if subNodeConType is null
	enum MeasurementDataType measurementType;
	uint8_t measurementCountPerLog;

	SensorV1() : Sensor(){}
	SensorV1(char *buff);

	size_t GetEncodedBufferSize() override;
	static size_t GetEncodedBufferSizeV1();
	void EncodeToBuffer(char *buff) override;
	ver_id GetVersionID() override;
};

//Current sensor version
struct SensorVC : public SensorV1 { using SensorV1::SensorV1; };

struct RideConfig {
	virtual ver_id GetVersionID() = 0;
	virtual void EncodeToBuffer(char *buffer) = 0;
	virtual size_t GetEncodedBufferSize() = 0;
};

struct RideConfigV1 : public RideConfig {
	Nullable<uint16_t> driverID;
	Nullable<double> startLocationLat;
	Nullable<double> startLocationLon;
	abs_timestamp startTime;

	RideConfigV1(Nullable<uint16_t> driverID, Nullable<double> startLocationLat, Nullable<double> startLocationLon, abs_timestamp startTime)
		: driverID(driverID), startLocationLat(startLocationLat), startLocationLon(startLocationLon), startTime(startTime) {}
	RideConfigV1(char *buffer);

	ver_id GetVersionID() override;
	void EncodeToBuffer(char *buffer) override;
	size_t GetEncodedBufferSize() override;
};

//Current ride config version
struct RideConfigVC : public RideConfigV1 { using RideConfigV1::RideConfigV1; };

struct Settings {
	virtual ver_id GetVersionID() = 0;
	virtual void EncodeToBuffer(char *buffer) = 0;
	virtual size_t GetEncodedBufferSize() = 0;
};

struct SettingsV1 : public Settings {
	uint8_t sensorCount;
	SensorV1 *sensors;

	SettingsV1(char *buffer);
	SettingsV1(uint8_t sensorCount, SensorV1 *sensors);
	~SettingsV1();
	SettingsV1(const SettingsV1 &other);
	SettingsV1& operator=(const SettingsV1 &other);
	SettingsV1(SettingsV1 &&other);
	SettingsV1& operator=(SettingsV1 &&other);

	ver_id GetVersionID() override;
	void EncodeToBuffer(char *buffer) override;
	size_t GetEncodedBufferSize() override;
};

//Current setting version
struct SettingsVC : public SettingsV1 { using SettingsV1::SettingsV1; };

#endif

