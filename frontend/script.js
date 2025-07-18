const audioInputSelect = document.getElementById("audio-input");
const startListeningButton = document.getElementById("start-listening");
const listeningIndicator = document.getElementById("listening-indicator");
const hindiSubtitleDiv = document.getElementById("hindi-subtitle");
const englishSubtitleDiv = document.getElementById("english-subtitle");
const statusMessageDiv = document.getElementById("status-message");
const audioFileInput = document.getElementById("audio-file-input");
const uploadAudioButton = document.getElementById("upload-audio-button");

let ws; // Declare WebSocket globally to manage connection state

function updateStatus(message, isError = false) {
  statusMessageDiv.textContent = message;
  statusMessageDiv.style.color = isError ? "red" : "white";
  if (isError) {
    listeningIndicator.classList.add("hidden");
    // Show live input options if there's an error with file upload or general issue
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
    updateStatus("Connected to backend. Ready for live audio or file upload.", false);
    listeningIndicator.classList.add("hidden"); // Hide listening indicator initially
    startListeningButton.style.display = "block";
    audioInputSelect.style.display = "block";
    document.querySelector('label[for="audio-input"]').style.display = "block";
    uploadAudioButton.style.display = "block";
    audioFileInput.style.display = "block";
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      hindiSubtitleDiv.textContent = data.hindi;
      englishSubtitleDiv.textContent = data.english;
      updateStatus("Receiving transcription...", false);
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
    } else {
      audioInputDevices.forEach(device => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.textContent = device.label || `Microphone ${audioInputSelect.options.length + 1}`;
        audioInputSelect.appendChild(option);
      });
      startListeningButton.disabled = false;
      updateStatus("Select your microphone and click 'Start Listening' or upload an audio file.", false);
    }
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
  updateStatus("Starting live audio processing...", false);
  listeningIndicator.classList.remove("hidden");
  // Hide file upload options
  uploadAudioButton.style.display = "none";
  audioFileInput.style.display = "none";
  // Ensure WebSocket is connected
  connectWebSocket();
  // Send a message to the backend to start live listening (if needed, or backend auto-starts)
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "start_live_audio" }));
  }
});

// Handle audio file upload
uploadAudioButton.addEventListener("click", () => {
  const file = audioFileInput.files[0];
  if (!file) {
    updateStatus("Please select an audio file first.", true);
    return;
  }

  updateStatus("Uploading audio file for transcription...", false);
  listeningIndicator.classList.remove("hidden"); // Show processing indicator
  // Hide live input options
  startListeningButton.style.display = "none";
  audioInputSelect.style.display = "none";
  document.querySelector('label[for="audio-input"]').style.display = "none";

  const reader = new FileReader();
  reader.onload = (event) => {
    const audioData = event.target.result; // ArrayBuffer
    if (ws && ws.readyState === WebSocket.OPEN) {
      // Send audio data as a binary message or base64 string
      // For simplicity, sending as ArrayBuffer directly. Backend needs to handle this.
      ws.send(audioData);
      updateStatus("Audio file sent. Processing...", false);
    } else {
      updateStatus("WebSocket not connected. Cannot upload file.", true);
      connectWebSocket(); // Try to reconnect
    }
  };
  reader.onerror = (error) => {
    console.error("Error reading file:", error);
    updateStatus("Error reading audio file.", true);
  };
  reader.readAsArrayBuffer(file);
});


// Request microphone permission on page load
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => {
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