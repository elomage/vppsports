require("dotenv").config();
const mongoose = require("mongoose");
const bcrypt = require("bcryptjs");

const User = require("./models/User");

const BCRYPT_ROUNDS = 12;

const parseAndValidate = () => {
  const mongoUri = process.env.MONGODB_URI;
  const username = String(process.env.ADMIN_USERNAME || "")
    .trim()
    .toLowerCase();
  const password = String(process.env.ADMIN_PASSWORD || "");

  if (!mongoUri) {
    throw new Error("MONGODB_URI is required.");
  }
  if (username.length < 3 || username.length > 64) {
    throw new Error("ADMIN_USERNAME must be 3-64 characters.");
  }
  if (password.length < 12 || password.length > 128) {
    throw new Error("ADMIN_PASSWORD must be 12-128 characters.");
  }

  return { mongoUri, username, password };
};

const seedUser = async () => {
  const { mongoUri, username, password } = parseAndValidate();
  await mongoose.connect(mongoUri);

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
        isActive: true,
        refreshTokenHash: null,
        refreshTokenExpiresAt: null,
        tokenVersion,
      },
    },
    { upsert: true }
  );

  // Keep single-user mode by disabling all other users and revoking their sessions.
  await User.updateMany(
    { username: { $ne: username } },
    {
      $set: {
        isActive: false,
        refreshTokenHash: null,
        refreshTokenExpiresAt: null,
      },
      $inc: { tokenVersion: 1 },
    }
  );

  const finalUser = await User.findOne({ username }).select("_id username role isActive");
  console.log(
    JSON.stringify(
      {
        message: "Seeded single auth user.",
        user: {
          id: String(finalUser._id),
          username: finalUser.username,
          role: finalUser.role,
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
