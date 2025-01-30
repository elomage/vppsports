class Measurement {
    constructor() {
        this.TimeFromStartInus = 0;
        this.Measurements = [];
    }
}

class MeasurementList {
    constructor() {
        this.SensorID = 0;
        this.MeasurementCount = 0;
        this.MeasurementsPerLog = 0;
        this.MeasurementTypes = [];
        this.Measurements = [];
    }
}

class ApiDataObject {
    constructor() {
        this.MacAddress = '';
        this.SensorCount = 0;
        this.SensorData = [];
    }
}

const measurementTypes = {
    0: (buffer, offset) => buffer.readInt8(offset),
    1: (buffer, offset) => buffer.readInt16LE(offset),
    2: (buffer, offset) => buffer.readInt32LE(offset),
    3: (buffer, offset) => buffer.readBigInt64LE(offset), // int64
    4: (buffer, offset) => buffer.readUInt8(offset),
    5: (buffer, offset) => buffer.readUInt16LE(offset),
    6: (buffer, offset) => buffer.readUInt32LE(offset),
    7: (buffer, offset) => buffer.readBigUInt64LE(offset), // uint64
    8: (buffer, offset) => buffer.readFloatLE(offset), // float16
    9: (buffer, offset) => buffer.readFloatLE(offset), // float32
    10: (buffer, offset) => buffer.readDoubleLE(offset), // float64
    11: (buffer, offset) => buffer.readUInt8(offset), // bool8
    12: (buffer, start, end) => buffer.toString('utf8', start, end), // ascii string
};

function getSizeOfType(type) {
    switch (type) {
        case 0: return 1; // int8
        case 1: return 2; // int16
        case 2: return 4; // int32
        case 3: return 8; // int64
        case 4: return 1; // uint8
        case 5: return 2; // uint16
        case 6: return 4; // uint32
        case 7: return 8; // uint64
        case 8: return 4; // float16
        case 9: return 4; // float32
        case 10: return 8; // float64
        case 11: return 1; // bool8
        case 12: return 0; // ascii string (variable length, handled separately)
        default: throw new Error(`Unknown type: ${type}`);
    }
};

function bytesToMacString(bytes) {
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join(':');
}

function parseApiDataObject(data) {
    let position = 0;
    const apiObj = new ApiDataObject();

    const smallEndian = data.readUInt8(position) === 1;
    position += 1;

    const macBytes = data.slice(position, position + 6);
    apiObj.MacAddress = bytesToMacString(macBytes);
    position += 6;

    apiObj.SensorCount = data.readUInt8(position);
    position += 1;

    for (let i = 0; i < apiObj.SensorCount; i++) {
        const sensor = new MeasurementList();
        sensor.SensorID = data.readInt16LE(position);
        position += 2;
        sensor.MeasurementCount = data.readInt32LE(position);
        position += 4;
        sensor.MeasurementsPerLog = data.readUInt8(position);
        position += 1;
        sensor.MeasurementTypes = [];
        for (let j = 0; j < sensor.MeasurementsPerLog; j++) {
            sensor.MeasurementTypes.push(data.readUInt8(position));
            position += 1;
        }
        sensor.Measurements = [];
        for (let j = 0; j < sensor.MeasurementCount; j++) {
            const measurement = new Measurement();
            measurement.TimeFromStartInus = data.readInt32LE(position);
            position += 8;
            measurement.Measurements = [];
            for (let k = 0; k < sensor.MeasurementsPerLog; k++) {
                measurement.Measurements.push(data.readInt32LE(position));
                position += 8;
            }
            sensor.Measurements.push(measurement);
        }
        apiObj.SensorData.push(sensor);
    }

    return apiObj;
}

module.exports = {
    parseApiDataObject,
};