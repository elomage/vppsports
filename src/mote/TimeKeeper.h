#ifndef __TIMEKEEPER_H__
#define __TIMEKEEPER_H__

#include "constants.h"

class TimeKeeper {
	static bool _isSetUp;
	static log_timestamp _startTimeInMs;
	
public:
	static void Setup();
	static void Reset();
	static log_timestamp GetRecordingTimeStamp();

	static inline log_timestamp GetMsSinceBoot();
};

#endif

