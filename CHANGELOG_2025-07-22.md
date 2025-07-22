# Changelog - 2025-07-22

## Real-time STT Integration and Python-based Frontend

This update introduces real-time Speech-to-Text (STT) capabilities by integrating the `RealtimeSTT` library and completely refactors the frontend to be Python-based using PyQt6. Due to persistent issues with PyInstaller and CUDA/Torch dependencies, the application is no longer packaged into standalone executables. It will be run directly from the Python scripts.

### Key Changes:

*   **Real-time STT Integration:**
    *   Cloned `https://github.com/oddlama/whisper-overlay` into `temporary clones/` for analysis.
    *   Integrated `RealtimeSTT` into `backend/main.py` to handle live microphone input and provide real-time and final transcriptions.
    *   Modified `backend/main.py` to send WebSocket messages with a `type` field (`"realtime"`, `"final"`, `"status"`, `"error"`) for better frontend differentiation.
    *   Added a "Stop Listening" command to the backend.
    *   Updated `backend/requirements.txt` to include `RealtimeSTT`.
    *   Forced CPU usage for `torch` in `backend/stt_engine.py` and `backend/main.py` to avoid CUDA dependency issues.

*   **Python-based PyQt6 Frontend:**
    *   Replaced the entire HTML/JavaScript frontend with a new PyQt6 application (`frontend/gui.py`).
    *   The new frontend provides a graphical user interface for:
        *   Connecting to the backend WebSocket server.
        *   Starting and stopping live audio transcription.
        *   Uploading audio files for batch processing.
        *   Displaying real-time and final Hindi and English subtitles.
        *   A transparent, always-on-top overlay window for subtitles.
        *   API configuration settings (currently saved to console).
    *   Removed all old frontend files: `frontend/index.html`, `frontend/overlay.html`, `frontend/script.js`, `frontend/style.css`.
    *   Updated `backend/requirements.txt` to include `PyQt6`.

*   **Reverted Packaging Attempt:**
    *   Removed `setup.py`.
    *   Removed `dist/` and `build/` directories.
    *   Reverted `backend/main.py` to direct execution (removed `run_backend_server` wrapper function).
    *   Reverted `frontend/gui.py` to direct execution (removed `run_frontend_gui` wrapper function).
    *   Reverted `run.sh` to directly execute the Python scripts.

### How to Run:

1.  **Install Dependencies:**
    ```bash
    pip install -r backend/requirements.txt
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
    ```
    (Ensure `enum34` is uninstalled if present: `pip uninstall enum34`)

2.  **Start the Backend Server:**
    ```bash
    python3 backend/main.py
    ```
    Keep this terminal open.

3.  **Start the Frontend GUI:**
    ```bash
    python3 frontend/gui.py