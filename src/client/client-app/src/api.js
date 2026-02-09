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

export async function uploadSensorDataBin(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${SERVER_URL}/sensor-data/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Upload failed");
  }

  return response.json();
}
