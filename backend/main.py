import asyncio
import numpy as np
from faster_whisper import WhisperModel
from transformers import MarianMTModel, MarianTokenizer
import websockets
import json
import concurrent.futures
import logging
import io
from pydub import AudioSegment
import sounddevice as sd # Keep sounddevice for live input option

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
WS_SERVER_PORT = 8768

# Global variable to hold the main event loop
_main_event_loop = None

# Queues for inter-task communication
audio_queue = asyncio.Queue()
subtitle_output_queue = asyncio.Queue() # New queue for processed subtitles

# Set of connected WebSocket clients
connected_clients = set()

# Audio processing constants
SAMPLE_RATE = 16000 # Hz
CHUNK_SIZE_MS = 1000 # milliseconds (1 second chunks for file processing)

async def register_client(websocket):
    connected_clients.add(websocket)
    logging.info(f"Client {websocket.remote_address} connected. Total clients: {len(connected_clients)}")

async def unregister_client(websocket):
    connected_clients.remove(websocket)
    logging.info(f"Client {websocket.remote_address} disconnected. Total clients: {len(connected_clients)}")

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

async def send_subtitle_to_all_clients(data):
    if not connected_clients:
        logging.warning("No WebSocket clients connected to send subtitles.")
        return

    message = json.dumps(data)
    # Send to all connected clients
    disconnected_clients = set()
    for client in connected_clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosedOK:
            disconnected_clients.add(client)
        except Exception as e:
            logging.error(f"Error sending to client {client.remote_address}: {e}")
            disconnected_clients.add(client)
    for client in disconnected_clients:
        await unregister_client(client) # Clean up disconnected clients

async def process_subtitles_for_frontend():
    while True:
        hindi_text, english_text = await subtitle_output_queue.get()
        if hindi_text or english_text:
            logging.info(f"🎧 HINDI (sending to frontend): {hindi_text}")
            logging.info(f"🌐 ENGLISH (sending to frontend): {english_text}")
            await send_subtitle_to_all_clients({"hindi": hindi_text, "english": english_text})
        else:
            logging.info("Empty subtitle received, not sending to frontend.")
        subtitle_output_queue.task_done()

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
            processed_segments = await loop.run_in_executor(
                pool,
                blocking_transcribe_and_translate,
                audio_data
            )
            for hindi, english in processed_segments:
                await subtitle_output_queue.put((hindi, english))
            audio_queue.task_done()

# Live microphone input callback
def live_audio_callback(indata, frames, time, status):
    if status:
        logging.warning(f"Sounddevice status: {status}")
    audio_bytes = indata.copy().tobytes()
    if len(audio_bytes) > 0:
        if _main_event_loop and _main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(audio_queue.put(audio_bytes), _main_event_loop)
        else:
            logging.error("Main event loop not running or not set in callback.")
    else:
        logging.info("No live audio data received in callback.")

async def start_live_microphone_input():
    try:
        devices = sd.query_devices()
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        logging.info("\nAvailable input devices:")
        for i, device in enumerate(input_devices):
            logging.info(f"{i}: {device['name']}")

        default_input_device_info = sd.query_devices(kind='input')
        logging.info(f"\nUsing default input device: {default_input_device_info['name']}")

        with sd.InputStream(callback=live_audio_callback, channels=1, samplerate=SAMPLE_RATE, dtype='float32'):
            logging.info("🎙️ Live microphone input started...")
            await asyncio.Future() # Keep stream open indefinitely
    except Exception as e:
        logging.critical(f"Fatal error in live audio input stream: {e}")
        # Consider sending an error message to frontend clients
        exit(1)

async def process_uploaded_audio_data(audio_bytes_data):
    try:
        # pydub can read from a BytesIO object
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes_data))
        audio_segment = audio_segment.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2) # 16-bit samples

        total_length_ms = len(audio_segment)
        logging.info(f"Processing uploaded audio (Duration: {total_length_ms / 1000} seconds)")

        # Send a "start processing" message to frontend
        await send_subtitle_to_all_clients({"hindi": "", "english": "Processing uploaded audio..."})

        for i in range(0, total_length_ms, CHUNK_SIZE_MS):
            chunk = audio_segment[i:i + CHUNK_SIZE_MS]
            if not chunk:
                continue

            # Convert chunk to raw audio bytes (PCM, 16-bit, mono)
            raw_audio_data = np.array(chunk.get_array_of_samples()).astype(np.float32).tobytes()
            
            if raw_audio_data:
                await audio_queue.put(raw_audio_data)
            await asyncio.sleep(CHUNK_SIZE_MS / 1000.0) # Simulate real-time processing speed
        
        logging.info("Finished processing uploaded audio.")
        await send_subtitle_to_all_clients({"hindi": "", "english": "Finished processing audio."})

    except Exception as e:
        logging.error(f"Error processing uploaded audio: {e}")
        await send_subtitle_to_all_clients({"hindi": "", "english": f"Error processing audio: {e}"})

async def websocket_handler(websocket, *args, **kwargs):
    logging.info(f"WebSocket handler called with args: {args}, kwargs: {kwargs}")
    path = kwargs.get('path') # Extract path if it's passed as a keyword argument
    if path is None and len(args) > 1: # If path is not in kwargs, check positional arguments
        path = args[1] # Assuming path is the second positional argument

    await register_client(websocket)
    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    control_message = json.loads(message)
                    if control_message.get("type") == "start_live_audio":
                        logging.info("Received 'start_live_audio' command from frontend.")
                        # This assumes live audio is handled by a separate task that can be started/stopped.
                        # For simplicity, we'll just log it here. The `run.sh` will manage starting live input.
                        await send_subtitle_to_all_clients({"hindi": "", "english": "Live audio input active."})
                    elif control_message.get("type") == "audio_file_upload_start":
                        logging.info("Received 'audio_file_upload_start' command. Preparing for file data.")
                        # Frontend will send binary audio data next
                        await send_subtitle_to_all_clients({"hindi": "", "english": "Receiving audio file..."})
                except json.JSONDecodeError:
                    logging.warning(f"Received non-JSON string message: {message}")
            elif isinstance(message, bytes):
                logging.info(f"Received binary audio data of size: {len(message)} bytes")
                # Assuming the entire file is sent as one binary message for simplicity
                # For large files, this would need chunking and accumulation
                asyncio.create_task(process_uploaded_audio_data(message))
            else:
                logging.warning(f"Received unknown message type: {type(message)}")
    except websockets.exceptions.ConnectionClosedOK:
        logging.info(f"Client {websocket.remote_address} disconnected gracefully.")
    except Exception as e:
        logging.error(f"WebSocket handler error for {websocket.remote_address}: {e}")
    finally:
        await unregister_client(websocket)

async def main():
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop()

    # Start the core processing workers
    asyncio.create_task(audio_processing_worker())
    asyncio.create_task(process_subtitles_for_frontend())

    # Start the WebSocket server
    websocket_server = await websockets.serve(websocket_handler, "0.0.0.0", WS_SERVER_PORT)
    logging.info(f"🌐 WebSocket Server running at ws://localhost:{WS_SERVER_PORT}")

    # Start live microphone input as a background task
    # This will run concurrently with the WebSocket server and file processing
    asyncio.create_task(start_live_microphone_input())

    await asyncio.Future() # Keep the main loop running indefinitely

if __name__ == "__main__":
    asyncio.run(main())