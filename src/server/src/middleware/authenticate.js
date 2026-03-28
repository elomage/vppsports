const User = require("../models/User");
const { verifyAccessToken } = require("../utils/auth");

const authenticateAccessToken = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization || "";
    if (!authHeader.startsWith("Bearer ")) {
      return res.status(401).json({ message: "Missing Bearer token" });
    }

    const token = authHeader.slice("Bearer ".length).trim();
    if (!token) {
      return res.status(401).json({ message: "Invalid token format" });
    }

    const decoded = verifyAccessToken(token);
    if (decoded.type !== "access") {
      return res.status(401).json({ message: "Invalid token type" });
    }

    const user = await User.findById(decoded.sub).select(
      "_id username role contextRoles tokenVersion isActive"
    );
    if (!user || !user.isActive) {
      return res.status(401).json({ message: "User is inactive" });
    }

    if (user.tokenVersion !== decoded.tokenVersion) {
      return res.status(401).json({ message: "Token revoked" });
    }

    req.user = user;
    return next();
  } catch (error) {
    return res.status(401).json({ message: "Unauthorized" });
  }
};

module.exports = { authenticateAccessToken };
