import asyncio
import numpy as np
import websockets
import json
import concurrent.futures
import logging
import io
import os # Import os module
import torch # Import torch
from pydub import AudioSegment
from datetime import datetime, timezone

from stt_engine import STTEngine
from translate_engine import TranslationEngine
from RealtimeSTT import AudioToTextRecorder

# Force CPU usage for Torch and related libraries
os.environ["CUDA_VISIBLE_DEVICES"] = ""

# Force CPU usage for Torch and related libraries
os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.set_num_threads(1) # Limit Torch to single thread for CPU
torch.set_default_device('cpu') # Explicitly set default device to CPU

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize engines
stt_engine = STTEngine()
translation_engine = TranslationEngine()

# WebSocket endpoint
WS_SERVER_PORT = 8768

# Global variable to hold the main event loop
_main_event_loop = None

# Queues for inter-task communication
# audio_queue is no longer needed for live audio with RealtimeSTT
subtitle_output_queue = asyncio.Queue()
realtime_subtitle_queue = asyncio.Queue() # New queue for real-time subtitles

# Set of connected WebSocket clients
connected_clients = set()
live_audio_task = None
realtime_stt_recorder = None # Global for RealtimeSTT recorder

# Audio processing constants (might be less relevant for RealtimeSTT's internal handling)
SAMPLE_RATE = 16000  # Hz
CHUNK_SIZE_MS = 1000  # milliseconds

async def register_client(websocket):
    connected_clients.add(websocket)
    logging.info(f"Client {websocket.remote_address} connected. Total clients: {len(connected_clients)}")

async def unregister_client(websocket):
    connected_clients.remove(websocket)
    logging.info(f"Client {websocket.remote_address} disconnected. Total clients: {len(connected_clients)}")

async def send_subtitle_to_all_clients(data):
    if not connected_clients:
        logging.warning("No WebSocket clients connected to send subtitles.")
        return

    message = json.dumps(data)
    disconnected_clients = set()
    for client in connected_clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected_clients.add(client)
        except Exception as e:
            logging.error(f"Error sending to client {client.remote_address}: {e}")
            disconnected_clients.add(client)
    
    for client in disconnected_clients:
        if client in connected_clients:
            await unregister_client(client)

async def process_subtitles_for_frontend():
    while True:
        # This queue will now receive final transcriptions from RealtimeSTT
        hindi_text, english_text = await subtitle_output_queue.get()
        if hindi_text or english_text:
            timestamp = datetime.now(timezone.utc).isoformat()
            logging.info(f"🎧 HINDI (Final): {hindi_text}")
            logging.info(f"🌐 ENGLISH (Final): {english_text}")
            await send_subtitle_to_all_clients({
                "timestamp": timestamp,
                "hindi": hindi_text,
                "english": english_text,
                "source": "mic",
                "type": "final" # Indicate this is a final transcription
            })
        else:
            logging.info("Empty final subtitle received, not sending.")
        subtitle_output_queue.task_done()

async def process_realtime_subtitles_for_frontend():
    while True:
        realtime_text = await realtime_subtitle_queue.get()
        if realtime_text:
            timestamp = datetime.now(timezone.utc).isoformat()
            logging.debug(f"🎧 HINDI (Realtime): {realtime_text}") # Use debug for frequent updates
            # Translate real-time text if needed, or send as is
            # For now, sending as is, frontend can decide to display or not
            await send_subtitle_to_all_clients({
                "timestamp": timestamp,
                "hindi": realtime_text,
                "english": translation_engine.translate(realtime_text), # Translate real-time text
                "source": "mic",
                "type": "realtime" # Indicate this is a real-time transcription
            })
        realtime_subtitle_queue.task_done()

async def start_realtime_stt_input(device_id=None):
    global realtime_stt_recorder
    if realtime_stt_recorder:
        realtime_stt_recorder.shutdown() # Ensure previous recorder is shut down

    logging.info(f"Initializing RealtimeSTT recorder for device: {device_id}")
    recorder_config = {
        'use_microphone': True,
        'spinner': False,
        'model': "small", # Use a smaller model for real-time if needed, or configure
        'language': "hi", # Assuming Hindi input based on STTEngine
        'realtime_model_type': "tiny", # Faster model for real-time
        'device': "cpu", # Force CPU usage for PyInstaller compatibility
        'vad_enabled': False, # Disable VAD to bypass Silero VAD
        'input_device_index': device_id # Pass the selected device ID
    }
    
    realtime_stt_recorder = AudioToTextRecorder(**recorder_config)
    logging.info("🎙️ RealtimeSTT recorder started.")
    
    try:
        while True:
            # Get real-time transcription
            realtime_text, _ = realtime_stt_recorder.text(realtime=True)
            if realtime_text:
                await realtime_subtitle_queue.put(realtime_text)

            # Get final transcription
            final_text, _ = realtime_stt_recorder.text()
            if final_text:
                hindi_text = final_text
                english_text = translation_engine.translate(hindi_text)
                await subtitle_output_queue.put((hindi_text, english_text))

    except asyncio.CancelledError:
        logging.info("RealtimeSTT input task cancelled.")
    except Exception as e:
        logging.error(f"Error in RealtimeSTT input: {e}", exc_info=True)
        await send_subtitle_to_all_clients({"hindi": "", "english": f"Error in STT: {e}", "type": "error"})
    finally:
        if realtime_stt_recorder:
            realtime_stt_recorder.shutdown()
            realtime_stt_recorder = None
            logging.info("RealtimeSTT recorder shut down.")

def blocking_transcribe_and_translate(audio_data):
    hindi_text = stt_engine.transcribe(audio_data)
    if not hindi_text.strip():
        return "", "" # Return two empty strings if no transcription
    
    english_text = translation_engine.translate(hindi_text)
    return hindi_text, english_text # Return the two values directly

async def process_uploaded_audio_data(audio_bytes_data):
    try:
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes_data))
        audio_segment = audio_segment.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)

        total_length_ms = len(audio_segment)
        logging.info(f"Processing uploaded audio (Duration: {total_length_ms / 1000}s)")

        await send_subtitle_to_all_clients({"hindi": "", "english": "Processing uploaded audio...", "type": "status"})

        # For uploaded audio, we can still use the existing STTEngine for batch processing
        # or feed it to RealtimeSTT if it supports feeding raw bytes directly for non-mic input.
        # For simplicity, let's keep the existing batch processing for uploaded files for now.
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            hindi_text, english_text = await loop.run_in_executor(
                pool,
                blocking_transcribe_and_translate,
                audio_segment.raw_data # Pass raw audio data for transcription
            )
            await subtitle_output_queue.put((hindi_text, english_text))
        
        logging.info("Finished processing uploaded audio.")
        await send_subtitle_to_all_clients({"hindi": "", "english": "Finished processing audio.", "type": "status"})

    except Exception as e:
        logging.error(f"Error processing uploaded audio: {e}")
        await send_subtitle_to_all_clients({"hindi": "", "english": f"Error: {e}", "type": "error"})

async def websocket_handler(websocket):
    await register_client(websocket)
    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    control_message = json.loads(message)
                    if control_message.get("type") == "start_live_audio":
                        global live_audio_task
                        if live_audio_task:
                            live_audio_task.cancel() # Cancel existing task if any
                            await live_audio_task # Wait for it to finish cancelling
                        device_id = control_message.get("device")
                        logging.info(f"Received 'start_live_audio' command for device {device_id}. Starting RealtimeSTT.")
                        live_audio_task = asyncio.create_task(start_realtime_stt_input(device_id))
                        await send_subtitle_to_all_clients({"hindi": "", "english": "Live audio input started with RealtimeSTT.", "type": "status"})
                    elif control_message.get("type") == "stop_live_audio": # Add a stop command
                        if live_audio_task:
                            live_audio_task.cancel()
                            await live_audio_task
                            live_audio_task = None
                        await send_subtitle_to_all_clients({"hindi": "", "english": "Live audio input stopped.", "type": "status"})
                except json.JSONDecodeError:
                    logging.warning(f"Received non-JSON message: {message}")
            elif isinstance(message, bytes):
                logging.info(f"Received binary audio data of size: {len(message)} bytes")
                asyncio.create_task(process_uploaded_audio_data(message))
    except websockets.exceptions.ConnectionClosed:
        logging.info(f"Client {websocket.remote_address} disconnected.")
    finally:
        await unregister_client(websocket)
        # If this was the last client and live audio is running, consider stopping it
        if not connected_clients and live_audio_task:
            live_audio_task.cancel()
            await live_audio_task
            live_audio_task = None

async def main():
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop()

    # Start workers for processing subtitles
    asyncio.create_task(process_subtitles_for_frontend())
    asyncio.create_task(process_realtime_subtitles_for_frontend()) # New worker for real-time subtitles
    
    server = await websockets.serve(websocket_handler, "0.0.0.0", WS_SERVER_PORT)
    logging.info(f"🌐 WebSocket Server running at ws://localhost:{WS_SERVER_PORT}")

    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"Unhandled exception in main application: {e}", exc_info=True)