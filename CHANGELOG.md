# Changelog

This document outlines the major changes and enhancements made to the Live Audio STT Translate project.

## Version 2.0 - Multi-Device Broadcasting Platform

This major update transforms the application from a single-user subtitle tool into a robust, production-ready, multi-device broadcasting platform.

### Key Enhancements

#### 1. Dual STT Engine with Fallback
- **Primary STT:** Integrated Google Cloud Speech-to-Text for high-accuracy transcription.
- **Fallback STT:** Retained `faster-whisper` as a reliable fallback, which is loaded on-demand to conserve resources.
- **Implementation:** A new `STTEngine` class in `backend/stt_engine.py` now manages the transcription logic, attempting to use Google STT first and seamlessly falling back to Whisper if the primary service fails.

#### 2. Dual Translation Engine with Fallback
- **Primary Translation:** Integrated the DeepL API for superior translation quality.
- **Fallback Translation:** Retained the local MarianMT model as a fallback.
- **Implementation:** A new `TranslationEngine` class in `backend/translate_engine.py` handles all translation requests, prioritizing DeepL.

#### 3. WebSocket Multi-Client Synchronization
- The WebSocket server in `backend/main.py` has been upgraded to manage multiple concurrent client connections.
- Subtitles are now broadcast to all connected clients, ensuring all displays are synchronized.
- The message format has been updated to include a `timestamp` and `source` field for better data structure and potential future features.

#### 4. Persistent Overlay Frontend
- A new `frontend/overlay.html` page has been created to serve as a dedicated, persistent display for subtitles.
- It features a clean, fullscreen interface with fixed positions for Hindi and English lines, ideal for projectors or secondary monitors.
- Controls auto-hide after 3 seconds of inactivity, and the overlay can be exited by pressing the `ESC` key or using the on-screen button.

#### 5. Frontend API Configuration Panel
- The main `frontend/index.html` page now includes a configuration panel.
- Users can select their preferred STT and Translation engines from a dropdown menu.
- API keys for Google and DeepL can be entered directly on the page.
- All configuration settings are saved to the browser's `localStorage`, so they persist across sessions.

#### 6. Docker & Docker Compose Support
- **`Dockerfile`**: A new `Dockerfile` has been added to containerize the Python backend.
- **`docker-compose.yml`**: A new `docker-compose.yml` file orchestrates both the backend and a lightweight `nginx` frontend server.
- **`run.sh` Update**: The main execution script now supports a `docker` argument (`bash run.sh docker`) to build and launch the application using Docker Compose.

#### 7. Performance and Resilience
- **Logging:** Enhanced logging has been added throughout the backend to provide better insights into the application's state, including notifications for STT/translation fallbacks and WebSocket connection counts.
- **Auto-Restart:** The `docker-compose.yml` is configured with `restart: always` to ensure that both backend and frontend containers automatically restart if they crash.

### How to Use the New Features
1.  **Run with Docker:** Use `bash run.sh docker` for the most straightforward setup.
2.  **Configure APIs:** Open `http://localhost:8100`, enter your API keys in the config panel, and save.
3.  **Launch Overlay:** Click the "Open Overlay" button to open the subtitle display in a new window.
4.  **Start Transcribing:** Use the "Start Listening" button for live audio or upload a file. Subtitles will now appear on both the main page and all open overlay windows.