const { MongoClient } = require("mongodb");

let db;

const connectDB = async () => {
  if (db) return db;
  try {
    const client = new MongoClient(process.env.MONGODB_URI);
    await client.connect();
    db = client.db();
    console.log("Connected to MongoDB");
    return db;
  } catch (error) {
    console.error("Could not connect to MongoDB", error);
    throw error;
  }
};

const getCollection = async (db, collectionName) => {
  return db.collection(collectionName);
};

module.exports = { connectDB, getCollection };
