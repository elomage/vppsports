/**
 * Filter registry — loads built-in and custom filter plugins, exposes them
 * to the rest of the server, and handles upload/delete of custom filters.
 *
 * Built-in filters live in:  <repo>/src/server/filters/
 * Custom (uploaded) filters: <repo>/src/server/custom-filters/
 *
 * Each filter file must export:
 *   { id, label, description?, params, apply(readings, params) }
 *
 * apply() contract:
 *   - readings: Array<{ timestamp: number, data: number[] }>
 *   - params:   Record<string, number>
 *   - returns:  Array<{ timestamp: number, data: number[] }>  (new array, no mutation)
 *   - must be synchronous
 */
const path = require("path");
const fs = require("fs");

const BUILTIN_DIR = path.resolve(__dirname, "../../filters");
const CUSTOM_DIR = path.resolve(__dirname, "../../custom-filters");

// Map<id, { id, label, description, params, builtin, filepath, apply }>
const registry = new Map();

function validateFilterModule(mod, filepath) {
  if (!mod || typeof mod !== "object") {
    throw new Error("Filter must export a plain object");
  }
  if (typeof mod.id !== "string" || !/^[a-z0-9_-]+$/.test(mod.id)) {
    throw new Error(
      "Filter 'id' must be a non-empty lowercase alphanumeric string",
    );
  }
  if (typeof mod.label !== "string" || !mod.label.trim()) {
    throw new Error("Filter must have a non-empty 'label' string");
  }
  if (!Array.isArray(mod.params)) {
    throw new Error("Filter 'params' must be an array");
  }
  if (typeof mod.apply !== "function") {
    throw new Error("Filter must export an 'apply' function");
  }
}

function loadFile(filepath, builtin) {
  try {
    // Clear require cache so hot-reload works
    const resolved = require.resolve(filepath);
    delete require.cache[resolved];
    const mod = require(filepath);
    validateFilterModule(mod, filepath);
    registry.set(mod.id, {
      id: mod.id,
      label: mod.label,
      description: mod.description || "",
      params: mod.params,
      builtin,
      filepath,
      apply: mod.apply,
    });
    return true;
  } catch (err) {
    console.error(`[filters] Failed to load ${filepath}: ${err.message}`);
    return false;
  }
}

function loadDirectory(dir, builtin) {
  if (!fs.existsSync(dir)) return;
  for (const file of fs.readdirSync(dir)) {
    if (file.endsWith(".js")) {
      loadFile(path.join(dir, file), builtin);
    }
  }
}

function loadAll() {
  registry.clear();
  loadDirectory(BUILTIN_DIR, true);
  loadDirectory(CUSTOM_DIR, false);
}

// Initial load on require
loadAll();

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Returns metadata for all loaded filters (no apply function).
 */
function getAll() {
  return Array.from(registry.values()).map(
    ({ apply: _apply, filepath: _fp, ...meta }) => meta,
  );
}

/**
 * Returns the full entry (including apply) for a filter by id, or undefined.
 */
function getFilter(id) {
  return registry.get(id);
}

/**
 * Reload all filters from disk (built-in + custom).
 */
function reload() {
  loadAll();
}

/**
 * Upload and register a new custom filter.
 * @param {string} filename  - Desired filename (e.g. "myfilter.js")
 * @param {string} code      - JS source code of the filter module
 * @returns {{ id, label, params }} metadata of the newly loaded filter
 */
function uploadFilter(filename, code) {
  if (!/^[a-zA-Z0-9_-]+\.js$/.test(filename)) {
    throw new Error(
      "Filename must be alphanumeric with underscores/hyphens and end in .js",
    );
  }
  if (typeof code !== "string" || code.trim().length === 0) {
    throw new Error("Filter code must be a non-empty string");
  }

  fs.mkdirSync(CUSTOM_DIR, { recursive: true });
  const filepath = path.join(CUSTOM_DIR, filename);
  fs.writeFileSync(filepath, code, "utf8");

  const ok = loadFile(filepath, false);
  if (!ok) {
    // Remove the file if it failed validation
    try { fs.unlinkSync(filepath); } catch (_) {}
    throw new Error("Filter file failed validation — check server logs for details");
  }

  const entry = registry.get(
    // find by filepath since we don't know the id yet
    [...registry.values()].find((e) => e.filepath === filepath)?.id,
  );
  return entry
    ? { id: entry.id, label: entry.label, params: entry.params }
    : null;
}

/**
 * Delete a custom (non-built-in) filter by id.
 */
function deleteFilter(id) {
  const entry = registry.get(id);
  if (!entry) throw new Error(`Filter '${id}' not found`);
  if (entry.builtin) throw new Error(`Cannot delete built-in filter '${id}'`);

  try {
    fs.unlinkSync(entry.filepath);
  } catch (err) {
    throw new Error(`Failed to delete filter file: ${err.message}`);
  }

  try {
    const resolved = require.resolve(entry.filepath);
    delete require.cache[resolved];
  } catch (_) {}

  registry.delete(id);
}

module.exports = { getAll, getFilter, reload, uploadFilter, deleteFilter };
