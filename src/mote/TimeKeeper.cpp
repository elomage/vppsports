#include "TimeKeeper.h"

#include "pico/stdlib.h"

#include "helper_funcs.h"

bool TimeKeeper::_isSetUp = false;
log_timestamp TimeKeeper::_startTimeInMs = 0;

log_timestamp TimeKeeper::GetMsSinceBoot() { return to_ms_since_boot(get_absolute_time()); }

void TimeKeeper::Setup() {
	_isSetUp = true;
}

void TimeKeeper::Reset() {
	if (!_isSetUp) 
		fatalError("TimeKeeper isn't set up, call Setup()");

	_startTimeInMs = GetMsSinceBoot();
}

log_timestamp TimeKeeper::GetRecordingTimeStamp() {
	return GetMsSinceBoot() - _startTimeInMs;
}

