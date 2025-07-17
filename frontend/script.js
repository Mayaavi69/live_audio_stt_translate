const audioInputSelect = document.getElementById("audio-input");
const startListeningButton = document.getElementById("start-listening");
const listeningIndicator = document.getElementById("listening-indicator");
const hindiSubtitleDiv = document.getElementById("hindi-subtitle");
const englishSubtitleDiv = document.getElementById("english-subtitle");
const statusMessageDiv = document.getElementById("status-message"); // New element for status messages

let ws; // Declare WebSocket globally to manage connection state

function updateStatus(message, isError = false) {
  statusMessageDiv.textContent = message;
  statusMessageDiv.style.color = isError ? "red" : "white";
  if (isError) {
    listeningIndicator.classList.add("hidden");
    startListeningButton.style.display = "block";
    audioInputSelect.style.display = "block";
    document.querySelector('label[for="audio-input"]').style.display = "block";
  }
}

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return; // Already connected or connecting
  }

  ws = new WebSocket("ws://localhost:8768");

  ws.onopen = () => {
    console.log("WebSocket connected.");
    updateStatus("Connected to backend. Waiting for audio...", false);
    listeningIndicator.classList.remove("hidden");
    startListeningButton.style.display = "none";
    audioInputSelect.style.display = "none";
    document.querySelector('label[for="audio-input"]').style.display = "none";
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      hindiSubtitleDiv.textContent = data.hindi;
      englishSubtitleDiv.textContent = data.english;
      updateStatus("Listening...", false); // Clear any previous status messages
    } catch (e) {
      console.error("Error parsing WebSocket message:", e);
      updateStatus("Error processing subtitle data.", true);
    }
  };

  ws.onclose = (event) => {
    console.log("WebSocket disconnected:", event.code, event.reason);
    updateStatus("Disconnected from backend. Retrying...", true);
    setTimeout(connectWebSocket, 3000); // Attempt to reconnect after 3 seconds
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
    updateStatus("WebSocket error. Check backend server.", true);
    ws.close(); // Close to trigger reconnect logic
  };
}

// Function to populate audio input devices (client-side, not directly used by backend mic)
async function populateAudioDevices() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputDevices = devices.filter(device => device.kind === 'audioinput');

    audioInputSelect.innerHTML = ''; // Clear existing options
    if (audioInputDevices.length === 0) {
      const option = document.createElement('option');
      option.textContent = "No audio input devices found.";
      audioInputSelect.appendChild(option);
      startListeningButton.disabled = true;
      updateStatus("No microphone found. Please connect one.", true);
      return;
    }

    audioInputDevices.forEach(device => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `Microphone ${audioInputSelect.options.length + 1}`;
      audioInputSelect.appendChild(option);
    });
    startListeningButton.disabled = false;
    updateStatus("Select your microphone and click 'Start Listening'.", false);

  } catch (error) {
    console.error("Error enumerating devices:", error);
    updateStatus("Error accessing microphone devices. Please grant permission.", true);
    startListeningButton.disabled = true;
  }
}

// Initial population of devices
populateAudioDevices();

// Handle start listening button click (client-side, for visual feedback)
startListeningButton.addEventListener("click", () => {
  // This button is primarily for visual feedback on the frontend.
  // The actual mic listening starts with the Python backend.
  updateStatus("Starting backend audio processing...", false);
  connectWebSocket(); // Attempt to connect WebSocket when button is clicked
});

// Request microphone permission on page load
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => {
    // Mic access granted, no need to do anything with the stream here
    // as the Python backend handles the actual audio capture.
    stream.getTracks().forEach(track => track.stop()); // Stop the stream immediately
    updateStatus("Microphone access granted. Ready to connect.", false);
  })
  .catch(err => {
    console.error("Microphone access denied:", err);
    updateStatus("Microphone access denied. Please enable it in your browser settings.", true);
    startListeningButton.disabled = true;
  });

// Initial WebSocket connection attempt
connectWebSocket();