#include "UnitTests.h"

#include <functional>
#include <string>

#include "constants.h"
#include "Log.h"
#include "helper_funcs.h"
#include "Config.h"
#include "TimeKeeper.h"
#include "SDHandler.h"

Assertion::operator std::string() const {
	if (!_assertionFailed)
		return "Test passed";
	return "Test <" + _testName + ":" + std::to_string(_line) + "> failed: " + _message + " | expected: " + _expected + ", actual: " + _actual;
}

bool Assertion::TestFailed() const { return _assertionFailed; }
std::string Assertion::convertBoolToString(bool val) { return val ? "true" : "false"; }


Assertion LimitedQueueTests() {
	const std::string _testName = "LimitedQueueTests";
	logInfo("Running %s", _testName.c_str());
	Assertion assertion;
	LimitedQueue<int16_t> queue(3);
	if ((assertion = Assertion("Queue empty", _testName, __LINE__, true, queue.Empty())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element addition", _testName, __LINE__, true, queue.Push(3))).TestFailed())
		return assertion;
	if ((assertion = Assertion("Queue not empty", _testName, __LINE__, false, queue.Empty())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element addition", _testName, __LINE__, true, queue.Push(312))).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element addition", _testName, __LINE__, true, queue.Push(-10))).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element addition on full", _testName, __LINE__, false, queue.Push(325))).TestFailed())
		return assertion;
	if ((assertion = Assertion("Queue full", _testName, __LINE__, false, queue.Empty())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Queue pop", _testName, __LINE__, 3, queue.Pop())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Queue pop", _testName, __LINE__, 312, queue.Pop())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Queue pop", _testName, __LINE__, -10, queue.Pop())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Queue empty", _testName, __LINE__, true, queue.Empty())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element addition", _testName, __LINE__, true, queue.Push(423))).TestFailed())
		return assertion;
	if ((assertion = Assertion("Queue pop", _testName, __LINE__, 423, queue.Pop())).TestFailed())
		return assertion;

	return Assertion();
}

Assertion LogEncodeTest() {
	const std::string _testName = "LogEncodeTest";
	logInfo("Running %s", _testName.c_str());
	Assertion assertion;
	char buffer[100];
	int32_t m32_1[] = { 31 };
	int64_t m64_3[] = { -1, 32, -24 };
	float mf_4[] = { -12.3, 100, -132.24, 0 };
	double md_2[] = { -25.35, 1534.891 };

	Log log(1016, sizeof(int32_t), 1, (char*)m32_1);
	log.EncodeToBufferSmall(buffer);
	log = Log(sizeof(int32_t), 1, buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(int32_t), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 1, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 1016, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 1; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, m32_1[i], ((int32_t*)log.measurements)[i])).TestFailed())
			return assertion;

	log = Log(1016, sizeof(int32_t), 1, (char*)m32_1);
	log.EncodeToBuffer(buffer);
	log = Log(buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(int32_t), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 1, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 1016, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 1; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, m32_1[i], ((int32_t*)log.measurements)[i])).TestFailed())
			return assertion;


	log = Log(123456, sizeof(int64_t), 3, (char*)m64_3);
	log.EncodeToBufferSmall(buffer);
	log = Log(sizeof(int64_t), 3, buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(int64_t), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 3, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 123456, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 3; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, m64_3[i], ((int64_t*)log.measurements)[i])).TestFailed())
			return assertion;

	log = Log(123456, sizeof(int64_t), 3, (char*)m64_3);
	log.EncodeToBuffer(buffer);
	log = Log(buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(int64_t), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 3, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 123456, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 3; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, m64_3[i], ((int64_t*)log.measurements)[i])).TestFailed())
			return assertion;


	log = Log(1000, sizeof(float), 4, (char*)mf_4);
	log.EncodeToBufferSmall(buffer);
	log = Log(sizeof(float), 4, buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(float), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 4, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 1000, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 4; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, mf_4[i], ((float*)log.measurements)[i])).TestFailed())
			return assertion;

	log = Log(1000, sizeof(float), 4, (char*)mf_4);
	log.EncodeToBuffer(buffer);
	log = Log(buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(float), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 4, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 1000, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 4; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, mf_4[i], ((float*)log.measurements)[i])).TestFailed())
			return assertion;


	log = Log(987654, sizeof(double), 2, (char*)md_2);
	log.EncodeToBufferSmall(buffer);
	log = Log(sizeof(double), 2, buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(double), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 2, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 987654, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 2; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, md_2[i], ((double*)log.measurements)[i])).TestFailed())
			return assertion;

	log = Log(987654, sizeof(double), 2, (char*)md_2);
	log.EncodeToBuffer(buffer);
	log = Log(buffer);
	if ((assertion = Assertion("Element size", _testName, __LINE__, sizeof(double), (long long)log.measurementSize)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Element count", _testName, __LINE__, 2, log.measurementCount)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Timestamp", _testName, __LINE__, 987654, log.timestamp)).TestFailed())
		return assertion;
	for (int i = 0; i < 2; i++)
		if ((assertion = Assertion("Element check", _testName, __LINE__, md_2[i], ((double*)log.measurements)[i])).TestFailed())
			return assertion;

	return Assertion();
}

Assertion SDBufferTests() {
	const std::string _testName = "SDBufferTests";
	logInfo("Running %s", _testName.c_str());
	Assertion assertion;
	
	SDCardBuffer sdBuffer = SDCardBuffer(100);
	char buffer[SD_CARD_SECTOR_SIZE + 110];
	for (int i = 0; i < SD_CARD_SECTOR_SIZE + 110; i++)
		buffer[i] = i % (char)0xff;
	if ((assertion = Assertion("Buffer size check", _testName, __LINE__, (short)0, (short)sdBuffer.GetBufferSize())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer status check", _testName, __LINE__, false, sdBuffer.IsBufferFull())).TestFailed())
		return assertion;
	
	if ((assertion = Assertion("Buffer append", _testName, __LINE__, true, sdBuffer.AddToBuffer(buffer, SD_CARD_SECTOR_SIZE + 98))).TestFailed())
		return assertion;
	setPrintBlock(true);
	if ((assertion = Assertion("Buffer append", _testName, __LINE__, false, sdBuffer.AddToBuffer(buffer, sizeof(buffer)))).TestFailed())
		return assertion;
	setPrintBlock(false);
	if ((assertion = Assertion("Buffer size check", _testName, __LINE__, (short)SD_CARD_SECTOR_SIZE, (short)sdBuffer.GetBufferSize())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer status check", _testName, __LINE__, true, sdBuffer.IsBufferFull())).TestFailed())
		return assertion;

	int buffPos = 0;
	for (int i = 0; i < SD_CARD_SECTOR_SIZE; i++, buffPos++)
		if ((assertion = Assertion("Buffer check", _testName, __LINE__, buffer[buffPos], sdBuffer.buffer[i])).TestFailed())
			return assertion;

	if ((assertion = Assertion("Buffer discard", _testName, __LINE__, (short)98, (short)sdBuffer.DiscardBuffer())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer status check", _testName, __LINE__, false, sdBuffer.IsBufferFull())).TestFailed())
		return assertion;

	for (int i = 0; i < 98; i++, buffPos++)
		if ((assertion = Assertion("Buffer check", _testName, __LINE__, buffer[buffPos], sdBuffer.buffer[i])).TestFailed())
			return assertion;

	if ((assertion = Assertion("Buffer discard", _testName, __LINE__, 0, sdBuffer.DiscardBuffer())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer append", _testName, __LINE__, true, sdBuffer.AddToBuffer(buffer, SD_CARD_SECTOR_SIZE / 2 + 1))).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer append", _testName, __LINE__, true, sdBuffer.AddToBuffer(buffer, SD_CARD_SECTOR_SIZE / 2 + 1))).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer status check", _testName, __LINE__, true, sdBuffer.IsBufferFull())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer append", _testName, __LINE__, true, sdBuffer.AddToBuffer(buffer, 98))).TestFailed())
		return assertion;
	for (int i = 0; i < SD_CARD_SECTOR_SIZE; i++)
		if ((assertion = Assertion("Buffer check", _testName, __LINE__, buffer[i % (SD_CARD_SECTOR_SIZE / 2 + 1)], sdBuffer.buffer[i])).TestFailed())
			return assertion;
	if ((assertion = Assertion("Buffer discard", _testName, __LINE__, 100, sdBuffer.DiscardBuffer())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer status check", _testName, __LINE__, false, sdBuffer.IsBufferFull())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer check", _testName, __LINE__, buffer[SD_CARD_SECTOR_SIZE / 2 - 1], sdBuffer.buffer[0])).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer check", _testName, __LINE__, buffer[SD_CARD_SECTOR_SIZE / 2], sdBuffer.buffer[1])).TestFailed())
		return assertion;
	for (int i = 2; i < 100; i++)
		if ((assertion = Assertion("Buffer check", _testName, __LINE__, buffer[i - 2], sdBuffer.buffer[i])).TestFailed())
			return assertion;
	if ((assertion = Assertion("Buffer discard", _testName, __LINE__, 0, sdBuffer.DiscardBuffer())).TestFailed())
		return assertion;
	if ((assertion = Assertion("Buffer status check", _testName, __LINE__, false, sdBuffer.IsBufferFull())).TestFailed())
		return assertion;

	return Assertion();
}

Assertion NullableTests() {
	const std::string _testName = "NullableTests";
	logInfo("Running %s", _testName.c_str());
	Assertion assertion;

	Nullable<int64_t> nullableObj1(false, 1265);
	char buffer[nullableObj1.GetEncodedBufferSize()];
	nullableObj1.EncodeToBuffer(buffer);
	Nullable<int64_t> nullableObj2(buffer);
	if ((assertion = Assertion("Encode/Decode check", _testName, __LINE__, nullableObj1.isNull, nullableObj2.isNull)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Encode/Decode check", _testName, __LINE__, nullableObj1.value, nullableObj2.value)).TestFailed())
		return assertion;
	if ((assertion = Assertion("Encode/Decode check", _testName, __LINE__, (int64_t)nullableObj1, (int64_t)nullableObj2)).TestFailed())
		return assertion;

	return Assertion();
}

Assertion ConfigTests() {
	const std::string _testName = "ConfigTests";
	logInfo("Running %s", _testName.c_str());
	Assertion assertion;
	RideConfigV1 rideConfigV1(
		decltype(RideConfigV1::driverID)(true, 0),
		decltype(RideConfigV1::startLocationLat)(false, 538.68),
		decltype(RideConfigV1::startLocationLon)(false, 16849.4865),
		TimeKeeper::GetCurrentTimeStamp()
	);

	char rideBuffer[rideConfigV1.GetEncodedBufferSize()];
	rideConfigV1.EncodeToBuffer(rideBuffer);
	RideConfigV1 decodedConfigV1(rideBuffer);
	if ((assertion = Assertion("RideConfig decode check", _testName, __LINE__, (std::string)rideConfigV1.driverID, (std::string)decodedConfigV1.driverID)).TestFailed())
		return assertion;
	if ((assertion = Assertion("RideConfig decode check", _testName, __LINE__, (std::string)rideConfigV1.startLocationLat, (std::string)decodedConfigV1.startLocationLat)).TestFailed())
		return assertion;
	if ((assertion = Assertion("RideConfig decode check", _testName, __LINE__, (std::string)rideConfigV1.startLocationLon, (std::string)decodedConfigV1.startLocationLon)).TestFailed())
		return assertion;
	if ((assertion = Assertion("RideConfig decode check", _testName, __LINE__, rideConfigV1.startTime, decodedConfigV1.startTime)).TestFailed())
		return assertion;

	int sensorCount = 2;
	SensorV1 sensorsV1[sensorCount];
	sensorsV1[0].ID=1; sensorsV1[0].type=testing_sensor_random; sensorsV1[0].sensorPins[0]=15; sensorsV1[0].targetedFrequency=1000; sensorsV1[0].subNodeConType=Nullable<NodeConType>(false, I2C); sensorsV1[0].subNodeConPins[0]=1; sensorsV1[0].subNodeConPins[1]=3; sensorsV1[0].measurementType=uint16, sensorsV1[0].measurementCountPerLog=3;
	sensorsV1[1].ID=2; sensorsV1[1].type=testing_sensor_random; sensorsV1[1].sensorPins[0]=110; sensorsV1[1].sensorPins[1]=0; sensorsV1[1].targetedFrequency=2050; sensorsV1[1].subNodeConType=Nullable<NodeConType>(true, I2C); sensorsV1[1].measurementType=uint32, sensorsV1[1].measurementCountPerLog=1;
	SettingsV1 settingsV1(sensorCount, sensorsV1);
	char settingsV1Buffer[settingsV1.GetEncodedBufferSize()];
	settingsV1.EncodeToBuffer(settingsV1Buffer);
	SettingsV1 decodedSettingsV1(settingsV1Buffer);
	if ((assertion = Assertion("SettingsV1 decode sensor cound check", _testName, __LINE__, settingsV1.sensorCount, decodedSettingsV1.sensorCount)).TestFailed())
		return assertion;

	for (int sensor = 0; sensor < sensorCount; sensor++) {
		if ((assertion = Assertion("SettingsV1 decode sensor ID check", _testName, __LINE__, settingsV1.sensors[sensor].ID, decodedSettingsV1.sensors[sensor].ID)).TestFailed())
			return assertion;
		if ((assertion = Assertion("SettingsV1 decode sensor type check", _testName, __LINE__, settingsV1.sensors[sensor].type, decodedSettingsV1.sensors[sensor].type)).TestFailed())
			return assertion;
		for (int pin = 0; pin < SensorV1::maxPinsInDefinition; pin++) {
			if ((assertion = Assertion("SettingsV1 decode sensor connection pin check", _testName, __LINE__, settingsV1.sensors[sensor].sensorPins[pin], decodedSettingsV1.sensors[sensor].sensorPins[pin])).TestFailed())
				return assertion;
			if ((assertion = Assertion("SettingsV1 decode sensor subnode connection pin check", _testName, __LINE__, settingsV1.sensors[sensor].subNodeConPins[pin], decodedSettingsV1.sensors[sensor].subNodeConPins[pin])).TestFailed())
				return assertion;
		}
		if ((assertion = Assertion("SettingsV1 decode sensor frequency check", _testName, __LINE__, settingsV1.sensors[sensor].targetedFrequency, decodedSettingsV1.sensors[sensor].targetedFrequency)).TestFailed())
			return assertion;
		if ((assertion = Assertion("SettingsV1 decode sensor subNodeConType check", _testName, __LINE__, (std::string)settingsV1.sensors[sensor].subNodeConType, (std::string)decodedSettingsV1.sensors[sensor].subNodeConType)).TestFailed())
			return assertion;
		if ((assertion = Assertion("SettingsV1 decode sensor frequency check", _testName, __LINE__, settingsV1.sensors[sensor].measurementType, decodedSettingsV1.sensors[sensor].measurementType)).TestFailed())
			return assertion;
		if ((assertion = Assertion("SettingsV1 decode sensor frequency check", _testName, __LINE__, settingsV1.sensors[sensor].measurementCountPerLog, decodedSettingsV1.sensors[sensor].measurementCountPerLog)).TestFailed())
			return assertion;
	}

	return Assertion();
}


bool runUnitTests() {
	logInfo("---------------------------------------");
	logInfo("Running unit tests");
	bool anyFailed = false;
	log_timestamp allTestStart = TimeKeeper::GetMsSinceBoot();
	std::function<Assertion()> tests[] = { LimitedQueueTests, LogEncodeTest, SDBufferTests, NullableTests, ConfigTests };//Add any new unit tests here

	for (auto test : tests) {
		log_timestamp testStart = TimeKeeper::GetMsSinceBoot();
		Assertion assertion = test();
		if (assertion.TestFailed()) {
			logError(((std::string)assertion).c_str());
			anyFailed = true;
		}
		logInfo("Test finished in %ums", TimeKeeper::GetMsSinceBoot() - testStart);
	}
	
	logInfo("All test run time: %ums", TimeKeeper::GetMsSinceBoot() - allTestStart);
	if (anyFailed) logWarning("One or more tests failed!");
	else logInfo("All tests passed!");
	logInfo("---------------------------------------");
	return !anyFailed;
}

