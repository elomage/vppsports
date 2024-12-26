#ifndef __TIMEKEEPER_H__
#define __TIMEKEEPER_H__

#include "pico/stdlib.h"

#include "constants.h"

class TimeKeeper {
	static bool _isSetUp;
	static log_timestamp _startTimeInMs;
	
public:
	/**
	 * Performs any needed setup
	 */
	static void Setup();

	/**
	 * Resets the run time to 0
	 */
	static void Reset();

	/**
	 * Gets the current run time
	 *
	 * @return Ms since the start of the run
	 */
	static log_timestamp GetRecordingTimeStamp();

	/**
	 * Gets the ms since boot
	 *
	 * @return Ms since boot
	 */
	static inline log_timestamp GetMsSinceBoot() { return to_ms_since_boot(get_absolute_time()); }

	/**
	 * Gets the current timestamp
	 *
	 * @return Seconds since 1970-01-01 00:00:00 UTC
	 */
	static abs_timestamp GetCurrentTimeStamp();
};

#endif

