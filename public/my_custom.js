function toggleLogButton() {
  const logButton = document
    .querySelector('a[href="#"] img[alt="Download Logs"]')
    ?.closest("button");

  // check if URL contains "thread/{thread-id}"
  const urlPattern = /\/thread\/[a-f0-9-]+/;

  if (logButton) {
    if (!urlPattern.test(window.location.pathname)) {
      logButton.style.display = "none";
    } else {
      logButton.style.display = "block";
    }
  }
}

// Run when the DOM is fully loaded
document.addEventListener("DOMContentLoaded", toggleLogButton);

// Also run periodically in case the button is added dynamically
const observer = new MutationObserver(toggleLogButton);
observer.observe(document.body, { childList: true, subtree: true });

document.addEventListener("click", async (event) => {
  const anchor = event.target.closest("a[href='#']");
  if (anchor && anchor.querySelector("img[alt='Download Logs']")) {
    event.preventDefault();

    // Extract thread ID from URL (assumes URL structure: /thread/{thread_id})
    const match = window.location.pathname.match(/\/thread\/([a-f0-9-]+)/);
    if (!match) {
      alert("No active thread found.");
      return;
    }
    const threadId = match[1];

    if (confirm("Download logs for this thread?")) {
      try {
        // Build the URL to your dedicated download endpoint
        const url = new URL("http://localhost:8001/download_logs");
        url.searchParams.append("thread_id", threadId);

        // Call the download endpoint
        const response = await fetch(url, {
          method: "GET",
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText);
        }

        // Create a blob from the response and trigger the download
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = `logs_${threadId}.log`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        document.body.removeChild(a);
      } catch (error) {
        console.error("Error downloading logs:", error);
        alert("Error downloading logs: " + error.message);
      }
    }
  }
});
