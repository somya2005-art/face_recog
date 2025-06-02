document.addEventListener("DOMContentLoaded", function () {
    let startButton = document.getElementById("start-scan");
    let scanStatus = document.getElementById("scan-status");
    let scanLine = document.getElementById("scan-line");
    let consoleBox = document.getElementById("console");
    let logList = document.getElementById("log-list");

    startButton.addEventListener("click", function () {
        fetch("/start-scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "scan" })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                scanStatus.textContent = "Scanning...";
                scanLine.style.display = "block";

                setTimeout(() => {
                    scanStatus.textContent = "Face scanned successfully!";
                    scanLine.style.display = "none";

                    // Add log entry
                    let logItem = document.createElement("li");
                    logItem.textContent = `Face scanned at ${new Date().toLocaleTimeString()}`;
                    logList.appendChild(logItem);

                    // Update console log
                    let consoleEntry = document.createElement("p");
                    consoleEntry.textContent = "> Face scan completed.";
                    consoleBox.appendChild(consoleEntry);
                }, 3000);
            } else {
                scanStatus.textContent = "Scan failed!";
            }
        })
        .catch(error => console.error("Error:", error));
    });
});
