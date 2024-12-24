#include "pico/stdlib.h"
#include "pico/multicore.h"

#include "env.h"
#include "helper_funcs.h"
#include "UnitTests.h"
#include "SDHandler.h"
#include "Config.h"
#include "SensorHandler.h"
#include "TimeKeeper.h"

int main() {
#ifdef VPP_DEBUG
	stdio_init_all();
	sleep_ms(5000);//TODO:Put in an actual wait for serial connection
	logInfo("Starting bootup");
	if (!runUnitTests())
		fatalError("Unit tests failed");
#endif
	TimeKeeper::Setup();

	SensorV1 sensors[2];
	sensors[0].ID=1; sensors[0].type=SensorType::testing_sensor_random; sensors[0].targetedFrequency=1000; sensors[0].measurementType=uint16, sensors[0].measurementCountPerLog=3;
	sensors[1].ID=2; sensors[1].type=SensorType::testing_sensor_random; sensors[1].targetedFrequency=50; sensors[1].measurementType=uint16, sensors[0].measurementCountPerLog=5;
	SettingsVC settings(2, sensors);

	SDHandler::Initialize();
	SDHandler::SaveNewConfig(settings);
	logInfo("Saved settings: %s", ((std::string)settings).c_str());
	settings = SDHandler::GetLocalConfig();
	logInfo("Loaded settings: %s", ((std::string)settings).c_str());

	RideConfigVC rideConfig = GenerateRideConfig();
	runSensorLogger(settings, []() -> RunState { return TimeKeeper::GetMsSinceBoot() < 5 * 60 * 1000 ? RunState::started : RunState::runFinished; }, rideConfig);

	SDHandler::Stop();

#ifdef VPP_DEBUG
	sleep_ms(5000);//Wait for stdout to be flushed
#endif
	return 0;
}

