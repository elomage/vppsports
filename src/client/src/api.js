const SERVER_URL = import.meta.env.VITE_SERVER_URL;
const ACCESS_TOKEN_STORAGE_KEY = "vppsports_access_token";

let accessToken = null;
let onAuthFailure = null;
let refreshInFlight = null;

export class UnauthorizedError extends Error {
  constructor(message = "Unauthorized") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

export function setAuthFailureHandler(handler) {
  onAuthFailure = typeof handler === "function" ? handler : null;
}

export function setAccessToken(token) {
  accessToken = token || null;
  if (accessToken) {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, accessToken);
  } else {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  }
}

function notifyAuthFailure() {
  if (typeof onAuthFailure === "function") {
    onAuthFailure();
  }
}

async function parseResponse(response) {
  if (response.status === 204) return null;

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

async function refreshAccessToken() {
  if (refreshInFlight) {
    return refreshInFlight;
  }

  refreshInFlight = (async () => {
    const response = await fetch(`${SERVER_URL}/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({}),
    });

    if (!response.ok) {
      setAccessToken(null);
      throw new UnauthorizedError("Session expired");
    }

    const data = await response.json();
    setAccessToken(data.accessToken);
    return data.accessToken;
  })();

  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

async function request(path, options = {}, retry = true) {
  const headers = new Headers(options.headers || {});
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${SERVER_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (response.status === 401 && retry) {
    try {
      await refreshAccessToken();
      return request(path, options, false);
    } catch (error) {
      notifyAuthFailure();
      throw error;
    }
  }

  if (response.status === 401) {
    notifyAuthFailure();
    throw new UnauthorizedError();
  }

  if (!response.ok) {
    const payload = await parseResponse(response);
    const message =
      typeof payload === "string"
        ? payload
        : payload?.message || `Request failed (${response.status})`;
    throw new Error(message);
  }

  return parseResponse(response);
}

export async function login(username, password) {
  const response = await fetch(`${SERVER_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    const payload = await parseResponse(response);
    const message =
      typeof payload === "string"
        ? payload
        : payload?.message || "Login failed";
    throw new Error(message);
  }

  const data = await response.json();
  setAccessToken(data.accessToken);
  return data;
}

export async function fetchCurrentUser() {
  const data = await request("/auth/me");
  return data?.user || null;
}

export async function initializeSession() {
  const cachedToken = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  if (cachedToken) {
    setAccessToken(cachedToken);
    try {
      return await fetchCurrentUser();
    } catch (error) {
      setAccessToken(null);
    }
  }

  try {
    await refreshAccessToken();
    return await fetchCurrentUser();
  } catch (error) {
    setAccessToken(null);
    return null;
  }
}

export async function logout() {
  try {
    await request("/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  } catch (error) {
    // Always clear local state even if backend logout fails.
  } finally {
    setAccessToken(null);
    notifyAuthFailure();
  }
}

export async function fetchRuns(dateFrom, dateTo) {
  return request(`/run?dateFrom=${dateFrom || ""}&dateTo=${dateTo || ""}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export async function fetchSelectedRun(runId) {
  return request(`/run/${runId}`);
}

export async function fetchSelectedRunFiltered(runId) {
  return request(`/run/${runId}?filterData=true`);
}

export async function fetchRunVideo(videoName, retry = true) {
  const headers = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${SERVER_URL}/video/${videoName}`, {
    headers,
    credentials: "include",
  });

  if (response.status === 401 && retry) {
    try {
      await refreshAccessToken();
      return fetchRunVideo(videoName, false);
    } catch (error) {
      notifyAuthFailure();
      throw error;
    }
  }

  if (response.status === 401) {
    notifyAuthFailure();
    throw new UnauthorizedError();
  }

  if (!response.ok) {
    const payload = await parseResponse(response);
    const message =
      typeof payload === "string"
        ? payload
        : payload?.message || "Failed to fetch video";
    throw new Error(message);
  }

  return response;
}

export async function checkRunVideoExists(videoName, retry = true) {
  if (!videoName) return false;

  const headers = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${SERVER_URL}/video/${videoName}`, {
    method: "HEAD",
    headers,
    credentials: "include",
  });

  if (response.status === 401 && retry) {
    try {
      await refreshAccessToken();
      return checkRunVideoExists(videoName, false);
    } catch (error) {
      notifyAuthFailure();
      throw error;
    }
  }

  if (response.status === 401) {
    notifyAuthFailure();
    throw new UnauthorizedError();
  }

  if (response.status === 404) {
    return false;
  }

  if (!response.ok) {
    const payload = await parseResponse(response);
    const message =
      typeof payload === "string"
        ? payload
        : payload?.message || "Failed to check video availability";
    throw new Error(message);
  }

  return true;
}

export async function uploadSensorDataBin(file, options = {}) {
  const params = new URLSearchParams();
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.append(key, value);
    }
  });

  const query = params.toString();
  const uploadUrl = `/run/upload${query ? `?${query}` : ""}`;

  return request(uploadUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/octet-stream",
    },
    body: await file.arrayBuffer(),
  });
}

export async function deleteRun(runId) {
  return request(`/run/${runId}`, {
    method: "DELETE",
  });
}

export async function createUser(payload) {
  return request("/auth/users", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function fetchUsers() {
  return request("/auth/users", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export async function fetchDeletedUsers() {
  return request("/auth/users/deleted", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export async function updateUser(currentUsername, payload) {
  return request(`/auth/users/${encodeURIComponent(currentUsername)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function removeUser(username) {
  return request(`/auth/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export async function restoreUser(username) {
  return request(`/auth/users/${encodeURIComponent(username)}/restore`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
}

export async function fetchContexts() {
  return request("/context", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export async function fetchDeletedContexts() {
  return request("/context/deleted", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export async function createContext(name) {
  return request("/context", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
}

export async function updateContext(currentName, name) {
  return request(`/context/${encodeURIComponent(currentName)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
}

export async function removeContext(name) {
  return request(`/context/${encodeURIComponent(name)}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export async function restoreContext(name) {
  return request(`/context/${encodeURIComponent(name)}/restore`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
}
