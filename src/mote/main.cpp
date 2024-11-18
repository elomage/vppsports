#include "pico/stdlib.h"
#include "pico/multicore.h"
#include <tusb.h>

#include "env.h"
#include "helper_funcs.h"
#include "UnitTests.h"

int main() {
#ifdef VPP_DEBUG
	stdio_init_all();
	sleep_ms(5000);//TODO:Put an actual wait for serial connection
	logInfo("Starting bootup");
	if (!runUnitTests())
		fatalError("Unit tests failed");
#endif

}

