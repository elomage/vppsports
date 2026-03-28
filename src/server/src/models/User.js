const mongoose = require("mongoose");

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
    contexts: {
      type: [mongoose.Schema.Types.ObjectId],
      default: [],
    },
    contextRoles: {
      type: [
        new mongoose.Schema(
          {
            context: {
              type: String,
              trim: true,
              lowercase: true,
            },
          },
          { _id: false }
        ),
      ],
      default: undefined,
      select: false,
    },
    isActive: {
      type: Boolean,
      default: true,
    },
    deletedAt: {
      type: Date,
      default: null,
    },
    restoredAt: {
      type: Date,
      default: null,
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

module.exports = mongoose.model("User", userSchema);
