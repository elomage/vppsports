#ifndef __CONSTANTS_H__
#define __CONSTANTS_H__

#include <cstdint>

#define APP_VERSION "0.1"

typedef uint8_t ver_id;
typedef uint64_t abs_timestamp;
typedef uint32_t log_timestamp;
typedef uint16_t sensor_id;

#define SENSOR_BUFFER_IN_MEMORY 100
#define SD_CARD_SECTOR_SIZE 512

enum MeasurementDataType {
	int8 = 0,
	int16 = 1,
	int32 = 2,
	int64 = 3,
	uint8 = 4,
	uint16 = 5,
	uint32 = 6,
	uint64 = 7,
	float16 = 8,
	float32 = 9,
	float64 = 10,
	bool8 = 11
};

//Name_ID-from-sensor-sheet_connection-method
enum SensorType {
	lcm20600_AK09918_14_I2C = 0
};

enum NodeConType {
	I2C = 0,
	SPI = 1
};

#endif

