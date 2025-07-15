const ws = new WebSocket("ws://localhost:8768");

const audioInputSelect = document.getElementById("audio-input");
const startListeningButton = document.getElementById("start-listening");
const listeningIndicator = document.getElementById("listening-indicator");
const hindiSubtitleDiv = document.getElementById("hindi-subtitle");
const englishSubtitleDiv = document.getElementById("english-subtitle");

// Function to populate audio input devices (client-side, not directly used by backend mic)
async function populateAudioDevices() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputDevices = devices.filter(device => device.kind === 'audioinput');

    audioInputSelect.innerHTML = ''; // Clear existing options
    audioInputDevices.forEach(device => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `Microphone ${audioInputSelect.options.length + 1}`;
      audioInputSelect.appendChild(option);
    });
  } catch (error) {
    console.error("Error enumerating devices:", error);
  }
}

// Initial population of devices
populateAudioDevices();

// Listen for messages from the WebSocket server
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  hindiSubtitleDiv.textContent = data.hindi;
  englishSubtitleDiv.textContent = data.english;
};

// Handle start listening button click (client-side, for visual feedback)
startListeningButton.addEventListener("click", () => {
  // This button is primarily for visual feedback on the frontend.
  // The actual mic listening starts with the Python backend.
  listeningIndicator.classList.remove("hidden");
  startListeningButton.style.display = "none";
  audioInputSelect.style.display = "none";
  document.querySelector('label[for="audio-input"]').style.display = "none";
});

// Optional: Request microphone permission on page load
// This will prompt the user for mic access, which is good practice.
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => {
    // Mic access granted, no need to do anything with the stream here
    // as the Python backend handles the actual audio capture.
    stream.getTracks().forEach(track => track.stop()); // Stop the stream immediately
  })
  .catch(err => {
    console.error("Microphone access denied:", err);
    // Inform the user that mic access is needed for the system to work
    alert("Microphone access is required for live transcription. Please enable it in your browser settings.");
  });