import sys
import asyncio
import websockets
import json
import sounddevice as sd
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QLineEdit, QFileDialog, QCheckBox, QMainWindow, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPalette, QFont

class WebSocketClient(QThread):
    message_received = pyqtSignal(dict)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, uri):
        super().__init__()
        self.uri = uri
        self.websocket = None
        self.running = True

    async def connect(self):
        reconnect_attempts = 0
        while self.running:
            try:
                self.websocket = await websockets.connect(self.uri)
                self.connected.emit()
                reconnect_attempts = 0
                await self.listen()
            except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
                print("WebSocket connection closed, attempting to reconnect...")
            except Exception as e:
                print(f"WebSocket connection error: {e}, attempting to reconnect...")
            finally:
                if self.running:
                    reconnect_attempts += 1
                    delay = min(1000 * (2 ** reconnect_attempts), 30000) / 1000
                    print(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    if self.websocket:
                        await self.websocket.close()
                    self.disconnected.emit()

    async def listen(self):
        try:
            while self.running:
                message = await self.websocket.recv()
                data = json.loads(message)
                self.message_received.emit(data)
        except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
            print("WebSocket listener stopped due to connection closure.")
        except Exception as e:
            print(f"Error in WebSocket listener: {e}")
        finally:
            self.disconnected.emit()

    def send_message(self, message):
        if self.websocket and self.websocket.state == websockets.protocol.State.OPEN:
            asyncio.run_coroutine_threadsafe(self.websocket.send(json.dumps(message)), self.loop)
        else:
            print("WebSocket not open, cannot send message.")

    def send_binary(self, data):
        if self.websocket and self.websocket.state == websockets.protocol.State.OPEN:
            asyncio.run_coroutine_threadsafe(self.websocket.send(data), self.loop)
        else:
            print("WebSocket not open, cannot send binary data.")

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.connect())
        self.loop.close()

    def stop(self):
        self.running = False
        if self.websocket:
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)
        self.wait() # Wait for the thread to finish

class OverlayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Subtitle Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background:transparent;")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hindi_realtime_label = QLabel("")
        self.hindi_realtime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hindi_realtime_label.setStyleSheet("color: #888; font-size: 40px;")
        self.hindi_realtime_label.setWordWrap(True)
        layout.addWidget(self.hindi_realtime_label)

        self.hindi_final_label = QLabel("")
        self.hindi_final_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hindi_final_label.setStyleSheet("color: #ccc; font-size: 45px;")
        self.hindi_final_label.setWordWrap(True)
        layout.addWidget(self.hindi_final_label)

        self.english_final_label = QLabel("")
        self.english_final_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.english_final_label.setStyleSheet("color: white; font-size: 50px;")
        self.english_final_label.setWordWrap(True)
        layout.addWidget(self.english_final_label)

        self.setGeometry(100, 100, 800, 300) # Initial size and position

    def update_subtitles(self, data):
        if data.get("type") == "realtime":
            self.hindi_realtime_label.setText(data.get("hindi", ""))
            self.hindi_final_label.setText("")
            self.english_final_label.setText("")
        elif data.get("type") == "final":
            self.hindi_final_label.setText(data.get("hindi", ""))
            self.english_final_label.setText(data.get("english", ""))
            self.hindi_realtime_label.setText("") # Clear real-time when final arrives
        else:
            # Clear all on status/error or unknown types
            self.hindi_realtime_label.setText("")
            self.hindi_final_label.setText("")
            self.english_final_label.setText("")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Audio STT Translate")
        self.setGeometry(100, 100, 600, 700)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self.ws_client = WebSocketClient("ws://localhost:8768")
        self.ws_client.message_received.connect(self.handle_websocket_message)
        self.ws_client.connected.connect(self.on_websocket_connected)
        self.ws_client.disconnected.connect(self.on_websocket_disconnected)
        self.ws_client.start()

        self.overlay_window = None

        self.status_label = QLabel("Status: Disconnected")
        self.listening_indicator = QLabel("Listening...")
        self.audio_input_combo = QComboBox()
        self.start_listening_btn = QPushButton("Start Listening")
        self.stop_listening_btn = QPushButton("Stop Listening")
        self.open_overlay_btn = QPushButton("Open Overlay")
        self.audio_file_path_label = QLabel("No file chosen")
        self.choose_file_btn = QPushButton("Choose file")
        self.upload_audio_btn = QPushButton("Upload Audio")
        self.main_hindi_realtime_label = QLabel("Real-time Hindi:")
        self.main_hindi_realtime_text = QLabel("")
        self.main_hindi_final_label = QLabel("Final Hindi:")
        self.main_hindi_final_text = QLabel("")
        self.main_english_final_label = QLabel("Final English:")
        self.main_english_final_text = QLabel("")
        self.stt_engine_combo = QComboBox()
        self.google_api_key_input = QLineEdit()
        self.translation_engine_combo = QComboBox()
        self.deepl_api_key_input = QLineEdit()
        self.save_config_btn = QPushButton("Save Configuration")

        self.init_ui()
        self.load_config()
        self.update_status("Connecting to backend...", False)

    def init_ui(self):
        # Status Message
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 1.1em; color: white;")
        self.main_layout.addWidget(self.status_label)

        # Listening Indicator
        self.listening_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.listening_indicator.setStyleSheet("font-size: 1.5em; color: #007bff;")
        self.listening_indicator.hide() # Hidden by default
        self.main_layout.addWidget(self.listening_indicator)

        # Device Selection
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Select Audio Input:"))
        self.audio_input_combo.clear()
        try:
            devices = sd.query_devices()
            input_devices = [d for d in devices if d['max_input_channels'] > 0]
            if not input_devices:
                self.audio_input_combo.addItem("No input devices found", "none")
                self.start_listening_btn.setEnabled(False)
            else:
                for i, device in enumerate(input_devices):
                    # Store device info including default_samplerate
                    device_info = {
                        'name': device['name'],
                        'index': device['index'],
                        'default_samplerate': device['default_samplerate']
                    }
                    display_name = device['name']
                    if 'default' in device and device['default']:
                        display_name = f"Default: {display_name}"
                    self.audio_input_combo.addItem(f"{display_name} (ID: {device['index']})", device_info)
                self.start_listening_btn.setEnabled(True)
            # Add a "Test Audio" button
            self.test_audio_btn = QPushButton("Test Audio")
            self.test_audio_btn.clicked.connect(self.test_audio_input)
            device_layout.addWidget(self.test_audio_btn)
        except Exception as e:
            self.audio_input_combo.addItem("Error listing devices", "error")
            self.start_listening_btn.setEnabled(False)
            self.update_status(f"Error listing audio devices: {e}", True)
        device_layout.addWidget(self.audio_input_combo)
        self.start_listening_btn.clicked.connect(self.start_listening)
        device_layout.addWidget(self.start_listening_btn)
        self.stop_listening_btn.clicked.connect(self.stop_listening)
        device_layout.addWidget(self.stop_listening_btn)
        self.open_overlay_btn.clicked.connect(self.open_overlay)
        device_layout.addWidget(self.open_overlay_btn)
        self.main_layout.addLayout(device_layout)

        # File Upload
        file_upload_layout = QHBoxLayout()
        file_upload_layout.addWidget(self.audio_file_path_label)
        self.choose_file_btn.clicked.connect(self.choose_audio_file)
        file_upload_layout.addWidget(self.choose_file_btn)
        self.upload_audio_btn.clicked.connect(self.upload_audio_file)
        file_upload_layout.addWidget(self.upload_audio_btn)
        self.main_layout.addLayout(file_upload_layout)

        # Subtitle Display (Main Window - for testing/debugging)
        subtitle_frame = QFrame()
        subtitle_frame.setFrameShape(QFrame.Shape.StyledPanel)
        subtitle_frame.setFrameShadow(QFrame.Shadow.Raised)
        subtitle_layout = QVBoxLayout(subtitle_frame)
        
        self.main_hindi_realtime_label.setStyleSheet("color: #888; font-size: 1.2em;")
        self.main_hindi_realtime_text.setStyleSheet("color: #888; font-size: 1.5em;")
        self.main_hindi_realtime_text.setWordWrap(True)
        subtitle_layout.addWidget(self.main_hindi_realtime_label)
        subtitle_layout.addWidget(self.main_hindi_realtime_text)

        self.main_hindi_final_label.setStyleSheet("color: #ccc; font-size: 1.2em;")
        self.main_hindi_final_text.setStyleSheet("color: #ccc; font-size: 1.5em;")
        self.main_hindi_final_text.setWordWrap(True)
        subtitle_layout.addWidget(self.main_hindi_final_label)
        subtitle_layout.addWidget(self.main_hindi_final_text)

        self.main_english_final_label.setStyleSheet("color: white; font-size: 1.2em;")
        self.main_english_final_text.setStyleSheet("color: white; font-size: 1.5em;")
        self.main_english_final_text.setWordWrap(True)
        subtitle_layout.addWidget(self.main_english_final_label)
        subtitle_layout.addWidget(self.main_english_final_text)
        
        self.main_layout.addWidget(subtitle_frame)

        # API Configuration
        config_group_box = QFrame()
        config_group_box.setFrameShape(QFrame.Shape.StyledPanel)
        config_group_box.setFrameShadow(QFrame.Shadow.Raised)
        config_layout = QVBoxLayout(config_group_box)
        config_layout.addWidget(QLabel("<h3>API Configuration</h3>"))

        stt_layout = QHBoxLayout()
        stt_layout.addWidget(QLabel("STT Engine:"))
        self.stt_engine_combo.addItem("Google", "google")
        self.stt_engine_combo.addItem("Whisper", "whisper")
        stt_layout.addWidget(self.stt_engine_combo)
        config_layout.addLayout(stt_layout)

        google_api_key_layout = QHBoxLayout()
        google_api_key_layout.addWidget(QLabel("Google API Key:"))
        self.google_api_key_input.setPlaceholderText("Enter Google API Key")
        self.google_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        google_api_key_layout.addWidget(self.google_api_key_input)
        config_layout.addLayout(google_api_key_layout)

        translation_layout = QHBoxLayout()
        translation_layout.addWidget(QLabel("Translation Engine:"))
        self.translation_engine_combo.addItem("DeepL", "deepl")
        self.translation_engine_combo.addItem("Google Translate", "google")
        self.translation_engine_combo.addItem("MarianMT", "marianmt")
        translation_layout.addWidget(self.translation_engine_combo)
        config_layout.addLayout(translation_layout)

        deepl_api_key_layout = QHBoxLayout()
        deepl_api_key_layout.addWidget(QLabel("DeepL API Key:"))
        self.deepl_api_key_input.setPlaceholderText("Enter DeepL API Key")
        self.deepl_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        deepl_api_key_layout.addWidget(self.deepl_api_key_input)
        config_layout.addLayout(deepl_api_key_layout)

        self.save_config_btn.clicked.connect(self.save_config)
        config_layout.addWidget(self.save_config_btn)

        self.main_layout.addWidget(config_group_box)

        # Set dark theme
        self.set_dark_theme()

    def set_dark_theme(self):
        app.setStyle("Fusion")
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        app.setPalette(dark_palette)

    def update_status(self, message, is_error=False):
        self.status_label.setText(f"Status: {message}")
        self.status_label.setStyleSheet(f"font-size: 1.1em; color: {'red' if is_error else 'white'};")

    def on_websocket_connected(self):
        self.update_status("Connected to backend.", False)
        self.listening_indicator.hide()

    def on_websocket_disconnected(self):
        self.update_status("Disconnected. Retrying...", True)
        self.listening_indicator.hide()

    def handle_websocket_message(self, data):
        if data.get("type") == "realtime":
            self.main_hindi_realtime_text.setText(data.get("hindi", ""))
            self.main_hindi_final_text.setText("")
            self.main_english_final_text.setText("")
            if self.overlay_window:
                self.overlay_window.update_subtitles(data)
        elif data.get("type") == "final":
            self.main_hindi_final_text.setText(data.get("hindi", ""))
            self.main_english_final_text.setText(data.get("english", ""))
            self.main_hindi_realtime_text.setText("") # Clear real-time when final arrives
            if self.overlay_window:
                self.overlay_window.update_subtitles(data)
        elif data.get("type") == "status":
            self.update_status(data.get("english", ""), False)
            if self.overlay_window:
                self.overlay_window.update_subtitles(data) # Clear overlay on status
        elif data.get("type") == "error":
            self.update_status(data.get("english", ""), True)
            if self.overlay_window:
                self.overlay_window.update_subtitles(data) # Clear overlay on error

    def start_listening(self):
        device_info = self.audio_input_combo.currentData()
        if not isinstance(device_info, dict) or device_info.get("index") is None:
            self.update_status("No valid audio input device selected.", True)
            return
        device_id = device_info['index'] # Send only the integer index
        self.update_status("Starting live audio...", False)
        self.listening_indicator.show()
        self.ws_client.send_message({"type": "start_live_audio", "device": device_id})

    def stop_listening(self):
        self.update_status("Stopping live audio...", False)
        self.listening_indicator.hide()
        self.ws_client.send_message({"type": "stop_live_audio"})

    def choose_audio_file(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(self, "Select Audio File", "", "Audio Files (*.mp3 *.wav *.m4a)")
        if file_path:
            self.audio_file_path_label.setText(file_path)
            self.selected_audio_file = file_path
        else:
            self.selected_audio_file = None
            self.audio_file_path_label.setText("No file chosen")

    def upload_audio_file(self):
        if not hasattr(self, 'selected_audio_file') or not self.selected_audio_file:
            self.update_status("Please select a file first.", True)
            return

        self.update_status("Uploading file...", False)
        self.listening_indicator.hide()
        try:
            with open(self.selected_audio_file, "rb") as f:
                audio_data = f.read()
            self.ws_client.send_binary(audio_data)
        except Exception as e:
            self.update_status(f"Error reading file: {e}", True)

    def open_overlay(self):
        if not self.overlay_window:
            self.overlay_window = OverlayWindow()
        self.overlay_window.showFullScreen() # Show as fullscreen overlay

    def test_audio_input(self):
        device_info = self.audio_input_combo.currentData()
        if not isinstance(device_info, dict) or device_info.get("index") is None:
            self.update_status("No valid audio input device selected for testing.", True)
            return
        
        device_id = device_info['index']
        samplerate = int(device_info['default_samplerate']) # Use the device's default sample rate

        self.update_status(f"Testing audio input from device ID: {device_id} (Sample Rate: {samplerate})...", False)
        try:
            # Record a short audio snippet
            duration = 3  # seconds
            self.update_status(f"Recording {duration} seconds from device {device_id} at {samplerate} Hz...", False)
            audio_data = sd.rec(int(samplerate * duration), samplerate=samplerate, channels=1, device=device_id, dtype='float32')
            sd.wait() # Wait for recording to finish

            self.update_status("Recording complete. Playing back...", False)
            sd.play(audio_data, samplerate)
            sd.wait() # Wait for playback to finish
            self.update_status("Audio test complete. If you heard your voice, the microphone is working.", False)
        except Exception as e:
            self.update_status(f"Audio test failed: {e}. Check device and permissions.", True)

    def load_config(self):
        config = json.loads(localStorage.getItem("apiConfig")) if "apiConfig" in localStorage else {}
        self.stt_engine_combo.setCurrentText(config.get("sttEngine", "Google"))
        self.google_api_key_input.setText(config.get("googleApiKey", ""))
        self.translation_engine_combo.setCurrentText(config.get("translationEngine", "DeepL"))
        self.deepl_api_key_input.setText(config.get("deeplApiKey", ""))

    def save_config(self):
        config = {
            "sttEngine": self.stt_engine_combo.currentText(),
            "googleApiKey": self.google_api_key_input.text(),
            "translationEngine": self.translation_engine_combo.currentText(),
            "deeplApiKey": self.deepl_api_key_input.text(),
        }
        # localStorage is a browser concept, for PyQt we'll use QSettings or a simple JSON file
        # For now, let's just print it. For a real app, save to a config file.
        print("Saving config:", config)
        self.update_status("Configuration saved (to console for now).", False)

    def closeEvent(self, event):
        self.ws_client.stop()
        if self.overlay_window:
            self.overlay_window.close()
        event.accept()

# Mock localStorage for PyQt environment
class LocalStorage:
    def __init__(self):
        self._data = {}

    def getItem(self, key):
        return self._data.get(key)

    def setItem(self, key, value):
        self._data[key] = value

    def __contains__(self, key):
        return key in self._data

localStorage = LocalStorage()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())