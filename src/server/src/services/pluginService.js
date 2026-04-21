/**
 * Plugin assignment service.
 *
 * Stores per-context configuration for which plugins are enabled and in what
 * order. Covers both plugin types:
 *   - "filter"        — sensor data processing filters (server-side)
 *   - "visualization" — dashboard visualization components (client-side)
 *
 * Collection: plugin_assignments
 * Schema: one document per { contextId, pluginType }.
 *   contextId: null  →  system-wide default (fallback when no context config).
 *
 * Resolution order: context-specific → global default → all plugins enabled.
 */

const mongoose = require("mongoose");
const { ObjectId } = require("mongodb");

// ─── Static viz plugin registry ──────────────────────────────────────────────
// These match the keys in VisualizationSelection's componentsMap.
const BUILTIN_VIZ_PLUGINS = [
  { id: "echart", label: "Chart (ECharts)", builtin: true },
  { id: "video", label: "Video", builtin: true },
  { id: "info", label: "Info Panel", builtin: true },
  { id: "graph", label: "Graph (uPlot)", builtin: true },
  { id: "model", label: "3D Model", builtin: true },
];

// ─── Schema ───────────────────────────────────────────────────────────────────

const pluginAssignmentSchema = new mongoose.Schema(
  {
    contextId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Context",
      default: null,
      index: true,
    },
    pluginType: {
      type: String,
      enum: ["filter", "visualization"],
      required: true,
    },
    assignments: [
      {
        _id: false,
        pluginId: { type: String, required: true },
        enabled: { type: Boolean, default: true },
        order: { type: Number, default: 0 },
      },
    ],
    updatedAt: { type: Date, default: Date.now },
  },
  { versionKey: false }
);

pluginAssignmentSchema.index(
  { contextId: 1, pluginType: 1 },
  { unique: true }
);

const PluginAssignment =
  mongoose.models.PluginAssignment ||
  mongoose.model(
    "PluginAssignment",
    pluginAssignmentSchema,
    "plugin_assignments"
  );

// ─── Helpers ──────────────────────────────────────────────────────────────────

const resolveContextId = (contextId) => {
  if (!contextId || !ObjectId.isValid(contextId)) return null;
  return new ObjectId(contextId);
};

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Returns the assignments array for a context + type.
 * Falls back to the global default (contextId: null) if no context-specific
 * config exists. Returns null when neither exists (caller uses built-in defaults).
 */
const getAssignments = async (contextId, pluginType) => {
  const contextObjId = resolveContextId(contextId);

  if (contextObjId) {
    const doc = await PluginAssignment.findOne({
      contextId: contextObjId,
      pluginType,
    }).lean();
    if (doc) return { assignments: doc.assignments, hasContextConfig: true };
  }

  const globalDoc = await PluginAssignment.findOne({
    contextId: null,
    pluginType,
  }).lean();

  return globalDoc
    ? { assignments: globalDoc.assignments, hasContextConfig: false }
    : { assignments: null, hasContextConfig: false };
};

/**
 * Saves (upsert) assignments for a context + type.
 */
const updateAssignments = async (contextId, pluginType, assignments) => {
  const contextObjId = resolveContextId(contextId);

  await PluginAssignment.findOneAndUpdate(
    { contextId: contextObjId, pluginType },
    { contextId: contextObjId, pluginType, assignments, updatedAt: new Date() },
    { upsert: true, new: true }
  );
};

/**
 * Deletes the context-specific assignment doc, reverting to global defaults.
 * Cannot be called for the global default itself (contextId must be provided).
 */
const resetAssignments = async (contextId, pluginType) => {
  const contextObjId = resolveContextId(contextId);
  if (!contextObjId) {
    throw new Error(
      "A valid contextId is required to reset context-specific plugin config."
    );
  }
  await PluginAssignment.deleteOne({ contextId: contextObjId, pluginType });
};

module.exports = {
  BUILTIN_VIZ_PLUGINS,
  getAssignments,
  updateAssignments,
  resetAssignments,
};
