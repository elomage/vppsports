#ifndef __TIMEKEEPER_H__
#define __TIMEKEEPER_H__

#include "pico/stdlib.h"

#include "constants.h"

class TimeKeeper {
	static bool _isSetUp;
	static log_timestamp _startTimeInMs;
	
public:
	static void Setup();
	static void Reset();
	static log_timestamp GetRecordingTimeStamp();
	static inline log_timestamp GetMsSinceBoot() { return to_ms_since_boot(get_absolute_time()); }
	static abs_timestamp GetCurrentTimeStamp();
};

#endif

