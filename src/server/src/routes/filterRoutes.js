const express = require("express");
const filterRegistry = require("../filters/registry");

const router = express.Router();

const requireAdmin = (req, res) => {
  if (req.user?.role !== "admin") {
    res.status(403).json({ message: "Admin role required." });
    return false;
  }
  return true;
};

/**
 * GET /filters
 * Returns metadata for all loaded filters (built-in + custom).
 * Available to all authenticated users.
 */
router.get("/", (req, res) => {
  try {
    res.json(filterRegistry.getAll());
  } catch (err) {
    res.status(500).json({ message: "Failed to load filters", error: err.message });
  }
});

/**
 * POST /filters
 * Upload a new custom filter.
 * Body: { filename: string, code: string }
 * Admin only.
 */
router.post("/", express.json(), async (req, res) => {
  if (!requireAdmin(req, res)) return;

  const { filename, code } = req.body || {};

  if (typeof filename !== "string" || !filename.trim()) {
    return res.status(400).json({ message: "filename is required" });
  }
  if (typeof code !== "string" || !code.trim()) {
    return res.status(400).json({ message: "code is required" });
  }

  try {
    const meta = filterRegistry.uploadFilter(filename.trim(), code);
    res.status(201).json({ message: "Filter uploaded successfully", filter: meta });
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
});

/**
 * DELETE /filters/:id
 * Remove a custom filter by id. Built-in filters cannot be deleted.
 * Admin only.
 */
router.delete("/:id", (req, res) => {
  if (!requireAdmin(req, res)) return;

  const id = String(req.params.id || "").trim();
  if (!id) return res.status(400).json({ message: "Filter id is required" });

  try {
    filterRegistry.deleteFilter(id);
    res.json({ message: `Filter '${id}' deleted` });
  } catch (err) {
    res.status(400).json({ message: err.message });
  }
});

module.exports = router;
