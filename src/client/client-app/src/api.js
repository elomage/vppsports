const SERVER_URL = "http://localhost:8081";

export async function fetchRuns(dateFrom, dateTo) {
  const response = await fetch(
    `${SERVER_URL}/run?dateFrom=${dateFrom}&dateTo=${dateTo}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
  return response.json();
}

export async function fetchSelectedRun(runId) {
  const response = await fetch(`${SERVER_URL}/run/${runId}`);
  return response.json();
}

export async function fetchSelectedRunFiltered(runId) {
  const response = await fetch(`${SERVER_URL}/run/${runId}?filterData=true`);
  return response.json();
}

export async function fetchRunVideo(videoName) {
  const response = await fetch(`${SERVER_URL}/video/${videoName}`);
  return response;
}

export async function uploadSensorDataBin(file, options = {}) {
  const params = new URLSearchParams();
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.append(key, value);
    }
  });

  const query = params.toString();
  const uploadUrl = `${SERVER_URL}/run/upload${query ? `?${query}` : ""}`;

  const response = await fetch(uploadUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/octet-stream",
    },
    body: await file.arrayBuffer(),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Upload failed");
  }

  return response.json();
}
