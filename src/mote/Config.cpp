#include "Config.h"

#include <cstring>

Sensor::Sensor(char *buff) { std::memcpy(&ID, buff, sizeof(ID)); }
size_t Sensor::GetEncodedBufferSize() { return sizeof(ID); }
void Sensor::EncodeToBuffer(char *buff) { std::memcpy(buff, &ID, sizeof(ID)); }

SensorV1::SensorV1(char *buff) : Sensor(buff) {
	int pos = Sensor::GetEncodedBufferSize();
	std::memcpy(&type, buff + pos, sizeof(type)); pos += sizeof(type);
	std::memcpy(&pins, buff + pos, sizeof(pins)); pos += sizeof(pins);
	std::memcpy(&targetedFrequency, buff + pos, sizeof(targetedFrequency)); pos += sizeof(targetedFrequency);
	std::memcpy(&connectionType, buff + pos, sizeof(connectionType)); pos += sizeof(connectionType);
	std::memcpy(&measurementType, buff + pos, sizeof(measurementType)); pos += sizeof(measurementType);
	std::memcpy(&measurementCountPerLog, buff + pos, sizeof(measurementCountPerLog)); pos += sizeof(measurementCountPerLog);
}

size_t SensorV1::GetEncodedBufferSize() {
	return Sensor::GetEncodedBufferSize()
		+ sizeof(type)
		+ sizeof(pins)
		+ sizeof(targetedFrequency)
		+ sizeof(connectionType)
		+ sizeof(measurementType)
		+ sizeof(measurementCountPerLog);
}

void SensorV1::EncodeToBuffer(char *buff) {
	Sensor::EncodeToBuffer(buff);
	short pos = Sensor::GetEncodedBufferSize();
	std::memcpy(buff + pos, &type, sizeof(type)); pos += sizeof(type);
	std::memcpy(buff + pos, pins, sizeof(pins)); pos += sizeof(pins);
	std::memcpy(buff + pos, &targetedFrequency, sizeof(targetedFrequency)); pos += sizeof(targetedFrequency);
	std::memcpy(buff + pos, &connectionType, sizeof(connectionType)); pos += sizeof(connectionType);
	std::memcpy(buff + pos, &measurementType, sizeof(measurementType)); pos += sizeof(measurementType);
	std::memcpy(buff + pos, &measurementCountPerLog, sizeof(measurementCountPerLog));
}

ver_id SensorV1::GetVersionID() { return 1; }

