import { useEffect, useMemo, useState } from "react";
import {
  createContext,
  createUser,
  deleteRun,
  fetchDeletedContexts,
  fetchContexts,
  removeContext,
  restoreContext,
  updateContext,
} from "./api";

const emptyContextRole = { context: "", role: "user" };

const normalizeContext = (value) =>
  String(value || "")
    .trim()
    .toLowerCase();

const AdminPanel = ({ runs, onRunDeleted, onUserCreated }) => {
  const [selectedRunId, setSelectedRunId] = useState("");
  const [deleteStatus, setDeleteStatus] = useState({
    type: "idle",
    message: "",
  });
  const [isDeleting, setIsDeleting] = useState(false);
  const [newContext, setNewContext] = useState("");
  const [storedContexts, setStoredContexts] = useState([]);
  const [deletedContexts, setDeletedContexts] = useState([]);
  const [contextStatus, setContextStatus] = useState({
    type: "idle",
    message: "",
  });
  const [isLoadingContexts, setIsLoadingContexts] = useState(false);
  const [form, setForm] = useState({
    username: "",
    password: "",
    role: "user",
    contextRoles: [{ ...emptyContextRole }],
  });
  const [isCreating, setIsCreating] = useState(false);
  const [createStatus, setCreateStatus] = useState({
    type: "idle",
    message: "",
  });

  const sortedRuns = useMemo(
    () =>
      [...(Array.isArray(runs) ? runs : [])].sort((a, b) =>
        String(a.name || "").localeCompare(String(b.name || "")),
      ),
    [runs],
  );

  const availableContexts = useMemo(
    () => [...new Set(storedContexts)].sort((a, b) => a.localeCompare(b)),
    [storedContexts],
  );

  const loadContexts = async () => {
    setIsLoadingContexts(true);
    try {
      const [contexts, deleted] = await Promise.all([
        fetchContexts(),
        fetchDeletedContexts(),
      ]);
      setStoredContexts(
        Array.isArray(contexts)
          ? contexts.map((entry) => normalizeContext(entry?.name)).filter(Boolean)
          : [],
      );
      setDeletedContexts(
        Array.isArray(deleted)
          ? deleted.map((entry) => normalizeContext(entry?.name)).filter(Boolean)
          : [],
      );
    } catch (error) {
      setContextStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to load contexts.",
      });
    } finally {
      setIsLoadingContexts(false);
    }
  };

  useEffect(() => {
    loadContexts();
  }, []);

  const updateContextRole = (index, field, value) => {
    setForm((current) => ({
      ...current,
      contextRoles: current.contextRoles.map((entry, entryIndex) =>
        entryIndex === index ? { ...entry, [field]: value } : entry,
      ),
    }));
  };

  const addContextRole = () => {
    setForm((current) => ({
      ...current,
      contextRoles: [...current.contextRoles, { ...emptyContextRole }],
    }));
  };

  const removeContextRole = (index) => {
    setForm((current) => ({
      ...current,
      contextRoles:
        current.contextRoles.length > 1
          ? current.contextRoles.filter((_, entryIndex) => entryIndex !== index)
          : [{ ...emptyContextRole }],
    }));
  };

  const handleAddContext = () => {
    const normalized = normalizeContext(newContext);
    if (!normalized) {
      setContextStatus({ type: "error", message: "Enter a context name." });
      return;
    }

    if (availableContexts.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "Context already exists in the list.",
      });
      return;
    }

    if (deletedContexts.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "A deleted context with this name exists. Restore it instead.",
      });
      return;
    }

    const saveContext = async () => {
      try {
        const response = await createContext(normalized);
        const createdName = normalizeContext(
          response?.context?.name || normalized,
        );
        setStoredContexts((current) =>
          [...new Set([...current, createdName])].sort((a, b) =>
            a.localeCompare(b),
          ),
        );
        setDeletedContexts((current) =>
          current.filter((entry) => entry !== createdName),
        );
        setNewContext("");
        setContextStatus({
          type: "success",
          message: `Context '${createdName}' added.`,
        });
      } catch (error) {
        setContextStatus({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Failed to create context.",
        });
      }
    };

    saveContext();
  };

  const handleEditContext = (context) => {
    const newName = window.prompt("Enter new name for context", context);
    const normalized = normalizeContext(newName);
    if (!normalized) {
      setContextStatus({ type: "error", message: "Context name cannot be empty." });
      return;
    }
    if (normalized === context) {
      setContextStatus({ type: "info", message: "Context name is unchanged." });
      return;
    }
    if (availableContexts.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "Another context with this name already exists.",
      });
      return;
    }
    if (deletedContexts.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "A deleted context with this name already exists.",
      });
      return;
    }

    const saveContext = async () => {
      try {
        const response = await updateContext(context, normalized);
        const updatedName = normalizeContext(
          response?.context?.name || normalized,
        );
        setStoredContexts((current) =>
          current
            .map((entry) => (entry === context ? updatedName : entry))
            .filter(Boolean)
            .filter((entry, index, array) => array.indexOf(entry) === index)
            .sort((a, b) => a.localeCompare(b)),
        );
        setForm((current) => ({
          ...current,
          contextRoles: current.contextRoles.map((entry) => ({
            ...entry,
            context: entry.context === context ? updatedName : entry.context,
          })),
        }));
        setContextStatus({
          type: "success",
          message: `Context '${context}' renamed to '${updatedName}'.`,
        });
      } catch (error) {
        setContextStatus({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to update context.",
        });
      }
    };

    saveContext();
  };

  const handleRemoveContext = (context) => {
    const confirmed = window.confirm(
      `Remove context '${context}' from the available context list?`,
    );
    if (!confirmed) return;

    const deleteContext = async () => {
      try {
        await removeContext(context);
        setStoredContexts((current) => current.filter((entry) => entry !== context));
        setDeletedContexts((current) =>
          [...new Set([...current, context])].sort((a, b) => a.localeCompare(b)),
        );
        setForm((current) => ({
          ...current,
          contextRoles: current.contextRoles.map((entry) => ({
            ...entry,
            context: entry.context === context ? "" : entry.context,
          })),
        }));
        setContextStatus({
          type: "success",
          message: `Context '${context}' removed.`,
        });
      } catch (error) {
        setContextStatus({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to remove context.",
        });
      }
    };

    deleteContext();
  };

  const handleRestoreContext = (context) => {
    const restoreDeletedContext = async () => {
      try {
        await restoreContext(context);
        setDeletedContexts((current) => current.filter((entry) => entry !== context));
        setStoredContexts((current) =>
          [...new Set([...current, context])].sort((a, b) => a.localeCompare(b)),
        );
        setContextStatus({
          type: "success",
          message: `Context '${context}' restored.`,
        });
      } catch (error) {
        setContextStatus({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to restore context.",
        });
      }
    };

    restoreDeletedContext();
  };


  const handleDelete = async () => {
    if (!selectedRunId || isDeleting) return;
    const selectedRun = sortedRuns.find((run) => run._id === selectedRunId);
    const confirmed = window.confirm(
      `Delete ${selectedRun?.name || `Run ${selectedRunId}`} and all related sensor readings?`,
    );
    if (!confirmed) return;

    setIsDeleting(true);
    setDeleteStatus({ type: "info", message: "Deleting run..." });

    try {
      await deleteRun(selectedRunId);
      setDeleteStatus({
        type: "success",
        message: "Run deleted successfully.",
      });
      setSelectedRunId("");
      onRunDeleted?.(selectedRunId);
    } catch (error) {
      setDeleteStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to delete run.",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCreateUser = async (event) => {
    event.preventDefault();
    if (isCreating) return;

    setIsCreating(true);
    setCreateStatus({ type: "info", message: "Creating user..." });

    try {
      const contextRoles = form.contextRoles
        .map((entry) => ({
          context: normalizeContext(entry.context),
          role: entry.role,
        }))
        .filter((entry) => entry.context);

      const response = await createUser({
        username: form.username.trim(),
        password: form.password,
        role: form.role,
        contextRoles,
      });

      setCreateStatus({
        type: "success",
        message: "User created successfully.",
      });
      setForm({
        username: "",
        password: "",
        role: "user",
        contextRoles: [{ ...emptyContextRole }],
      });
      onUserCreated?.(response.user);
    } catch (error) {
      setCreateStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to create user.",
      });
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="upload-view row">
      <div className="upload-card col m-2">
        <h3>Run management</h3>

        <div className="upload-form">
          <label htmlFor="admin-delete-run">Delete run</label>
          <select
            id="admin-delete-run"
            className="form-control"
            value={selectedRunId}
            onChange={(event) => setSelectedRunId(event.target.value)}
            disabled={isDeleting}
          >
            <option value="">Select run to delete</option>
            {sortedRuns.map((run) => (
              <option key={run._id} value={run._id}>
                {run.name || `Run ${run._id}`}
                {run.context ? ` (${run.context})` : ""}
              </option>
            ))}
          </select>
          <div className="upload-actions">
            <button
              className="btn btn-outline-danger"
              type="button"
              onClick={handleDelete}
              disabled={!selectedRunId || isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete run"}
            </button>
          </div>
          {deleteStatus.message && (
            <div
              className={`upload-status ${deleteStatus.type !== "idle" ? `is-${deleteStatus.type}` : ""}`}
            >
              {deleteStatus.message}
            </div>
          )}
        </div>
      </div>
      <div className="upload-card col m-2">
        <h3>Context management</h3>
        <div>
          <strong>Add new context</strong>
        </div>
        <div className="upload-actions">
          <input
            className="form-control"
            type="text"
            placeholder="Enter context name"
            value={newContext}
            onChange={(event) => {
              setNewContext(event.target.value);
              setContextStatus({ type: "idle", message: "" });
            }}
            disabled={isCreating}
          />
          <button
            className="btn btn-outline-primary btn-sm"
            type="button"
            onClick={handleAddContext}
            disabled={isCreating}
          >
            Add context
          </button>
        </div>
        {contextStatus.message && (
          <div
            className={`upload-status ${contextStatus.type !== "idle" ? `is-${contextStatus.type}` : ""}`}
          >
            {contextStatus.message}
          </div>
        )}
        {availableContexts.length > 0 && (
          <>
          <div>
            <strong>Available contexts</strong>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {availableContexts.map((context) => (
                <tr key={context}>
                  <td>{context}</td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm me-2"
                      type="button"
                      onClick={() => handleEditContext(context)}
                      disabled={isCreating}
                    >
                      Edit
                    </button>
                    <button
                      className="btn btn-outline-danger btn-sm"
                      type="button"
                      onClick={() => handleRemoveContext(context)}
                      disabled={isCreating}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </>
        )}
        {deletedContexts.length > 0 && (
          <>
          <div>
            <strong>Deleted contexts</strong>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {deletedContexts.map((context) => (
                <tr key={context}>
                  <td>{context}</td>
                  <td>
                    <button
                      className="btn btn-outline-secondary btn-sm"
                      type="button"
                      onClick={() => handleRestoreContext(context)}
                      disabled={isCreating}
                    >
                      Restore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </>
        )}
        {isLoadingContexts && (
          <div className="upload-file-meta">Loading contexts...</div>
        )}
      </div>
      <div className="upload-card col m-2">
        <form className="upload-form" onSubmit={handleCreateUser}>
          <h3>User management</h3>

          <input
            className="form-control"
            type="text"
            placeholder="Username"
            value={form.username}
            minLength={3}
            maxLength={64}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                username: event.target.value,
              }))
            }
            required
            disabled={isCreating}
          />
          <input
            className="form-control"
            type="password"
            placeholder="Password"
            value={form.password}
            minLength={12}
            maxLength={128}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                password: event.target.value,
              }))
            }
            required
            disabled={isCreating}
          />
          <select
            className="form-control"
            value={form.role}
            onChange={(event) =>
              setForm((current) => ({ ...current, role: event.target.value }))
            }
            disabled={isCreating}
          >
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>

          {form.contextRoles.map((entry, index) => (
            <div
              key={`${index}-${entry.context}-${entry.role}`}
              className="upload-actions"
            >
              <select
                className="form-control"
                value={entry.context}
                onChange={(event) =>
                  updateContextRole(index, "context", event.target.value)
                }
                disabled={isCreating}
              >
                <option value="">Select context</option>
                {availableContexts.map((context) => (
                  <option key={context} value={context}>
                    {context}
                  </option>
                ))}
              </select>

              {index !== 0 && (
                <button
                  className="btn btn-outline-danger btn-sm"
                  type="button"
                  onClick={() => removeContextRole(index)}
                  disabled={isCreating}
                >
                  Remove
                </button>
              )}
            </div>
          ))}

          <div className="upload-actions">
            <button
              className="btn btn-outline-secondary btn-sm"
              type="button"
              onClick={addContextRole}
              disabled={isCreating}
            >
              Add context role
            </button>
          </div>
          <div className="upload-actions">
            <button
              className="btn btn-primary"
              type="submit"
              disabled={isCreating || availableContexts.length === 0}
            >
              {isCreating ? "Creating..." : "Create user"}
            </button>
          </div>
          {createStatus.message && (
            <div
              className={`upload-status ${createStatus.type !== "idle" ? `is-${createStatus.type}` : ""}`}
            >
              {createStatus.message}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};

export default AdminPanel;
