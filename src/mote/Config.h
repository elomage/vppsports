#ifndef __CONFIG_H__
#define __CONFIG_H__

#include "constants.h"
#include "helper_funcs.h"

struct Sensor {
	sensor_id ID;

	Sensor(){}
	Sensor(char *buff);

	virtual size_t GetEncodedBufferSize();
	virtual void EncodeToBuffer(char *buff);
	virtual ver_id GetVersionID() = 0;
};

struct SensorV1 : public Sensor {
	enum SensorType type;
	char pins[10];
	uint16_t targetedFrequency;
	enum NodeConType connectionType;
	enum MeasurementDataType measurementType;
	uint8_t measurementCountPerLog;

	SensorV1() : Sensor(){}
	SensorV1(char *buff);

	size_t GetEncodedBufferSize() override;
	void EncodeToBuffer(char *buff) override;
	ver_id GetVersionID() override;
};

struct RideConfigV1 {
	const ver_id configVersionID;
	Nullable<uint16_t> driverID;
	Nullable<double> StartLocationLat;
	Nullable<double> StartLocationLon;
	abs_timestamp StartTime;
};

#endif

