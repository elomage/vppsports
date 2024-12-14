#include "pico/stdlib.h"
#include "pico/multicore.h"
#include <tusb.h>

#include "env.h"
#include "helper_funcs.h"
#include "UnitTests.h"
#include "SDHandler.h"
#include "Config.h"

int main() {
#ifdef VPP_DEBUG
	stdio_init_all();
	sleep_ms(5000);//TODO:Put an actual wait for serial connection
	logInfo("Starting bootup");
	if (!runUnitTests())
		fatalError("Unit tests failed");
#endif
	SensorV1 sensors[1];
	sensors[0].ID=1; sensors[0].type=lcm20600_AK09918_14_I2C; sensors[0].targetedFrequency=1000; sensors[0].measurementType=uint16, sensors[0].measurementCountPerLog=3;
	SettingsVC settings(1, sensors);

	SDHandler::Initialize();
	SDHandler::SaveNewConfig(settings);
	logInfo("Saved settings: %s", ((std::string)settings).c_str());
	settings = SDHandler::GetLocalConfig();
	logInfo("Loaded settings: %s", ((std::string)settings).c_str());

	SDHandler::Stop();

#ifdef VPP_DEBUG
	sleep_ms(5000);//Wait for stdout to be flushed
#endif
	return 0;
}

