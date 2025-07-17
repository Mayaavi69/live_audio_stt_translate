import asyncio
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from transformers import MarianMTModel, MarianTokenizer
import websockets
import json
import concurrent.futures
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load STT model
try:
    whisper_model = WhisperModel("medium", compute_type="float16")
    logging.info("Faster-Whisper model loaded successfully.")
except Exception as e:
    logging.error(f"Error loading Whisper model: {e}")
    exit(1)

# Load translation model
model_name = "Helsinki-NLP/opus-mt-hi-en"
try:
    tokenizer = MarianTokenizer.from_pretrained(model_name)
    translator = MarianMTModel.from_pretrained(model_name)
    logging.info(f"Translation model '{model_name}' loaded successfully.")
except Exception as e:
    logging.error(f"Error loading translation model '{model_name}': {e}")
    exit(1)

# WebSocket endpoint
WS_SERVER = "ws://localhost:8768"

# Global variable to hold the main event loop
_main_event_loop = None

# Queues for inter-task communication
audio_queue = asyncio.Queue()
subtitle_output_queue = asyncio.Queue() # New queue for processed subtitles

# Persistent WebSocket connection for sending subtitles
websocket_client = None

async def connect_to_websocket():
    global websocket_client
    while True:
        try:
            logging.info(f"Attempting to connect to WebSocket server at {WS_SERVER}...")
            websocket_client = await websockets.connect(WS_SERVER)
            logging.info("Successfully connected to WebSocket server.")
            return
        except Exception as e:
            logging.error(f"WebSocket connection failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

def translate_hindi_to_english(text):
    if not text.strip():
        return ""
    try:
        tokens = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        translated = translator.generate(**tokens)
        return tokenizer.decode(translated[0], skip_special_tokens=True)
    except Exception as e:
        logging.error(f"Translation error for text '{text}': {e}")
        return "[Translation Error]"

async def send_subtitle_to_ws(data):
    global websocket_client
    if not websocket_client or not websocket_client.open:
        logging.warning("WebSocket client not connected. Attempting to reconnect...")
        await connect_to_websocket() # Reconnect if not open

    try:
        await websocket_client.send(json.dumps(data))
        logging.debug(f"Sent data to WebSocket: {data}")
    except websockets.exceptions.ConnectionClosedOK:
        logging.warning("WebSocket connection closed gracefully. Reconnecting...")
        websocket_client = None # Mark as closed
        await connect_to_websocket()
        await websocket_client.send(json.dumps(data)) # Try sending again after reconnect
    except Exception as e:
        logging.error(f"Error sending data to WebSocket: {e}")
        websocket_client = None # Mark as closed to trigger reconnect

async def process_subtitles_for_frontend(): # Renamed for clarity
    while True:
        hindi_text, english_text = await subtitle_output_queue.get()
        if hindi_text or english_text: # Only send if there's actual text
            logging.info(f"🎧 HINDI (sending to frontend): {hindi_text}")
            logging.info(f"🌐 ENGLISH (sending to frontend): {english_text}")
            await send_subtitle_to_ws({"hindi": hindi_text, "english": english_text})
        else:
            logging.info("Empty subtitle received, not sending to frontend.")
        subtitle_output_queue.task_done()

# This function will run the blocking STT and translation
def blocking_transcribe_and_translate(audio_data):
    audio_np = np.frombuffer(audio_data, dtype=np.float32)
    logging.debug(f"Processing audio chunk of size: {len(audio_np)} samples")
    segments = []
    try:
        segments, _ = whisper_model.transcribe(audio_np, language="hi", task="transcribe")
    except Exception as e:
        logging.error(f"Whisper transcription error: {e}")
        return []

    results = []
    segment_count = 0
    for segment in segments:
        segment_count += 1
        hindi = segment.text
        english = translate_hindi_to_english(hindi)
        results.append((hindi, english))
    logging.debug(f"Whisper produced {segment_count} segments.")
    return results

async def audio_processing_worker():
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        while True:
            audio_data = await audio_queue.get()
            # Run the blocking operations in a separate thread
            processed_segments = await loop.run_in_executor(
                pool,
                blocking_transcribe_and_translate,
                audio_data
            )
            for hindi, english in processed_segments:
                await subtitle_output_queue.put((hindi, english))
            audio_queue.task_done()

# Record from mic - this callback should be as fast as possible
def callback(indata, frames, time, status):
    if status:
        logging.warning(f"Sounddevice status: {status}")
    audio_bytes = indata.copy().tobytes()
    # Check if audio_bytes has actual data
    if len(audio_bytes) > 0:
        # Use the stored main event loop
        if _main_event_loop and _main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(audio_queue.put(audio_bytes), _main_event_loop)
        else:
            logging.error("Main event loop not running or not set in callback.")
    else:
        logging.info("No audio data received in callback.")

async def start_listening_async():
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop() # Store the running loop

    # Get available audio devices
    try:
        devices = sd.query_devices()
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        logging.info("\nAvailable input devices:")
        for i, device in enumerate(input_devices):
            logging.info(f"{i}: {device['name']}")

        default_input_device_info = sd.query_devices(kind='input')
        logging.info(f"\nUsing default input device: {default_input_device_info['name']}")
    except Exception as e:
        logging.error(f"Error querying audio devices: {e}")
        logging.warning("Proceeding without device enumeration. Ensure a default input device is available.")

    # Establish WebSocket connection before starting audio stream
    await connect_to_websocket()

    try:
        with sd.InputStream(callback=callback, channels=1, samplerate=16000, dtype='float32'):
            logging.info("🎙️ Listening...")
            # Start the worker tasks
            asyncio.create_task(audio_processing_worker())
            asyncio.create_task(process_subtitles_for_frontend())
            while True:
                await asyncio.sleep(1)
    except Exception as e:
        logging.critical(f"Fatal error in audio input stream: {e}")
        # Attempt to gracefully close WebSocket connection on critical error
        if websocket_client and websocket_client.open:
            await websocket_client.close()
        exit(1)


if __name__ == "__main__":
    asyncio.run(start_listening_async())