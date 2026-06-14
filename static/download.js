const form = document.querySelector("[data-download-form]");
const button = document.querySelector("[data-download-button]");
const buttonText = document.querySelector("[data-button-text]");
const statusPanel = document.querySelector("[data-download-status]");
const statusText = document.querySelector("[data-status-text]");
const statusPercent = document.querySelector("[data-status-percent]");
const progressTrack = document.querySelector("[data-progress-track]");
const progressBar = document.querySelector("[data-progress-bar]");

const pollDelay = 900;

function setStatus(state, message, progress = null) {
  statusPanel.hidden = false;
  statusPanel.dataset.state = state;
  statusText.textContent = message;

  if (Number.isFinite(progress)) {
    const clamped = Math.max(0, Math.min(100, progress));
    statusPercent.hidden = false;
    statusPercent.textContent = `${clamped}%`;
    progressTrack.hidden = false;
    progressBar.style.width = `${clamped}%`;
  } else {
    statusPercent.hidden = true;
    progressTrack.hidden = true;
    progressBar.style.width = "0%";
  }
}

function setBusy(isBusy, label = "Preparing...") {
  button.disabled = isBusy;
  buttonText.textContent = isBusy ? label : "Download";
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function readError(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = await response.json();
    return body.error || "Download failed. Please try again.";
  }

  return "Download failed. Please try again.";
}

async function createJob() {
  const response = await fetch(form.dataset.jobUrl, {
    method: "POST",
    body: new FormData(form),
    headers: {
      "X-Requested-With": "fetch",
    },
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

async function fetchJob(jobId) {
  const response = await fetch(`/jobs/${jobId}`, {
    headers: {
      "X-Requested-With": "fetch",
    },
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

async function waitForJob(jobId) {
  while (true) {
    const job = await fetchJob(jobId);
    const progress = Number.isFinite(job.progress) ? job.progress : null;

    if (job.status === "error") {
      throw new Error(job.error || "Download failed. Please try again.");
    }

    if (job.status === "complete") {
      setStatus("success", job.message || "Download complete.", 100);
      return job;
    }

    setStatus("busy", job.message || "Downloading media...", progress);
    await delay(pollDelay);
  }
}

function downloadFile(url) {
  const link = document.createElement("a");

  link.href = url;
  document.body.append(link);
  link.click();
  link.remove();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  setBusy(true, "Starting...");
  setStatus("busy", "Starting download...", 0);

  try {
    const job = await createJob();
    setBusy(true, "Downloading...");
    setStatus("busy", job.message || "Queued download...", job.progress || 0);

    const finishedJob = await waitForJob(job.id);
    downloadFile(finishedJob.download_url);
  } catch (error) {
    setStatus("error", error.message || "Download failed. Please try again.");
  } finally {
    setBusy(false);
  }
});
