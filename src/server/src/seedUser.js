require("dotenv").config();
const mongoose = require("mongoose");
const bcrypt = require("bcryptjs");

const User = require("./models/User");

const BCRYPT_ROUNDS = 12;

const parseContextRoles = (value, fallbackRole = "user") => {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return [];
  }

  return rawValue
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const [contextPart, rolePart] = entry.split(":");
      const context = String(contextPart || "")
        .trim()
        .toLowerCase();
      const role = String(rolePart || fallbackRole)
        .trim()
        .toLowerCase();

      if (!context) {
        throw new Error(
          "Context roles must use 'context:role' format, for example 'sport:user'."
        );
      }

      if (!["admin", "user"].includes(role)) {
        throw new Error(
          `Invalid role '${role}' in context roles. Allowed roles: admin, user.`
        );
      }

      return { context, role };
    });
};

const parseAndValidate = () => {
  const mongoUri = process.env.MONGODB_URI;
  const username = String(process.env.ADMIN_USERNAME || "")
    .trim()
    .toLowerCase();
  const password = String(process.env.ADMIN_PASSWORD || "");
  const contextRoles = parseContextRoles(
    process.env.ADMIN_CONTEXT_ROLES,
    "admin"
  );

  if (!mongoUri) {
    throw new Error("MONGODB_URI is required.");
  }
  if (username.length < 3 || username.length > 64) {
    throw new Error("ADMIN_USERNAME must be 3-64 characters.");
  }
  if (password.length < 12 || password.length > 128) {
    throw new Error("ADMIN_PASSWORD must be 12-128 characters.");
  }

  return { mongoUri, username, password, contextRoles };
};

const seedUser = async () => {
  const { mongoUri, username, password, contextRoles } = parseAndValidate();
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
        contextRoles,
        isActive: true,
        refreshTokenHash: null,
        refreshTokenExpiresAt: null,
        tokenVersion,
      },
    },
    { upsert: true }
  );

  const finalUser = await User.findOne({ username }).select(
    "_id username role contextRoles isActive"
  );
  console.log(
    JSON.stringify(
      {
        message: "Seeded admin user.",
        user: {
          id: String(finalUser._id),
          username: finalUser.username,
          role: finalUser.role,
          contextRoles: finalUser.contextRoles,
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
