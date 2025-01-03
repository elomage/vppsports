#include "pico/stdlib.h"

#include <stdio.h>

#include "ff.h"

#include "helper_funcs.h"
#include "env.h"

static bool printBlocked = false;

void fatalError(std::string errorMessage) {
	while (true) {
		logError(std::string("FATAL: " + errorMessage).c_str());
		sleep_ms(5000);
	}
}

void setPrintBlock(bool block) { printBlocked = block; }

#define _LOGGER_LOG va_list args; va_start(args, format); vprintf(format, args); va_end(args); printf("\n"); fflush(stdout);
#if defined(VPP_DEBUG) && defined(VPP_LOG_ERR)
void logError(const char *format, ...) {
	if (printBlocked) return;
	printf("[ERROR]: ");
	_LOGGER_LOG;
}
#else
void logError(const char *format, ...) {}
#endif

#if defined(VPP_DEBUG) && defined(VPP_LOG_WARN)
void logWarning(const char *format, ...) {
	if (printBlocked) return;
	printf("[WARN]:  ");
	_LOGGER_LOG;
}
#else
void logWarning(const char *format, ...) {}
#endif

#if defined(VPP_DEBUG) && defined(VPP_LOG_INFO)
void logInfo(const char *format, ...) {
	if (printBlocked) return;
	printf("[INFO]:  ");
	_LOGGER_LOG;
}
#else
void logInfo(const char *format, ...) {}
#endif


size_t getMeasurementDataSize(const enum MeasurementDataType measurementDataType) {
	switch (measurementDataType) {
		case MeasurementDataType::int8:
		case MeasurementDataType::uint8:
		case MeasurementDataType::bool8:
			return 1;
		case MeasurementDataType::int16:
		case MeasurementDataType::uint16:
		case MeasurementDataType::float16:
			return 2;
		case MeasurementDataType::int32:
		case MeasurementDataType::uint32:
		case MeasurementDataType::float32:
			return 4;
		case MeasurementDataType::int64:
		case MeasurementDataType::uint64:
		case MeasurementDataType::float64:
			return 8;
		default: fatalError("Used data type not defined"); return 0;
	}
}

