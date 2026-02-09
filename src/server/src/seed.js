const { Seeder } = require("mongo-seeding");
require("dotenv").config();
const path = require("path");
const { ObjectId } = require("mongodb");

const config = {
  database: process.env.MONGODB_URI,
  dropDatabase: true,
};

const seeder = new Seeder(config);

const driver1Id = new ObjectId();
const driver2Id = new ObjectId();
const track1Id = new ObjectId();
const track2Id = new ObjectId();
const run1Id = new ObjectId();
const run2Id = new ObjectId();

const collections = [
  {
    name: "drivers",
    documents: [
      {
        _id: driver1Id,
        name: "John Doe",
        age: 21,
        licenseNumber: "ABC123",
      },
      {
        _id: driver2Id,
        name: "Jane Smith",
        age: 25,
        licenseNumber: "XYZ789",
      },
    ],
  },
  {
    name: "tracks",
    documents: [
      {
        _id: track1Id,
        name: "Track 1",
        length: 5000,
        location: "City Center",
      },
      {
        _id: track2Id,
        name: "Track 2",
        length: 3000,
        location: "Suburbs",
      },
    ],
  },
  {
    name: "runs",
    documents: [
      {
        _id: run1Id,
        driverId: driver1Id,
        trackId: track1Id,
        time: 120,
        date: new Date("2023-01-01"),
      },
      {
        _id: run2Id,
        driverId: driver2Id,
        trackId: track2Id,
        time: 150,
        date: new Date("2023-01-02"),
      },
    ],
  },
  {
    name: "sensor_readings",
    documents: [
      {
        runId: run1Id,
        sensorId: 1,
        timestamp: new Date("2023-01-01T10:00:00Z"),
        data: [0.1, 0.2, 0.3],
      },
      {
        runId: run2Id,
        sensorId: 2,
        timestamp: new Date("2023-01-01T10:00:00Z"),
        data: [0.4, 0.5, 0.6],
      },
    ],
  },
];

const importData = async () => {
  try {
    await seeder.import(collections);
    console.log("Seed data imported successfully");
  } catch (err) {
    console.error("Error importing seed data:", err);
  }
  process.exit();
};

importData();
