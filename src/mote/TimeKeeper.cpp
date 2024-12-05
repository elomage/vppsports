#include "TimeKeeper.h"

#include "helper_funcs.h"

bool TimeKeeper::_isSetUp = false;
log_timestamp TimeKeeper::_startTimeInMs = 0;

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

abs_timestamp TimeKeeper::GetCurrentTimeStamp() {
	//TODO: Implement
	return 1704060000/*2024*/ + GetMsSinceBoot() / 1000;
}

