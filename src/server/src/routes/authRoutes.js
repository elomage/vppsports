const bcrypt = require("bcryptjs");
const express = require("express");

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

const router = express.Router();
const REFRESH_COOKIE_NAME = "refreshToken";

const normalizeContextRoles = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }

  const seenContexts = new Set();
  const normalizedRoles = [];

  value.forEach((entry) => {
    const context = String(entry?.context || "")
      .trim()
      .toLowerCase();
    const role = String(entry?.role || "user")
      .trim()
      .toLowerCase();

    if (!context) {
      throw new Error("Each context role requires a context.");
    }

    if (!["admin", "user"].includes(role)) {
      throw new Error(
        `Invalid context role '${role}'. Allowed roles: admin, user.`
      );
    }

    if (seenContexts.has(context)) {
      throw new Error(`Duplicate context '${context}' is not allowed.`);
    }

    seenContexts.add(context);
    normalizedRoles.push({ context, role });
  });

  return normalizedRoles;
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
      "+passwordHash +refreshTokenHash tokenVersion role contextRoles username isActive"
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
      user: {
        id: user._id,
        username: user.username,
        role: user.role,
        contextRoles: user.contextRoles,
      },
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
      "+refreshTokenHash tokenVersion username role contextRoles isActive refreshTokenExpiresAt"
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
    user: {
      id: req.user._id,
      username: req.user.username,
      role: req.user.role,
      contextRoles: req.user.contextRoles,
    },
  });
});

router.post("/users", authenticateAccessToken, async (req, res) => {
  try {
    if (req.user.role !== "admin") {
      return res.status(403).json({ message: "Admin role required." });
    }

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

    let contextRoles = [];
    try {
      contextRoles = normalizeContextRoles(req.body?.contextRoles);
    } catch (error) {
      return res.status(400).json({ message: error.message });
    }

    const existingUser = await User.findOne({ username: parsed.username })
      .select("_id")
      .lean();
    if (existingUser) {
      return res.status(409).json({ message: "Username already exists." });
    }

    const passwordHash = await bcrypt.hash(parsed.password, 12);
    const createdUser = await User.create({
      username: parsed.username,
      passwordHash,
      role,
      contextRoles,
    });

    return res.status(201).json({
      message: "User created successfully.",
      user: {
        id: createdUser._id,
        username: createdUser.username,
        role: createdUser.role,
        contextRoles: createdUser.contextRoles,
        isActive: createdUser.isActive,
      },
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to create user.",
      error: error.message,
    });
  }
});

module.exports = router;
