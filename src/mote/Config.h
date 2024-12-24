#ifndef __CONFIG_H__
#define __CONFIG_H__

#include "constants.h"
#include "helper_funcs.h"

//Note: Any new version of these data structures should include an upgrade method to allow loading an older config file

struct Sensor {
	sensor_id ID;

	Sensor(){}
	Sensor(char *buff);
	virtual operator std::string() const = 0;

	virtual size_t GetEncodedBufferSize() const = 0;
	virtual void EncodeToBuffer(char *buff) const = 0;
	virtual ver_id GetVersionID() const = 0;
};

struct SensorV1 : public Sensor {
	static const int maxPinsInDefinition = 20;//The buffer is this large to accommodate addresses, if they are needed

	enum SensorType type;
	uint8_t sensorPins[maxPinsInDefinition];
	float targetedFrequency;
	Nullable<NodeConType> subNodeConType;//null, if the sensor is on this node
	uint8_t subNodeConPins[maxPinsInDefinition];//Ignore, if subNodeConType is null
	enum MeasurementDataType measurementType;
	uint8_t measurementCountPerLog;

	SensorV1() : Sensor(){}
	SensorV1(char *buff);
	virtual operator std::string() const override;

	virtual size_t GetEncodedBufferSize() const override final;
	static size_t GetEncodedBufferSizeV1();
	virtual void EncodeToBuffer(char *buff) const override final;
	virtual ver_id GetVersionID() const override final;
};

//Current sensor version
struct SensorVC : public SensorV1 { using SensorV1::SensorV1; SensorVC(const SensorV1 &sensor) : SensorV1(sensor) {} };

struct RideConfig {
	virtual operator std::string() const = 0;

	virtual ver_id GetVersionID() const = 0;
	virtual void EncodeToBuffer(char *buffer) const = 0;
	virtual size_t GetEncodedBufferSize() const = 0;
};

struct RideConfigV1 : public RideConfig {
	Nullable<uint16_t> driverID;
	Nullable<double> startLocationLat;
	Nullable<double> startLocationLon;
	abs_timestamp startTime;

	RideConfigV1(Nullable<uint16_t> driverID, Nullable<double> startLocationLat, Nullable<double> startLocationLon, abs_timestamp startTime)
		: driverID(driverID), startLocationLat(startLocationLat), startLocationLon(startLocationLon), startTime(startTime) {}
	RideConfigV1(char *buffer);
	virtual operator std::string() const override;

	virtual ver_id GetVersionID() const override final;
	virtual void EncodeToBuffer(char *buffer) const override final;
	virtual size_t GetEncodedBufferSize() const override final;
};

//Current ride config version
struct RideConfigVC : public RideConfigV1 { using RideConfigV1::RideConfigV1; RideConfigVC(const RideConfigV1 &rideConfig) : RideConfigV1(rideConfig) {} };

struct Settings {
	virtual operator std::string() const = 0;

	virtual ver_id GetVersionID() const = 0;
	virtual void EncodeToBuffer(char *buffer) const = 0;
	virtual size_t GetEncodedBufferSize() const = 0;
};

struct SettingsV1 : public Settings {
	uint8_t sensorCount;
	SensorV1 *sensors;

	SettingsV1() : SettingsV1(0, NULL) {}
	SettingsV1(char *buffer);
	SettingsV1(uint8_t sensorCount, SensorV1 *sensors);
	~SettingsV1();
	SettingsV1(const SettingsV1 &other);
	SettingsV1& operator=(const SettingsV1 &other);
	SettingsV1(SettingsV1 &&other);
	SettingsV1& operator=(SettingsV1 &&other);
	virtual operator std::string() const override;

	virtual ver_id GetVersionID() const override final;
	virtual void EncodeToBuffer(char *buffer) const override final;
	virtual size_t GetEncodedBufferSize() const override final;
};

//Current setting version
struct SettingsVC : public SettingsV1 { using SettingsV1::SettingsV1; SettingsVC(const SettingsV1 &settings) : SettingsV1(settings) {} };


RideConfigVC GenerateRideConfig();

#endif

