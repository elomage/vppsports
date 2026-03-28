const { ObjectId } = require("mongodb");

const { connectDB, getCollection } = require("../config/db");

const normalizeContextId = (value) => {
  if (!value) return null;

  if (value instanceof ObjectId) {
    return value;
  }

  const rawValue =
    typeof value === "object" && value !== null && "_id" in value
      ? value._id
      : typeof value === "object" && value !== null && "id" in value
        ? value.id
      : value;

  if (!ObjectId.isValid(rawValue)) {
    return null;
  }

  return new ObjectId(rawValue);
};

const normalizeContextIds = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }

  const seen = new Set();
  const normalized = [];

  value.forEach((entry) => {
    const objectId = normalizeContextId(entry);
    if (!objectId) {
      return;
    }

    const key = objectId.toString();
    if (seen.has(key)) {
      return;
    }

    seen.add(key);
    normalized.push(objectId);
  });

  return normalized;
};

const loadContextsByIds = async (contextIds) => {
  const normalizedIds = normalizeContextIds(contextIds);
  if (normalizedIds.length === 0) {
    return [];
  }

  const db = await connectDB();
  const contextsColl = await getCollection(db, "contexts");
  const contexts = await contextsColl
    .find(
      { _id: { $in: normalizedIds } },
      { projection: { _id: 1, name: 1, deletedAt: 1 } }
    )
    .toArray();

  const byId = new Map(
    contexts.map((context) => [
      String(context._id),
      {
        id: String(context._id),
        name: String(context.name || "").trim().toLowerCase(),
        deletedAt: context.deletedAt || null,
      },
    ])
  );

  return normalizedIds
    .map((id) => byId.get(String(id)))
    .filter(Boolean);
};

const loadContextsByNames = async (contextNames) => {
  const normalizedNames = [...new Set(
    (Array.isArray(contextNames) ? contextNames : [])
      .map((entry) => String(entry || "").trim().toLowerCase())
      .filter(Boolean)
  )];
  if (normalizedNames.length === 0) {
    return [];
  }

  const db = await connectDB();
  const contextsColl = await getCollection(db, "contexts");
  const contexts = await contextsColl
    .find(
      { name: { $in: normalizedNames } },
      { projection: { _id: 1, name: 1, deletedAt: 1 } }
    )
    .toArray();

  const byName = new Map(
    contexts.map((context) => [
      String(context.name || "").trim().toLowerCase(),
      {
        id: String(context._id),
        name: String(context.name || "").trim().toLowerCase(),
        deletedAt: context.deletedAt || null,
      },
    ])
  );

  return normalizedNames.map((name) => byName.get(name)).filter(Boolean);
};

const serializeUser = async (user) => {
  const contexts =
    Array.isArray(user?.contexts) && user.contexts.length > 0
      ? await loadContextsByIds(user.contexts)
      : await loadContextsByNames(
          Array.isArray(user?.contextRoles)
            ? user.contextRoles.map((entry) => entry?.context)
            : []
        );

  return {
    id: String(user._id),
    username: user.username,
    role: user.role,
    contexts,
    isActive: user.isActive,
    createdAt: user.createdAt || null,
    updatedAt: user.updatedAt || null,
    deletedAt: user.deletedAt || null,
    restoredAt: user.restoredAt || null,
  };
};

module.exports = {
  loadContextsByIds,
  loadContextsByNames,
  normalizeContextId,
  normalizeContextIds,
  serializeUser,
};
