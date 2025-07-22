import os
import logging
from dotenv import load_dotenv
from google.cloud import speech
import torch
from faster_whisper import WhisperModel
import numpy as np

load_dotenv(dotenv_path='../config/.env')

class STTEngine:
    def __init__(self, language_code="hi-IN"):
        self.language_code = language_code
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        if self.google_api_key and self.google_api_key != "your_google_api_key":
            self.client = speech.SpeechClient(client_options={"api_key": self.google_api_key})
        else:
            logging.warning("Google API key not found or is a placeholder. Google STT will not work.")
            self.client = None
        self._whisper_model = None

    @property
    def whisper_model(self):
        if self._whisper_model is None:
            logging.info("Loading Whisper model for fallback (CPU only)...")
            device = "cpu" # Force CPU usage for PyInstaller compatibility
            self._whisper_model = WhisperModel("small", device=device, compute_type="int8")
            logging.info("Whisper model loaded (CPU).")
        return self._whisper_model

    def transcribe_google(self, audio_data: bytes) -> str:
        logging.info("Transcribing with Google STT...")
        audio = speech.RecognitionAudio(content=audio_data)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=self.language_code,
        )
        response = self.client.recognize(config=config, audio=audio)
        if response.results and response.results[0].alternatives:
            return response.results[0].alternatives[0].transcript
        return ""

    def transcribe_whisper(self, audio_data: bytes) -> str:
        logging.info("Transcribing with Whisper STT...")
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self.whisper_model.transcribe(audio_np, beam_size=5, language="hi")
        return " ".join([segment.text for segment in segments])

    def transcribe(self, audio_data: bytes) -> str:
        if self.client:
            try:
                transcript = self.transcribe_google(audio_data)
                if transcript:
                    logging.info("Google STT successful.")
                    return transcript
                else:
                    raise ValueError("Empty transcript from Google")
            except Exception as e:
                logging.warning(f"Google STT failed: {e}. Falling back to Whisper.")
                return self.transcribe_whisper(audio_data)
        else:
            return self.transcribe_whisper(audio_data)