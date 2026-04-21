/**
 * Plugin assignment routes.
 *
 * GET  /plugins?contextId=...&pluginType=filter|visualization
 *   Returns all available plugins for the type, merged with the context's
 *   assignment config (or global defaults). Open to all authenticated users.
 *
 * PUT  /plugins?contextId=...&pluginType=...
 *   Body: { assignments: [{ pluginId, enabled, order }] }
 *   Saves config for the given context (null contextId = global default).
 *   Admin only.
 *
 * DELETE /plugins?contextId=...&pluginType=...
 *   Resets a context's config back to the global default. Admin only.
 */

const express = require("express");
const router = express.Router();
const filterRegistry = require("../filters/registry");
const {
  BUILTIN_VIZ_PLUGINS,
  getAssignments,
  updateAssignments,
  resetAssignments,
} = require("../services/pluginService");

const VALID_PLUGIN_TYPES = ["filter", "visualization"];

const requireAdmin = (req, res) => {
  if (req.user?.role !== "admin") {
    res.status(403).json({ message: "Admin role required." });
    return false;
  }
  return true;
};

const getAvailablePlugins = (pluginType) => {
  if (pluginType === "visualization") {
    return BUILTIN_VIZ_PLUGINS;
  }
  return filterRegistry
    .getAll()
    .map(({ id, label, builtin, params }) => ({ id, label, builtin, params }));
};

// GET /plugins?contextId=...&pluginType=filter|visualization
router.get("/", async (req, res) => {
  try {
    const { contextId, pluginType } = req.query;

    if (!VALID_PLUGIN_TYPES.includes(pluginType)) {
      return res.status(400).json({
        message: `pluginType must be one of: ${VALID_PLUGIN_TYPES.join(", ")}`,
      });
    }

    const available = getAvailablePlugins(pluginType);
    const { assignments, hasContextConfig } = await getAssignments(
      contextId || null,
      pluginType
    );

    // Merge available plugins with their assignment config.
    // Plugins not in the assignment list default to enabled.
    const plugins = available
      .map((plugin, idx) => {
        const assignment = assignments?.find((a) => a.pluginId === plugin.id);
        return {
          ...plugin,
          enabled: assignment ? assignment.enabled : true,
          order: assignment ? assignment.order : idx,
        };
      })
      .sort((a, b) => a.order - b.order);

    return res.json({ plugins, hasContextConfig });
  } catch (err) {
    return res.status(500).json({
      message: "Failed to fetch plugin assignments.",
      error: err.message,
    });
  }
});

// PUT /plugins?contextId=...&pluginType=...
router.put("/", express.json(), async (req, res) => {
  if (!requireAdmin(req, res)) return;

  try {
    const { contextId, pluginType } = req.query;

    if (!VALID_PLUGIN_TYPES.includes(pluginType)) {
      return res.status(400).json({
        message: `pluginType must be one of: ${VALID_PLUGIN_TYPES.join(", ")}`,
      });
    }

    const { assignments } = req.body || {};
    if (!Array.isArray(assignments)) {
      return res.status(400).json({ message: "assignments must be an array." });
    }

    const normalized = assignments
      .map((a, idx) => ({
        pluginId: String(a.pluginId || "").trim(),
        enabled: Boolean(a.enabled ?? true),
        order: Number.isFinite(Number(a.order)) ? Number(a.order) : idx,
      }))
      .filter((a) => a.pluginId);

    await updateAssignments(contextId || null, pluginType, normalized);
    return res.json({ message: "Plugin assignments updated." });
  } catch (err) {
    return res.status(500).json({
      message: "Failed to update plugin assignments.",
      error: err.message,
    });
  }
});

// DELETE /plugins?contextId=...&pluginType=...
router.delete("/", async (req, res) => {
  if (!requireAdmin(req, res)) return;

  try {
    const { contextId, pluginType } = req.query;

    if (!contextId) {
      return res.status(400).json({
        message: "contextId is required to reset context-specific config.",
      });
    }

    if (!VALID_PLUGIN_TYPES.includes(pluginType)) {
      return res.status(400).json({
        message: `pluginType must be one of: ${VALID_PLUGIN_TYPES.join(", ")}`,
      });
    }

    await resetAssignments(contextId, pluginType);
    return res.json({
      message: "Context plugin config reset to global defaults.",
    });
  } catch (err) {
    return res.status(500).json({
      message: "Failed to reset plugin assignments.",
      error: err.message,
    });
  }
});

module.exports = router;
