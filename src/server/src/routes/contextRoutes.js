const express = require("express");

const { connectDB, getCollection } = require("../config/db");

const router = express.Router();

const normalizeContext = (value) =>
  String(value || "")
    .trim()
    .toLowerCase();

const requireAdmin = (req, res) => {
  if (req.user?.role !== "admin") {
    res.status(403).json({ message: "Admin role required." });
    return false;
  }

  return true;
};

router.get("/", async (req, res) => {
  try {
    const db = await connectDB();
    const contextsColl = await getCollection(db, "contexts");
    const contexts = await contextsColl
      .find(
        { deletedAt: null },
        { projection: { _id: 0, name: 1, createdAt: 1 } }
      )
      .sort({ name: 1 })
      .toArray();

    return res.json(
      contexts.map((context) => ({
        name: normalizeContext(context.name),
        createdAt: context.createdAt || null,
      }))
    );
  } catch (error) {
    return res.status(500).json({
      message: "Failed to fetch contexts.",
      error: error.message,
    });
  }
});

router.get("/deleted", async (req, res) => {
  try {
    const db = await connectDB();
    const contextsColl = await getCollection(db, "contexts");
    const contexts = await contextsColl
      .find(
        { deletedAt: { $ne: null } },
        { projection: { _id: 0, name: 1, createdAt: 1, deletedAt: 1 } }
      )
      .sort({ deletedAt: -1, name: 1 })
      .toArray();

    return res.json(
      contexts.map((context) => ({
        name: normalizeContext(context.name),
        createdAt: context.createdAt || null,
        deletedAt: context.deletedAt || null,
      }))
    );
  } catch (error) {
    return res.status(500).json({
      message: "Failed to fetch deleted contexts.",
      error: error.message,
    });
  }
});

router.post("/", async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const normalizedName = normalizeContext(req.body?.name);
    if (!normalizedName) {
      return res.status(400).json({ message: "Context name is required." });
    }

    const db = await connectDB();
    const contextsColl = await getCollection(db, "contexts");

    await contextsColl.createIndex({ name: 1 }, { unique: true });

    const existingContext = await contextsColl.findOne({ name: normalizedName });
    if (existingContext) {
      return res.status(409).json({
        message: "Context name must be unique across active and deleted contexts.",
      });
    }

    const document = {
      name: normalizedName,
      createdAt: new Date(),
      deletedAt: null,
    };

    await contextsColl.insertOne(document);

    return res.status(201).json({
      message: "Context created successfully.",
      context: document,
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to create context.",
      error: error.message,
    });
  }
});

router.post("/:name/restore", async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const normalizedName = normalizeContext(req.params.name);
    if (!normalizedName) {
      return res.status(400).json({ message: "Context name is required." });
    }

    const db = await connectDB();
    const contextsColl = await getCollection(db, "contexts");
    const result = await contextsColl.updateOne(
      { name: normalizedName, deletedAt: { $ne: null } },
      {
        $set: {
          deletedAt: null,
          restoredAt: new Date(),
          updatedAt: new Date(),
        },
      }
    );

    if (result.matchedCount !== 1) {
      return res.status(404).json({ message: "Deleted context not found." });
    }

    return res.json({
      message: "Context restored successfully.",
      context: {
        name: normalizedName,
        deletedAt: null,
      },
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to restore context.",
      error: error.message,
    });
  }
});

router.patch("/:name", async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const currentName = normalizeContext(req.params.name);
    const nextName = normalizeContext(req.body?.name);

    if (!currentName || !nextName) {
      return res.status(400).json({ message: "Context name is required." });
    }

    if (currentName === nextName) {
      return res.status(200).json({
        message: "Context name unchanged.",
        context: { name: currentName },
      });
    }

    const db = await connectDB();
    const contextsColl = await getCollection(db, "contexts");
    await contextsColl.createIndex({ name: 1 }, { unique: true });

    const currentContext = await contextsColl.findOne({
      name: currentName,
      deletedAt: null,
    });
    if (!currentContext) {
      return res.status(404).json({ message: "Context not found." });
    }

    const targetContext = await contextsColl.findOne({ name: nextName });
    if (targetContext) {
      return res.status(409).json({
        message:
          "Context name must be unique across active and deleted contexts.",
      });
    }

    await contextsColl.updateOne(
      { name: currentName, deletedAt: null },
      {
        $set: {
          name: nextName,
          updatedAt: new Date(),
        },
      }
    );

    return res.json({
      message: "Context updated successfully.",
      context: {
        name: nextName,
        createdAt: currentContext.createdAt || null,
        deletedAt: null,
      },
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to update context.",
      error: error.message,
    });
  }
});

router.delete("/:name", async (req, res) => {
  try {
    if (!requireAdmin(req, res)) return;

    const normalizedName = normalizeContext(req.params.name);
    if (!normalizedName) {
      return res.status(400).json({ message: "Context name is required." });
    }

    const db = await connectDB();
    const contextsColl = await getCollection(db, "contexts");
    const result = await contextsColl.updateOne(
      { name: normalizedName, deletedAt: null },
      {
        $set: {
          deletedAt: new Date(),
        },
      }
    );

    if (result.matchedCount !== 1) {
      return res.status(404).json({ message: "Context not found." });
    }

    return res.json({
      message: "Context removed successfully.",
      context: {
        name: normalizedName,
      },
    });
  } catch (error) {
    return res.status(500).json({
      message: "Failed to remove context.",
      error: error.message,
    });
  }
});

module.exports = router;
