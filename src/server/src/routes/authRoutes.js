const bcrypt = require("bcryptjs");
const express = require("express");

const { connectDB, getCollection } = require("../config/db");
const User = require("../models/User");
const { authenticateAccessToken } = require("../middleware/authenticate");
const {
  ACCESS_TOKEN_TTL,
  getCookieSecureFlag,
  hashToken,
  parseExpiryToDate,
  signAccessToken,
  signRefreshToken,
  verifyRefreshToken,
} = require("../utils/auth");
const { normalizeContextIds, serializeUser } = require("../utils/userContexts");

const router = express.Router();
const REFRESH_COOKIE_NAME = "refreshToken";

const normalizeUserContexts = async (value) => {
  const contextIds = normalizeContextIds(value);
  if (contextIds.length === 0) {
    return [];
  }

  const db = await connectDB();
  const contextsColl = await getCollection(db, "contexts");
  const activeContexts = await contextsColl
    .find(
      { _id: { $in: contextIds }, deletedAt: null },
      { projection: { _id: 1 } }
    )
    .toArray();

  if (activeContexts.length !== contextIds.length) {
    throw new Error("Each selected context must exist and be active.");
  }

  return contextIds;
};

const buildRefreshCookieOptions = () => ({
  httpOnly: true,
  secure: getCookieSecureFlag(),
  sameSite: "lax",
  path: "/auth",
});

const createTokenPair = async (user) => {
  const accessToken = signAccessToken(user);
  const refreshToken = signRefreshToken(user);
  const decodedRefreshToken = verifyRefreshToken(refreshToken);

  user.refreshTokenHash = hashToken(refreshToken);
  user.refreshTokenExpiresAt = parseExpiryToDate(decodedRefreshToken);
  await user.save();

  return { accessToken, refreshToken };
};

const validateCredentials = ({ username, password }) => {
  const normalizedUsername = String(username || "")
    .trim()
    .toLowerCase();
  const normalizedPassword = String(password || "");

  if (normalizedUsername.length < 3 || normalizedUsername.length > 64) {
    return { error: "Username must be 3-64 characters long." };
  }

  if (normalizedPassword.length < 12 || normalizedPassword.length > 128) {
    return { error: "Password must be 12-128 characters long." };
  }

  return {
    username: normalizedUsername,
    password: normalizedPassword,
  };
};

const requireAdmin = (req, res) => {
  if (req.user?.role !== "admin") {
    res.status(403).json({ message: "Admin role required." });
    return false;
  }

  return true;
};

router.post("/login", async (req, res) => {
  try {
    const parsed = validateCredentials(req.body || {});
    if (parsed.error) {
      return res.status(400).json({ message: parsed.error });
    }

    const userCount = await User.countDocuments();
    if (userCount === 0) {
      return res.status(404).json({
        message:
          "No user provisioned. Create one by running 'npm run seed:user' in src/server.",
      });
    }

    const user = await User.findOne({ username: parsed.username }).select(
      "+passwordHash +refreshTokenHash tokenVersion role contexts username isActive +contextRoles"
    );

    if (!user || !user.isActive) {
      return res.status(401).json({ message: "Invalid credentials." });
    }

    const isMatch = await bcrypt.compare(parsed.password, user.passwordHash);
    if (!isMatch) {
      return res.status(401).json({ message: "Invalid credentials." });
    }

    const { accessToken, refreshToken } = await createTokenPair(user);
    res.cookie(
      REFRESH_COOKIE_NAME,
      refreshToken,
      buildRefreshCookieOptions()
    );

    return res.json({
      accessToken,
      tokenType: "Bearer",
      expiresIn: ACCESS_TOKEN_TTL,
      user: await serializeUser(user),
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to login.",
      error: error.message,
    });
  }
});

router.post("/refresh", async (req, res) => {
  try {
    const cookieToken = req.cookies && req.cookies[REFRESH_COOKIE_NAME];
    const bodyToken =
      req.body && typeof req.body.refreshToken === "string"
        ? req.body.refreshToken
        : null;
    const refreshToken = cookieToken || bodyToken;

    if (!refreshToken) {
      return res.status(401).json({ message: "Missing refresh token." });
    }

    const decoded = verifyRefreshToken(refreshToken);
    if (decoded.type !== "refresh") {
      return res.status(401).json({ message: "Invalid token type." });
    }

    const user = await User.findById(decoded.sub).select(
      "+refreshTokenHash tokenVersion username role contexts isActive refreshTokenExpiresAt +contextRoles"
    );

    if (!user || !user.isActive) {
      return res.status(401).json({ message: "Invalid refresh token." });
    }

    if (user.tokenVersion !== decoded.tokenVersion) {
      return res.status(401).json({ message: "Token revoked." });
    }

    const incomingHash = hashToken(refreshToken);
    if (!user.refreshTokenHash || user.refreshTokenHash !== incomingHash) {
      user.tokenVersion += 1;
      user.refreshTokenHash = null;
      user.refreshTokenExpiresAt = null;
      await user.save();
      return res.status(401).json({ message: "Refresh token mismatch." });
    }

    const { accessToken, refreshToken: rotatedRefreshToken } =
      await createTokenPair(user);

    res.cookie(
      REFRESH_COOKIE_NAME,
      rotatedRefreshToken,
      buildRefreshCookieOptions()
    );

    return res.json({
      accessToken,
      tokenType: "Bearer",
      expiresIn: ACCESS_TOKEN_TTL,
    });
  } catch (error) {
    return res.status(401).json({ message: "Invalid refresh token." });
  }
});

router.post("/logout", authenticateAccessToken, async (req, res) => {
  try {
    const user = await User.findById(req.user._id).select(
      "+refreshTokenHash tokenVersion"
    );
    if (user) {
      user.tokenVersion += 1;
      user.refreshTokenHash = null;
      user.refreshTokenExpiresAt = null;
      await user.save();
    }

    res.clearCookie(REFRESH_COOKIE_NAME, buildRefreshCookieOptions());
    return res.status(204).send();
  } catch (error) {
    return res.status(500).json({ message: "Failed to logout." });
  }
});

router.get("/me", authenticateAccessToken, async (req, res) => {
  return res.json({
    user: await serializeUser(req.user),
  });
});

router.get("/users", authenticateAccessToken, async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const users = await User.find(
      { isActive: true },
      "username role contexts isActive createdAt updatedAt deletedAt restoredAt +contextRoles"
    )
      .sort({ username: 1 })
      .lean();

    return res.json(await Promise.all(users.map((user) => serializeUser(user))));
  } catch (error) {
    return res.status(500).json({
      message: "Failed to fetch users.",
      error: error.message,
    });
  }
});

router.get("/users/deleted", authenticateAccessToken, async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const users = await User.find(
      { isActive: false },
      "username role contexts isActive createdAt updatedAt deletedAt restoredAt +contextRoles"
    )
      .sort({ deletedAt: -1, username: 1 })
      .lean();

    return res.json(await Promise.all(users.map((user) => serializeUser(user))));
  } catch (error) {
    return res.status(500).json({
      message: "Failed to fetch deleted users.",
      error: error.message,
    });
  }
});

router.post("/users", authenticateAccessToken, async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const parsed = validateCredentials(req.body || {});
    if (parsed.error) {
      return res.status(400).json({ message: parsed.error });
    }

    const role = String(req.body?.role || "user")
      .trim()
      .toLowerCase();
    if (!["admin", "user"].includes(role)) {
      return res
        .status(400)
        .json({ message: "Role must be either 'admin' or 'user'." });
    }

    let contexts = [];
    try {
      contexts = await normalizeUserContexts(req.body?.contextIds);
    } catch (error) {
      return res.status(400).json({ message: error.message });
    }

    const existingUser = await User.findOne({ username: parsed.username })
      .select("_id")
      .lean();
    if (existingUser) {
      return res.status(409).json({
        message: "Username must be unique across active and deleted users.",
      });
    }

    const passwordHash = await bcrypt.hash(parsed.password, 12);
    const createdUser = await User.create({
      username: parsed.username,
      passwordHash,
      role,
      contexts,
    });

    return res.status(201).json({
      message: "User created successfully.",
      user: await serializeUser(createdUser),
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to create user.",
      error: error.message,
    });
  }
});

router.patch("/users/:username", authenticateAccessToken, async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const currentUsername = String(req.params.username || "")
      .trim()
      .toLowerCase();
    if (!currentUsername) {
      return res.status(400).json({ message: "Username is required." });
    }

    const nextUsername = String(req.body?.username || "")
      .trim()
      .toLowerCase();
    if (nextUsername.length < 3 || nextUsername.length > 64) {
      return res.status(400).json({ message: "Username must be 3-64 characters long." });
    }

    const role = String(req.body?.role || "user")
      .trim()
      .toLowerCase();
    if (!["admin", "user"].includes(role)) {
      return res
        .status(400)
        .json({ message: "Role must be either 'admin' or 'user'." });
    }

    let contexts = [];
    try {
      contexts = await normalizeUserContexts(req.body?.contextIds);
    } catch (error) {
      return res.status(400).json({ message: error.message });
    }

    const currentUser = await User.findOne({ username: currentUsername });
    if (!currentUser) {
      return res.status(404).json({ message: "User not found." });
    }

    const conflictingUser = await User.findOne({
      username: nextUsername,
      _id: { $ne: currentUser._id },
    })
      .select("_id")
      .lean();
    if (conflictingUser) {
      return res.status(409).json({
        message: "Username must be unique across active and deleted users.",
      });
    }

    currentUser.username = nextUsername;
    currentUser.role = role;
    currentUser.contexts = contexts;

    const password = req.body?.password;
    if (typeof password === "string" && password.length > 0) {
      if (password.length < 12 || password.length > 128) {
        return res
          .status(400)
          .json({ message: "Password must be 12-128 characters long." });
      }
      currentUser.passwordHash = await bcrypt.hash(password, 12);
    }

    await currentUser.save();

    return res.json({
      message: "User updated successfully.",
      user: await serializeUser(currentUser),
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to update user.",
      error: error.message,
    });
  }
});

router.delete("/users/:username", authenticateAccessToken, async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const username = String(req.params.username || "")
      .trim()
      .toLowerCase();
    if (!username) {
      return res.status(400).json({ message: "Username is required." });
    }

    const result = await User.updateOne(
      { username, isActive: true },
      {
        $set: {
          isActive: false,
          deletedAt: new Date(),
          refreshTokenHash: null,
          refreshTokenExpiresAt: null,
        },
        $inc: {
          tokenVersion: 1,
        },
      }
    );

    if (result.matchedCount !== 1) {
      return res.status(404).json({ message: "User not found." });
    }

    return res.json({
      message: "User removed successfully.",
      user: {
        username,
        isActive: false,
      },
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to remove user.",
      error: error.message,
    });
  }
});

router.post(
  "/users/:username/restore",
  authenticateAccessToken,
  async (req, res) => {
    try {
      if (!requireAdmin(req, res)) return;

      const username = String(req.params.username || "")
        .trim()
        .toLowerCase();
      if (!username) {
        return res.status(400).json({ message: "Username is required." });
      }

      const result = await User.updateOne(
        { username, isActive: false },
        {
          $set: {
            isActive: true,
            deletedAt: null,
            restoredAt: new Date(),
          },
        }
      );

      if (result.matchedCount !== 1) {
        return res.status(404).json({ message: "Deleted user not found." });
      }

      return res.json({
        message: "User restored successfully.",
        user: {
          username,
          isActive: true,
          deletedAt: null,
        },
      });
    } catch (error) {
      return res.status(500).json({
        message: "Failed to restore user.",
        error: error.message,
      });
    }
  }
);

module.exports = router;
