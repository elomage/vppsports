require("dotenv").config();
const mongoose = require("mongoose");
const bcrypt = require("bcryptjs");
const { ObjectId } = require("mongodb");

const User = require("./models/User");
const { connectDB, getCollection } = require("./config/db");

const BCRYPT_ROUNDS = 12;

const parseContextNames = (value) => {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return [];
  }

  return rawValue
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const context = String(entry || "")
        .trim()
        .toLowerCase();

      if (!context) {
        throw new Error("Context names must be comma-separated non-empty values.");
      }

      return context;
    });
};

const parseAndValidate = () => {
  const mongoUri = process.env.MONGODB_URI;
  const username = String(process.env.ADMIN_USERNAME || "")
    .trim()
    .toLowerCase();
  const password = String(process.env.ADMIN_PASSWORD || "");
  const contextNames = parseContextNames(process.env.ADMIN_CONTEXTS);

  if (!mongoUri) {
    throw new Error("MONGODB_URI is required.");
  }
  if (username.length < 3 || username.length > 64) {
    throw new Error("ADMIN_USERNAME must be 3-64 characters.");
  }
  if (password.length < 12 || password.length > 128) {
    throw new Error("ADMIN_PASSWORD must be 12-128 characters.");
  }

  return { mongoUri, username, password, contextNames };
};

const seedUser = async () => {
  const { mongoUri, username, password, contextNames } = parseAndValidate();
  await mongoose.connect(mongoUri);
  const db = await connectDB();
  const contextsColl = await getCollection(db, "contexts");

  const contexts = contextNames.length
    ? await contextsColl
        .find(
          { name: { $in: contextNames }, deletedAt: null },
          { projection: { _id: 1, name: 1 } }
        )
        .toArray()
    : [];

  if (contexts.length !== contextNames.length) {
    const found = new Set(contexts.map((entry) => String(entry.name || "").trim().toLowerCase()));
    const missing = contextNames.filter((entry) => !found.has(entry));
    throw new Error(`ADMIN_CONTEXTS contains unknown or deleted contexts: ${missing.join(", ")}`);
  }

  const contextIds = contexts.map((entry) => new ObjectId(entry._id));

  const passwordHash = await bcrypt.hash(password, BCRYPT_ROUNDS);

  const existingUser = await User.findOne({ username }).select(
    "+passwordHash tokenVersion"
  );
  let tokenVersion = existingUser ? existingUser.tokenVersion : 0;

  if (existingUser) {
    const samePassword = await bcrypt.compare(password, existingUser.passwordHash);
    if (!samePassword) {
      tokenVersion += 1;
    }
  }

  await User.updateOne(
    { username },
    {
      $set: {
        username,
        passwordHash,
        role: "admin",
        contexts: contextIds,
        isActive: true,
        refreshTokenHash: null,
        refreshTokenExpiresAt: null,
        tokenVersion,
      },
    },
    { upsert: true }
  );

  const finalUser = await User.findOne({ username }).select(
    "_id username role contexts isActive"
  );
  console.log(
    JSON.stringify(
      {
        message: "Seeded admin user.",
        user: {
          id: String(finalUser._id),
          username: finalUser.username,
          role: finalUser.role,
          contexts: (finalUser.contexts || []).map((entry) => String(entry)),
          isActive: finalUser.isActive,
        },
      },
      null,
      2
    )
  );
};

seedUser()
  .catch((error) => {
    console.error("Failed to seed user:", error.message);
    process.exitCode = 1;
  })
  .finally(async () => {
    await mongoose.connection.close();
  });
