#ifndef __LOGKEEPER_H__
#define __LOGKEEPER_H__

#include <cstddef>
#include <map>

#include "hw_config.h"
#include "ff.h"

#include "constants.h"
#include "helper_funcs.h"
#include "Config.h"

template <typename T>
struct FullLog {
	log_timestamp timestamp;
	sensor_id sensorID;
	short measurementCount;
	T *measurements;
	
	FullLog(log_timestamp timestamp, sensor_id sensorID, short measurementCount, T *measurements);
	~FullLog();
};

struct Log {
	log_timestamp timestamp;
	size_t measurementSize;
	short measurementCount;
	char *measurements = NULL;

	/**
	 * Constructs a struct with the given parameters
	 *
	 * @param timestamp Log timestamp
	 * @param measurementSize Size of each measurement
	 * @param measurementCount How many measurements are in a log
	 * @param measurements Measurement array casted to char*
	 */
	Log(log_timestamp timestamp, size_t measurementSize, short measurementCount, char *measurements);

	/**
	 * Constructs a struct by reading an encoded buffer, as produced by EncodeToBufferSmall()
	 *
	 * @param measurementSize Size of each measurement
	 * @param measurementCount How many measurements are in a log
	 * @param buffer Buffer as encoded by EncodeToBufferSmall()
	 */
	Log(size_t measurementSize, short measurementCount, char *buffer);

	/**
	 * Constructs a struct by reading an encoded buffer, as produced by EncodeToBuffer()
	 *
	 * @param buff Buffer as encoded by EncodeToBuffer()
	 */
	Log(char *buffer);

	/**
	 * Copy constructor
	 *
	 * @param log Log object from which the copy is created
	 */
	Log(const Log &log);

	/**
	 * Copy assignment operator
	 *
	 * @param log Log object from which the copy is created
	 */
	Log& operator=(const Log& log);

	/**
	 * Move constructor
	 *
	 * @param log Log object from which the data is moved
	 */
	Log(Log&& log);

	/**
	 * Move assignement operator
	 *
	 * @param log Log object from which the data is moved
	 */
	Log& operator=(Log&& log);

	/**
	 * Destructor
	 */
	~Log();

	/**
	 * Gets the size of the measurement buffer
	 *
	 * @return size of the buffer
	 */
	inline size_t GetMeasurementBufferSizeInBytes();

	/**
	 * Gets the size of a measurement buffer with the given parameters
	 *
	 * @param measurementSize Size of each measurement
	 * @param measurementCount how many measurements are in a log
	 */
	static inline size_t GetMeasurementBufferSizeInBytes(size_t measurementSize, short measurementCount);

	/**
	 * Get small encode buffer size
	 *
	 * return Size of small encode buffer
	 */
	inline size_t GetSmallEncodeBufferSize();

	/**
	 * Get small encode buffer size
	 *
	 * @param measurementSize Size of each measurement
	 * @param measurementCount How many measurements are in a log
	 * return Size of small encode buffer
	 */
	static inline size_t GetSmallEncodeBufferSize(size_t measurementSize, short measurementCount);

	/**
	 * Get encoded buffer size
	 *
	 * return Size of small encode buffer
	 */
	inline size_t GetEncodeBufferSize();

	/**
	 * Get encoded buffer size
	 *
	 * @param measurementSize Size of each measurement
	 * @param measurementCount How many measurements are in a log
	 * return Size of small encode buffer
	 */
	inline static size_t GetEncodeBufferSize(size_t measurementSize, short measurementCount);

	/**
	 * Encodes this struct to buffer
	 *
	 * @param buffer Buffer, to which the data will be encoded
	 */
	void EncodeToBuffer(char *buffer);

	/**
	 * Encodes this struct to buffer, leaving out sizes (used when the sensor is known)
	 *
	 * @param buffer Buffer, to which the data will be encoded
	 */
	void EncodeToBufferSmall(char *buffer);
};

class SDCardBuffer {
	//All positions show the next writable element
	short _bufferPosition = 0, _bufferOverrunSize = 0, _bufferOverrunPosition = 0;
	char *_bufferOverrunData = NULL;

	bool _AddToOverrunBuffer(char *data, short size);
	inline short _GetFreeSpaceInBuffer() const;
	inline short _GetFreeSpaceInOverrunBuffer() const;
public:
	char buffer[SD_CARD_SECTOR_SIZE];

	/**
	 * Constructor
	 *
	 * @param overrunBufferSize Size of the overrun buffer (temporary storage while the main buffer is written out)
	 */
	SDCardBuffer(int overrunBufferSize);

	//Copy constructor
	SDCardBuffer(const SDCardBuffer&);
	//Copy assignment operator
	SDCardBuffer& operator=(const SDCardBuffer&);
	//Move constructor
	SDCardBuffer(SDCardBuffer&&);
	//Move assignement operator
	SDCardBuffer& operator=(SDCardBuffer&&);

	~SDCardBuffer();

	/**
	 * Gets the current buffer size
	 *
	 * return Current buffer size
	 */
	short GetBufferSize() const;

	/**
	 * Appends the given data to the buffer, writing anything that doesn't fit into the overrun buffer, if possible
	 *
	 * @param data The data to be written to the buffer
	 * @param size Size of the data
	 * return True, if data is appended, false if the apend would cause an overrun
	 */
	bool AddToBuffer(char *data, short size);

	/**
	 * Checks if the buffer is full
	 *
	 * return True, if the buffer is full
	 */
	bool IsBufferFull() const;

	/**
	 * Discards the current buffer, and replaces it with overrun data, if any
	 *
	 * return Returns the buffer size after discard
	 */
	short DiscardBuffer();
};

class ImmediateLogger {
	static std::map<sensor_id, SDCardBuffer> _logMap;
	static bool _initialized;
	static std::string _runName;
	static FATFS _sdFs;

	static void _dumpBuffer();
	static std::string _getFilePath(sensor_id sensorID);

public:
	static void Init(abs_timestamp absStartTime, Sensor *sensors, short sensorCount);
	static void InitSensors();
	static void StoreLog(sensor_id, Log);
	static void Stop();
};

#endif

