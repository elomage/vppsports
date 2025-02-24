export async function fetchRuns(dateFrom, dateTo) {
  const response = await fetch(
    `http://localhost:8081/run?dateFrom=${dateFrom}&dateTo=${dateTo}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    }
  );
  console.log(response);
  return response.json();
}

export async function fetchSelectedRun(runId) {
  const response = await fetch(`http://localhost:8081/run/${runId}`);
  return response.json();
}
