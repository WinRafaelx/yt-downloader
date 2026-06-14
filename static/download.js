const form = document.querySelector("[data-download-form]");
const button = document.querySelector("[data-download-button]");
const buttonText = document.querySelector("[data-button-text]");
const statusPanel = document.querySelector("[data-download-status]");
const statusText = document.querySelector("[data-status-text]");

function setStatus(state, message) {
  statusPanel.hidden = false;
  statusPanel.dataset.state = state;
  statusText.textContent = message;
}

function setBusy(isBusy, label = "Preparing...") {
  button.disabled = isBusy;
  buttonText.textContent = isBusy ? label : "Download";
}

function filenameFromDisposition(disposition) {
  if (!disposition) {
    return "youtube-download";
  }

  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    return decodeURIComponent(utf8Match[1].replaceAll("+", "%20"));
  }

  const asciiMatch = disposition.match(/filename="?([^"]+)"?/i);
  return asciiMatch ? asciiMatch[1] : "youtube-download";
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function readError(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = await response.json();
    return body.error || "Download failed. Please try again.";
  }

  return "Download failed. Please try again.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  setBusy(true);
  setStatus("busy", "Preparing download...");

  try {
    setBusy(true, "Downloading...");
    setStatus("busy", "Downloading media...");

    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: {
        "X-Requested-With": "fetch",
      },
    });

    if (!response.ok) {
      throw new Error(await readError(response));
    }

    setStatus("busy", "Saving file...");

    const blob = await response.blob();
    const filename = filenameFromDisposition(response.headers.get("content-disposition"));
    saveBlob(blob, filename);

    setStatus("success", "Download complete.");
  } catch (error) {
    setStatus("error", error.message || "Download failed. Please try again.");
  } finally {
    setBusy(false);
  }
});
