const mongoose = require("mongoose");

const contextRoleSchema = new mongoose.Schema(
  {
    context: {
      type: String,
      required: true,
      trim: true,
      lowercase: true,
      minlength: 2,
      maxlength: 64,
    },
    role: {
      type: String,
      required: true,
      enum: ["admin", "user"],
      default: "user",
    },
  },
  {
    _id: false,
  }
);

const userSchema = new mongoose.Schema(
  {
    username: {
      type: String,
      required: true,
      unique: true,
      trim: true,
      lowercase: true,
      minlength: 3,
      maxlength: 64,
    },
    passwordHash: {
      type: String,
      required: true,
      minlength: 60,
      maxlength: 60,
      select: false,
    },
    role: {
      type: String,
      default: "user",
      enum: ["admin", "user"],
    },
    contextRoles: {
      type: [contextRoleSchema],
      default: [],
    },
    isActive: {
      type: Boolean,
      default: true,
    },
    tokenVersion: {
      type: Number,
      default: 0,
    },
    refreshTokenHash: {
      type: String,
      default: null,
      select: false,
    },
    refreshTokenExpiresAt: {
      type: Date,
      default: null,
    },
  },
  {
    timestamps: true,
  }
);

userSchema.methods.getRoleForContext = function getRoleForContext(contextName) {
  const normalizedContext = String(contextName || "")
    .trim()
    .toLowerCase();

  if (!normalizedContext) {
    return this.role;
  }

  const contextRole = this.contextRoles.find(
    ({ context }) => context === normalizedContext
  );

  return contextRole ? contextRole.role : null;
};

userSchema.methods.hasRoleInContext = function hasRoleInContext(
  contextName,
  allowedRoles = []
) {
  const contextRole = this.getRoleForContext(contextName);

  if (!Array.isArray(allowedRoles) || allowedRoles.length === 0) {
    return Boolean(contextRole);
  }

  return allowedRoles.includes(contextRole);
};

module.exports = mongoose.model("User", userSchema);
