import { useEffect, useMemo, useRef, useState } from "react";
import {
  createContext,
  createUser,
  deleteFilter,
  deleteRun,
  exportMultiRunCsv,
  fetchContexts,
  fetchDeletedContexts,
  fetchDeletedUsers,
  fetchFilters,
  fetchPluginAssignments,
  fetchUsers,
  removeContext,
  removeUser,
  resetPluginAssignments,
  restoreContext,
  restoreUser,
  updateContext,
  updatePluginAssignments,
  updateUser,
  uploadFilter,
} from "./api";
import MultiRunExport from "./MultiRunExport";

const normalizeContext = (value) =>
  String(value || "")
    .trim()
    .toLowerCase();

const normalizeUsername = (value) =>
  String(value || "")
    .trim()
    .toLowerCase();

const sortContextsByName = (contexts) =>
  [...contexts].sort((a, b) =>
    String(a?.name || "").localeCompare(String(b?.name || "")),
  );

const formatContexts = (contexts) => {
  if (!Array.isArray(contexts) || contexts.length === 0) {
    return "None";
  }

  return contexts.map((context) => context.name).join(", ");
};

const createEmptyUserForm = () => ({
  username: "",
  password: "",
  role: "user",
  contextIds: [],
});


const AdminPanel = ({ runs, onRunDeleted, onUserCreated }) => {
  const [selectedRunId, setSelectedRunId] = useState("");
  const [deleteStatus, setDeleteStatus] = useState({
    type: "idle",
    message: "",
  });
  const [isDeleting, setIsDeleting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [newContext, setNewContext] = useState("");
  const [storedContexts, setStoredContexts] = useState([]);
  const [deletedContexts, setDeletedContexts] = useState([]);
  const [contextStatus, setContextStatus] = useState({
    type: "idle",
    message: "",
  });
  const [isLoadingContexts, setIsLoadingContexts] = useState(false);
  const [form, setForm] = useState(createEmptyUserForm);
  const [editingUsername, setEditingUsername] = useState("");
  const [storedUsers, setStoredUsers] = useState([]);
  const [deletedUsers, setDeletedUsers] = useState([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [userStatus, setUserStatus] = useState({ type: "idle", message: "" });

  const [filters, setFilters] = useState([]);
  const [isLoadingFilters, setIsLoadingFilters] = useState(false);
  const [filterStatus, setFilterStatus] = useState({
    type: "idle",
    message: "",
  });
  const [isUploadingFilter, setIsUploadingFilter] = useState(false);
  const [pendingFilterFile, setPendingFilterFile] = useState(null);
  const filterFileInputRef = useRef(null);

  const [pluginContextId, setPluginContextId] = useState("");
  const [pluginType, setPluginType] = useState("visualization");
  const [pluginList, setPluginList] = useState([]);
  const [isLoadingPlugins, setIsLoadingPlugins] = useState(false);
  const [isSavingPlugins, setIsSavingPlugins] = useState(false);
  const [pluginStatus, setPluginStatus] = useState({
    type: "idle",
    message: "",
  });
  const [pluginHasContextConfig, setPluginHasContextConfig] = useState(false);


  const sortedRuns = useMemo(
    () =>
      [...(Array.isArray(runs) ? runs : [])].sort((a, b) =>
        String(a.name || "").localeCompare(String(b.name || "")),
      ),
    [runs],
  );

  const availableContexts = useMemo(
    () =>
      sortContextsByName(Array.isArray(storedContexts) ? storedContexts : []),
    [storedContexts],
  );

  const removedContexts = useMemo(
    () =>
      sortContextsByName(Array.isArray(deletedContexts) ? deletedContexts : []),
    [deletedContexts],
  );

  const activeContextNames = useMemo(
    () => availableContexts.map((context) => context.name),
    [availableContexts],
  );

  const deletedContextNames = useMemo(
    () => removedContexts.map((context) => context.name),
    [removedContexts],
  );

  const isEditingUser = Boolean(editingUsername);

  const loadContexts = async () => {
    setIsLoadingContexts(true);
    try {
      const [contexts, deleted] = await Promise.all([
        fetchContexts(),
        fetchDeletedContexts(),
      ]);
      setStoredContexts(
        Array.isArray(contexts) ? sortContextsByName(contexts) : [],
      );
      setDeletedContexts(
        Array.isArray(deleted) ? sortContextsByName(deleted) : [],
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

  const loadUsers = async () => {
    setIsLoadingUsers(true);
    try {
      const [activeUsers, removedUsers] = await Promise.all([
        fetchUsers(),
        fetchDeletedUsers(),
      ]);
      setStoredUsers(Array.isArray(activeUsers) ? activeUsers : []);
      setDeletedUsers(Array.isArray(removedUsers) ? removedUsers : []);
    } catch (error) {
      setUserStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to load users.",
      });
    } finally {
      setIsLoadingUsers(false);
    }
  };

  const loadFilters = async () => {
    setIsLoadingFilters(true);
    try {
      const data = await fetchFilters();
      setFilters(Array.isArray(data) ? data : []);
    } catch (error) {
      setFilterStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to load filters.",
      });
    } finally {
      setIsLoadingFilters(false);
    }
  };

  const loadPlugins = async () => {
    setIsLoadingPlugins(true);
    setPluginStatus({ type: "idle", message: "" });
    try {
      const data = await fetchPluginAssignments(
        pluginContextId || null,
        pluginType,
      );
      setPluginList(Array.isArray(data?.plugins) ? data.plugins : []);
      setPluginHasContextConfig(Boolean(data?.hasContextConfig));
    } catch (error) {
      setPluginStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to load plugins.",
      });
    } finally {
      setIsLoadingPlugins(false);
    }
  };

  useEffect(() => {
    loadContexts();
    loadUsers();
    loadFilters();
  }, []);

  useEffect(() => {
    loadPlugins();
  }, [pluginContextId, pluginType]);

  const toggleContextSelection = (contextId, checked) => {
    setForm((current) => {
      const hasContext = current.contextIds.includes(contextId);

      if (checked && !hasContext) {
        return {
          ...current,
          contextIds: [...current.contextIds, contextId],
        };
      }

      if (!checked && hasContext) {
        return {
          ...current,
          contextIds: current.contextIds.filter((entry) => entry !== contextId),
        };
      }

      return current;
    });
  };

  const resetUserForm = () => {
    setForm(createEmptyUserForm());
    setEditingUsername("");
  };

  const populateUserForm = (user) => {
    setEditingUsername(normalizeUsername(user?.username));
    setForm({
      username: user?.username || "",
      password: "",
      role: user?.role || "user",
      contextIds: Array.isArray(user?.contexts)
        ? user.contexts.map((context) => context.id).filter(Boolean)
        : [],
    });
    setUserStatus({
      type: "info",
      message: `Editing user '${user.username}'.`,
    });
  };

  const handleAddContext = () => {
    const normalized = normalizeContext(newContext);
    if (!normalized) {
      setContextStatus({ type: "error", message: "Enter a context name." });
      return;
    }

    if (activeContextNames.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "Context already exists in the list.",
      });
      return;
    }

    if (deletedContextNames.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "A deleted context with this name exists. Restore it instead.",
      });
      return;
    }

    const saveContext = async () => {
      try {
        const response = await createContext(normalized);
        const createdContext = response?.context || null;
        if (createdContext) {
          setStoredContexts((current) =>
            sortContextsByName([...current, createdContext]),
          );
        }
        setDeletedContexts((current) =>
          current.filter((entry) => entry.id !== createdContext?.id),
        );
        setNewContext("");
        setContextStatus({
          type: "success",
          message: `Context '${normalizeContext(createdContext?.name || normalized)}' added.`,
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
    const newName = window.prompt("Enter new name for context", context.name);
    const normalized = normalizeContext(newName);
    if (!normalized) {
      setContextStatus({
        type: "error",
        message: "Context name cannot be empty.",
      });
      return;
    }
    if (normalized === context.name) {
      setContextStatus({ type: "info", message: "Context name is unchanged." });
      return;
    }
    if (activeContextNames.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "Another context with this name already exists.",
      });
      return;
    }
    if (deletedContextNames.includes(normalized)) {
      setContextStatus({
        type: "error",
        message: "A deleted context with this name already exists.",
      });
      return;
    }

    const saveContext = async () => {
      try {
        const response = await updateContext(context.name, normalized);
        const updatedContext = response?.context || {
          ...context,
          name: normalized,
        };
        setStoredContexts((current) =>
          sortContextsByName(
            current.map((entry) =>
              entry.id === updatedContext.id ? updatedContext : entry,
            ),
          ),
        );
        await loadUsers();
        setContextStatus({
          type: "success",
          message: `Context '${context.name}' renamed to '${updatedContext.name}'.`,
        });
      } catch (error) {
        setContextStatus({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Failed to update context.",
        });
      }
    };

    saveContext();
  };

  const handleRemoveContext = (context) => {
    const confirmed = window.confirm(
      `Remove context '${context.name}' from the available context list?`,
    );
    if (!confirmed) return;

    const deleteContextRecord = async () => {
      try {
        await removeContext(context.name);
        setStoredContexts((current) =>
          current.filter((entry) => entry.id !== context.id),
        );
        setDeletedContexts((current) =>
          sortContextsByName([...current, context]),
        );
        setForm((current) => ({
          ...current,
          contextIds: current.contextIds.filter(
            (entry) => entry !== context.id,
          ),
        }));
        await loadUsers();
        setContextStatus({
          type: "success",
          message: `Context '${context.name}' removed.`,
        });
      } catch (error) {
        setContextStatus({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Failed to remove context.",
        });
      }
    };

    deleteContextRecord();
  };

  const handleRestoreContext = (context) => {
    const restoreDeletedContext = async () => {
      try {
        await restoreContext(context.name);
        setDeletedContexts((current) =>
          current.filter((entry) => entry.id !== context.id),
        );
        setStoredContexts((current) =>
          sortContextsByName([...current, context]),
        );
        setContextStatus({
          type: "success",
          message: `Context '${context.name}' restored.`,
        });
      } catch (error) {
        setContextStatus({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Failed to restore context.",
        });
      }
    };

    restoreDeletedContext();
  };

  const togglePlugin = (id) => {
    setPluginList((prev) =>
      prev.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p)),
    );
  };

  const movePlugin = (id, direction) => {
    setPluginList((prev) => {
      const idx = prev.findIndex((p) => p.id === id);
      if (idx < 0) return prev;
      const next = [...prev];
      const swapIdx = idx + direction;
      if (swapIdx < 0 || swapIdx >= next.length) return prev;
      [next[idx], next[swapIdx]] = [next[swapIdx], next[idx]];
      return next;
    });
  };

  const handleSavePlugins = async () => {
    if (isSavingPlugins) return;
    setIsSavingPlugins(true);
    setPluginStatus({ type: "info", message: "Saving..." });
    try {
      const assignments = pluginList.map((p, idx) => ({
        pluginId: p.id,
        enabled: p.enabled,
        order: idx,
      }));
      await updatePluginAssignments(
        pluginContextId || null,
        pluginType,
        assignments,
      );
      setPluginStatus({
        type: "success",
        message: "Plugin assignments saved.",
      });
      setPluginHasContextConfig(true);
    } catch (error) {
      setPluginStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to save plugins.",
      });
    } finally {
      setIsSavingPlugins(false);
    }
  };

  const handleResetPlugins = async () => {
    if (!pluginContextId) return;
    const confirmed = window.confirm(
      "Reset this context's plugin config to global defaults?",
    );
    if (!confirmed) return;
    try {
      await resetPluginAssignments(pluginContextId, pluginType);
      setPluginStatus({
        type: "success",
        message: "Reset to global defaults.",
      });
      setPluginHasContextConfig(false);
      await loadPlugins();
    } catch (error) {
      setPluginStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to reset.",
      });
    }
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

  const handleFilterFileChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      setPendingFilterFile(null);
      return;
    }
    if (!file.name.endsWith(".js")) {
      setFilterStatus({
        type: "error",
        message: "Only .js files are allowed.",
      });
      setPendingFilterFile(null);
      if (filterFileInputRef.current) filterFileInputRef.current.value = "";
      return;
    }
    setPendingFilterFile(file);
    setFilterStatus({ type: "idle", message: "" });
  };

  const handleFilterUpload = async () => {
    if (!pendingFilterFile) return;

    setIsUploadingFilter(true);
    setFilterStatus({
      type: "info",
      message: `Uploading ${pendingFilterFile.name}…`,
    });

    try {
      const code = await pendingFilterFile.text();
      const result = await uploadFilter(pendingFilterFile.name, code);
      setFilterStatus({
        type: "success",
        message: `Filter '${result?.filter?.label || pendingFilterFile.name}' uploaded successfully.`,
      });
      setPendingFilterFile(null);
      if (filterFileInputRef.current) filterFileInputRef.current.value = "";
      await loadFilters();
    } catch (error) {
      setFilterStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to upload filter.",
      });
    } finally {
      setIsUploadingFilter(false);
    }
  };

  const handleFilterDelete = (filter) => {
    const confirmed = window.confirm(
      `Delete custom filter '${filter.label}'? This cannot be undone.`,
    );
    if (!confirmed) return;

    const doDelete = async () => {
      try {
        await deleteFilter(filter.id);
        setFilterStatus({
          type: "success",
          message: `Filter '${filter.label}' deleted.`,
        });
        await loadFilters();
      } catch (error) {
        setFilterStatus({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to delete filter.",
        });
      }
    };

    doDelete();
  };

  const handleExportCsv = async () => {
    if (!selectedRunId || isExporting) return;

    setIsExporting(true);
    setDeleteStatus({ type: "info", message: "Preparing CSV export..." });

    try {
      const { blob, fileName } = await exportMultiRunCsv([selectedRunId]);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setDeleteStatus({ type: "success", message: "CSV export downloaded." });
    } catch (error) {
      setDeleteStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to export run.",
      });
    } finally {
      setIsExporting(false);
    }
  };

  const handleSaveUser = async (event) => {
    event.preventDefault();
    if (isSavingUser) return;

    setIsSavingUser(true);
    setUserStatus({
      type: "info",
      message: isEditingUser ? "Updating user..." : "Creating user...",
    });

    try {
      const payload = {
        username: normalizeUsername(form.username),
        role: form.role,
        contextIds: form.contextIds,
      };

      if (form.password) {
        payload.password = form.password;
      }

      const response = isEditingUser
        ? await updateUser(editingUsername, payload)
        : await createUser(payload);

      setUserStatus({
        type: "success",
        message: isEditingUser
          ? `User '${payload.username}' updated successfully.`
          : "User created successfully.",
      });
      resetUserForm();
      await loadUsers();
      onUserCreated?.(response?.user);
    } catch (error) {
      setUserStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to save user.",
      });
    } finally {
      setIsSavingUser(false);
    }
  };

  const handleRemoveUser = (username) => {
    const confirmed = window.confirm(`Remove user '${username}'?`);
    if (!confirmed) return;

    const deleteUserRecord = async () => {
      try {
        await removeUser(username);
        await loadUsers();
        if (editingUsername === username) {
          resetUserForm();
        }
        setUserStatus({
          type: "success",
          message: `User '${username}' removed.`,
        });
      } catch (error) {
        setUserStatus({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to remove user.",
        });
      }
    };

    deleteUserRecord();
  };

  const handleRestoreUser = (username) => {
    const restoreDeletedUser = async () => {
      try {
        await restoreUser(username);
        await loadUsers();
        setUserStatus({
          type: "success",
          message: `User '${username}' restored.`,
        });
      } catch (error) {
        setUserStatus({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to restore user.",
        });
      }
    };

    restoreDeletedUser();
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
            disabled={isDeleting || isExporting}
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
              disabled={!selectedRunId || isDeleting || isExporting}
            >
              {isDeleting ? "Deleting..." : "Delete run"}
            </button>
            <button
              className="btn btn-outline-primary"
              type="button"
              onClick={handleExportCsv}
              disabled={!selectedRunId || isDeleting || isExporting}
            >
              {isExporting ? "Exporting..." : "Export CSV"}
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

      <MultiRunExport runs={sortedRuns} />

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
            disabled={isSavingUser}
          />
          <button
            className="btn btn-outline-primary btn-sm"
            type="button"
            onClick={handleAddContext}
            disabled={isSavingUser}
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
                  <tr key={context.id}>
                    <td>{context.name}</td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm me-2"
                        type="button"
                        onClick={() => handleEditContext(context)}
                        disabled={isSavingUser}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-outline-danger btn-sm"
                        type="button"
                        onClick={() => handleRemoveContext(context)}
                        disabled={isSavingUser}
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
        {removedContexts.length > 0 && (
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
                {removedContexts.map((context) => (
                  <tr key={context.id}>
                    <td>{context.name}</td>
                    <td>
                      <button
                        className="btn btn-outline-secondary btn-sm"
                        type="button"
                        onClick={() => handleRestoreContext(context)}
                        disabled={isSavingUser}
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
        <form className="upload-form" onSubmit={handleSaveUser}>
          <h3>User management</h3>
          {isEditingUser && (
            <div
              className={`upload-status ${userStatus.type !== "idle" ? `is-${userStatus.type}` : ""}`}
            >
              {userStatus.message}
            </div>
          )}
          <div>
            <strong>{isEditingUser ? "Edit user" : "Create user"}</strong>
          </div>

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
            disabled={isSavingUser}
          />
          <input
            className="form-control"
            type="password"
            placeholder={
              isEditingUser
                ? "New password (leave blank to keep current)"
                : "Password"
            }
            value={form.password}
            minLength={isEditingUser ? 0 : 12}
            maxLength={128}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                password: event.target.value,
              }))
            }
            required={!isEditingUser}
            disabled={isSavingUser}
          />
          <select
            className="form-control"
            value={form.role}
            onChange={(event) =>
              setForm((current) => ({ ...current, role: event.target.value }))
            }
            disabled={isSavingUser}
          >
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>

          <div>
            <strong>Contexts</strong>
          </div>
          {availableContexts.map((context) => (
            <label
              key={context.id}
              className="form-control d-flex align-items-center gap-2"
            >
              <input
                type="checkbox"
                checked={form.contextIds.includes(context.id)}
                onChange={(event) =>
                  toggleContextSelection(context.id, event.target.checked)
                }
                disabled={isSavingUser}
              />
              <span>{context.name}</span>
            </label>
          ))}

          <div className="upload-actions">
            <button
              className="btn btn-primary"
              type="submit"
              disabled={isSavingUser || availableContexts.length === 0}
            >
              {isSavingUser
                ? isEditingUser
                  ? "Saving..."
                  : "Creating..."
                : isEditingUser
                  ? "Save user"
                  : "Create user"}
            </button>
            {isEditingUser && (
              <>
                <button
                  className="btn btn-outline-secondary btn-sm"
                  type="button"
                  onClick={resetUserForm}
                  disabled={isSavingUser}
                >
                  Cancel edit
                </button>
              </>
            )}
          </div>
        </form>

        {storedUsers.length > 0 && (
          <div className="mt-2">
            <div>
              <strong>Active users</strong>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Contexts</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {storedUsers.map((user) => (
                  <tr key={user.id || user.username}>
                    <td>{user.username}</td>
                    <td>{user.role}</td>
                    <td>{formatContexts(user.contexts)}</td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm me-2"
                        type="button"
                        onClick={() => populateUserForm(user)}
                        disabled={isSavingUser}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-outline-danger btn-sm"
                        type="button"
                        onClick={() => handleRemoveUser(user.username)}
                        disabled={isSavingUser}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {deletedUsers.length > 0 && (
          <>
            <div>
              <strong>Deleted users</strong>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Contexts</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {deletedUsers.map((user) => (
                  <tr key={user.id || user.username}>
                    <td>{user.username}</td>
                    <td>{user.role}</td>
                    <td>{formatContexts(user.contexts)}</td>
                    <td>
                      <button
                        className="btn btn-outline-secondary btn-sm"
                        type="button"
                        onClick={() => handleRestoreUser(user.username)}
                        disabled={isSavingUser}
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

        {isLoadingUsers && (
          <div className="upload-file-meta">Loading users...</div>
        )}
      </div>

      <div className="upload-card col m-2">
        <h3>Filter management</h3>

        {/* Upload */}
        <div className="upload-form">
          <strong>Upload custom filter</strong>
          <p
            className="text-muted"
            style={{ fontSize: "0.85rem", margin: "4px 0 8px" }}
          >
            Upload a <code>.js</code> file that exports:
          </p>
          <pre
            style={{
              fontSize: "0.85rem",
              margin: "0 0 8px",
              padding: "8px",
              backgroundColor: "#f8f9fa",
              borderRadius: "4px",
            }}
          >
            <code>{`{
  id,
  label,
  decription, 
  params: [],
  apply: (readings, params) => { return readings }
}`}</code>
          </pre>
          <input
            ref={filterFileInputRef}
            className="form-control"
            type="file"
            accept=".js"
            onChange={handleFilterFileChange}
            disabled={isUploadingFilter}
          />
          {pendingFilterFile && (
            <div style={{ marginTop: "8px" }}>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={handleFilterUpload}
                disabled={isUploadingFilter}
              >
                {isUploadingFilter ? "Uploading…" : "Save"}
              </button>
            </div>
          )}
          {filterStatus.message && (
            <div
              className={`upload-status ${filterStatus.type !== "idle" ? `is-${filterStatus.type}` : ""}`}
            >
              {filterStatus.message}
            </div>
          )}
        </div>

        {isLoadingFilters && (
          <div className="upload-file-meta">Loading filters…</div>
        )}
        {filters.length > 0 && (
          <div className="mt-3">
            <strong>Loaded filters</strong>
            <table className="table mt-2">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Label</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filters.map((filter) => (
                  <tr key={filter.id}>
                    <td>
                      <code>{filter.id}</code>
                    </td>
                    <td>{filter.label}</td>
                    <td>
                      {!filter.builtin && (
                        <button
                          className="btn btn-outline-danger btn-sm"
                          type="button"
                          onClick={() => handleFilterDelete(filter)}
                          disabled={isUploadingFilter}
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="upload-card col m-2">
        <h3>Plugin management</h3>
        <p
          className="text-muted"
          style={{ fontSize: "0.85rem", margin: "4px 0 8px" }}
        >
          Control which filters and visualization components are available per
          context. Global defaults apply when a context has no specific config.
        </p>

        <div className="mb-2">
          <label htmlFor="plugin-context-select">Context</label>
          <select
            id="plugin-context-select"
            className="form-control"
            value={pluginContextId}
            onChange={(e) => setPluginContextId(e.target.value)}
            disabled={isSavingPlugins}
          >
            <option value="">Global defaults</option>
            {availableContexts.map((ctx) => (
              <option key={ctx.id} value={ctx.id}>
                {ctx.name}
              </option>
            ))}
          </select>
        </div>

        <div className="btn-group mb-3" role="group">
          <button
            type="button"
            className={`btn btn-sm ${pluginType === "visualization" ? "btn-primary" : "btn-outline-primary"}`}
            onClick={() => setPluginType("visualization")}
            disabled={isSavingPlugins}
          >
            Visualization
          </button>
          <button
            type="button"
            className={`btn btn-sm ${pluginType === "filter" ? "btn-primary" : "btn-outline-primary"}`}
            onClick={() => setPluginType("filter")}
            disabled={isSavingPlugins}
          >
            Filters
          </button>
        </div>

        {pluginContextId &&
          pluginHasContextConfig &&
          pluginStatus.type === "idle" && (
            <div
              className="upload-status is-info"
              style={{ marginBottom: "8px" }}
            >
              Context-specific config active.
            </div>
          )}
        {pluginStatus.message && (
          <div
            className={`upload-status ${pluginStatus.type !== "idle" ? `is-${pluginStatus.type}` : ""}`}
          >
            {pluginStatus.message}
          </div>
        )}

        {isLoadingPlugins ? (
          <div className="upload-file-meta">Loading plugins…</div>
        ) : pluginList.length > 0 ? (
          <table className="table mt-2">
            <thead>
              <tr>
                <th>Plugin</th>
                <th>Type</th>
                <th>Enabled</th>
                <th>Order</th>
              </tr>
            </thead>
            <tbody>
              {pluginList.map((plugin, idx) => (
                <tr key={plugin.id}>
                  <td>
                    <code>{plugin.id}</code>
                    <span style={{ marginLeft: "6px" }}>{plugin.label}</span>
                  </td>
                  <td>
                    <span
                      className={`badge ${plugin.builtin ? "bg-secondary" : "bg-primary"}`}
                    >
                      {plugin.builtin ? "Built-in" : "Custom"}
                    </span>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={plugin.enabled}
                      onChange={() => togglePlugin(plugin.id)}
                      disabled={isSavingPlugins}
                    />
                  </td>
                  <td>
                    <button
                      className="btn btn-outline-secondary btn-sm me-1"
                      type="button"
                      onClick={() => movePlugin(plugin.id, -1)}
                      disabled={idx === 0 || isSavingPlugins}
                    >
                      ↑
                    </button>
                    <button
                      className="btn btn-outline-secondary btn-sm"
                      type="button"
                      onClick={() => movePlugin(plugin.id, 1)}
                      disabled={
                        idx === pluginList.length - 1 || isSavingPlugins
                      }
                    >
                      ↓
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}

        <div className="upload-actions mt-2">
          <button
            className="btn btn-primary"
            type="button"
            onClick={handleSavePlugins}
            disabled={isSavingPlugins || pluginList.length === 0}
          >
            {isSavingPlugins ? "Saving…" : "Save"}
          </button>
          {pluginContextId && pluginHasContextConfig && (
            <button
              className="btn btn-outline-secondary btn-sm"
              type="button"
              onClick={handleResetPlugins}
              disabled={isSavingPlugins}
            >
              Reset to defaults
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminPanel;
