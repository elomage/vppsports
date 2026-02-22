const crypto = require("crypto");
const jwt = require("jsonwebtoken");

const ACCESS_TOKEN_TTL = process.env.ACCESS_TOKEN_TTL || "15m";
const REFRESH_TOKEN_TTL = process.env.REFRESH_TOKEN_TTL || "7d";
const JWT_ISSUER = process.env.JWT_ISSUER || "vppsports-api";
const JWT_AUDIENCE = process.env.JWT_AUDIENCE || "vppsports-client";

const requireEnv = (name, minLength = 32) => {
  const value = process.env[name];
  if (!value || value.length < minLength) {
    throw new Error(
      `${name} is required and must be at least ${minLength} characters`
    );
  }
  return value;
};

const ACCESS_SECRET = requireEnv("JWT_ACCESS_SECRET");
const REFRESH_SECRET = requireEnv("JWT_REFRESH_SECRET");

const getCookieSecureFlag = () => process.env.NODE_ENV === "production";

const hashToken = (token) =>
  crypto.createHash("sha256").update(token).digest("hex");

const signAccessToken = (user) => {
  return jwt.sign(
    {
      sub: String(user._id),
      username: user.username,
      role: user.role,
      tokenVersion: user.tokenVersion,
      type: "access",
    },
    ACCESS_SECRET,
    {
      expiresIn: ACCESS_TOKEN_TTL,
      issuer: JWT_ISSUER,
      audience: JWT_AUDIENCE,
    }
  );
};

const signRefreshToken = (user) => {
  return jwt.sign(
    {
      sub: String(user._id),
      tokenVersion: user.tokenVersion,
      type: "refresh",
    },
    REFRESH_SECRET,
    {
      expiresIn: REFRESH_TOKEN_TTL,
      issuer: JWT_ISSUER,
      audience: JWT_AUDIENCE,
    }
  );
};

const verifyAccessToken = (token) =>
  jwt.verify(token, ACCESS_SECRET, {
    issuer: JWT_ISSUER,
    audience: JWT_AUDIENCE,
  });

const verifyRefreshToken = (token) =>
  jwt.verify(token, REFRESH_SECRET, {
    issuer: JWT_ISSUER,
    audience: JWT_AUDIENCE,
  });

const parseExpiryToDate = (decodedToken) => {
  if (!decodedToken || typeof decodedToken.exp !== "number") {
    return null;
  }
  return new Date(decodedToken.exp * 1000);
};

module.exports = {
  ACCESS_TOKEN_TTL,
  getCookieSecureFlag,
  hashToken,
  parseExpiryToDate,
  signAccessToken,
  signRefreshToken,
  verifyAccessToken,
  verifyRefreshToken,
};
