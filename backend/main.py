import asyncio
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from transformers import MarianMTModel, MarianTokenizer
import websockets
import json # Import json for sending structured data

# Load STT model
whisper_model = WhisperModel("medium", compute_type="float16")

# Load translation model
model_name = "Helsinki-NLP/opus-mt-hi-en"
tokenizer = MarianTokenizer.from_pretrained(model_name)
translator = MarianMTModel.from_pretrained(model_name)

# WebSocket endpoint
WS_SERVER = "ws://localhost:8768"

import asyncio
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from transformers import MarianMTModel, MarianTokenizer
import websockets
import json # Import json for sending structured data
import concurrent.futures # For ThreadPoolExecutor

# Global variable to hold the main event loop
_main_event_loop = None

import asyncio
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from transformers import MarianMTModel, MarianTokenizer
import websockets
import json # Import json for sending structured data
import concurrent.futures # For ThreadPoolExecutor

# Load STT model
whisper_model = WhisperModel("medium", compute_type="float16")

# Load translation model
model_name = "Helsinki-NLP/opus-mt-hi-en"
tokenizer = MarianTokenizer.from_pretrained(model_name)
translator = MarianMTModel.from_pretrained(model_name)

# WebSocket endpoint
WS_SERVER = "ws://localhost:8768"

# Queues for inter-task communication
audio_queue = asyncio.Queue()
subtitle_output_queue = asyncio.Queue() # New queue for processed subtitles

def translate_hindi_to_english(text):
    tokens = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    translated = translator.generate(**tokens)
    return tokenizer.decode(translated[0], skip_special_tokens=True)

async def send_subtitle_to_ws(data): # Modified to send structured data
    try:
        async with websockets.connect(WS_SERVER) as ws:
            await ws.send(json.dumps(data)) # Send data as JSON string
    except Exception as e:
        print(f"WebSocket connection error: {e}")

async def process_subtitles_for_frontend(): # Renamed for clarity
    while True:
        hindi_text, english_text = await subtitle_output_queue.get()
        if hindi_text or english_text: # Only send if there's actual text
            print(f"🎧 HINDI (sending to frontend): {hindi_text}")
            print(f"🌐 ENGLISH (sending to frontend): {english_text}")
            await send_subtitle_to_ws({"hindi": hindi_text, "english": english_text})
        else:
            print("Empty subtitle received, not sending to frontend.")
        subtitle_output_queue.task_done()

# This function will run the blocking STT and translation
def blocking_transcribe_and_translate(audio_data):
    audio_np = np.frombuffer(audio_data, dtype=np.float32)
    print(f"Processing audio chunk of size: {len(audio_np)} samples")
    segments = []
    try:
        segments, _ = whisper_model.transcribe(audio_np, language="hi", task="transcribe")
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return []

    results = []
    segment_count = 0
    for segment in segments:
        segment_count += 1
        hindi = segment.text
        english = translate_hindi_to_english(hindi)
        results.append((hindi, english))
    print(f"Whisper produced {segment_count} segments.")
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
        print(f"Sounddevice status: {status}")
    audio_bytes = indata.copy().tobytes()
    # Check if audio_bytes has actual data
    if len(audio_bytes) > 0:
        # Use the stored main event loop
        if _main_event_loop and _main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(audio_queue.put(audio_bytes), _main_event_loop)
        else:
            print("Main event loop not running or not set in callback.")
    else:
        print("No audio data received in callback.")

async def start_listening_async():
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop() # Store the running loop

    # Get available audio devices
    devices = sd.query_devices()
    input_devices = [d for d in devices if d['max_input_channels'] > 0]
    print("\nAvailable input devices:")
    for i, device in enumerate(input_devices):
        print(f"{i}: {device['name']}")

    default_input_device_info = sd.query_devices(kind='input')
    print(f"\nUsing default input device: {default_input_device_info['name']}")

    with sd.InputStream(callback=callback, channels=1, samplerate=16000, dtype='float32'):
        print("🎙️ Listening...")
        # Start the worker tasks
        asyncio.create_task(audio_processing_worker())
        asyncio.create_task(process_subtitles_for_frontend())
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(start_listening_async())