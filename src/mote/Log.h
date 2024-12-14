#ifndef __LOGKEEPER_H__
#define __LOGKEEPER_H__

#include "constants.h"
#include "helper_funcs.h"
#include "Config.h"

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
	inline size_t GetMeasurementBufferSizeInBytes() const { return GetMeasurementBufferSizeInBytes(measurementSize, measurementCount); }

	/**
	 * Gets the size of a measurement buffer with the given parameters
	 *
	 * @param measurementSize Size of each measurement
	 * @param measurementCount how many measurements are in a log
	 */
	static inline size_t GetMeasurementBufferSizeInBytes(size_t measurementSize, short measurementCount) { return measurementSize * measurementCount; }

	/**
	 * Get small encode buffer size
	 *
	 * return Size of small encode buffer
	 */
	inline size_t GetSmallEncodeBufferSize() const { return GetSmallEncodeBufferSize(measurementSize, measurementCount); }

	/**
	 * Get small encode buffer size
	 *
	 * @param measurementSize Size of each measurement
	 * @param measurementCount How many measurements are in a log
	 * return Size of small encode buffer
	 */
	static inline size_t GetSmallEncodeBufferSize(size_t measurementSize, short measurementCount) { return sizeof(log_timestamp) + GetMeasurementBufferSizeInBytes(measurementSize, measurementCount); }

	/**
	 * Get encoded buffer size
	 *
	 * return Size of small encode buffer
	 */
	inline size_t GetEncodeBufferSize() const { return GetEncodeBufferSize(measurementSize, measurementCount); }

	/**
	 * Get encoded buffer size
	 *
	 * @param measurementSize Size of each measurement
	 * @param measurementCount How many measurements are in a log
	 * return Size of small encode buffer
	 */
	inline static size_t GetEncodeBufferSize(size_t measurementSize, short measurementCount) { return sizeof(log_timestamp) + sizeof(size_t) + sizeof(short) + GetMeasurementBufferSizeInBytes(measurementSize, measurementCount); }

	/**
	 * Encodes this struct to buffer
	 *
	 * @param buffer Buffer, to which the data will be encoded
	 */
	void EncodeToBuffer(char *buffer) const;

	/**
	 * Encodes this struct to buffer, leaving out sizes (used when the sensor is known)
	 *
	 * @param buffer Buffer, to which the data will be encoded
	 */
	void EncodeToBufferSmall(char *buffer) const;
};

#endif

