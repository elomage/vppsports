// const SERVER_URL = "http://192.168.88.3:8081";
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
  console.log(`${SERVER_URL}/run?dateFrom=${dateFrom}&dateTo=${dateTo}`);
  console.log(response);
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
