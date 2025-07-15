#!/bin/bash

# Function to kill processes on specific ports
kill_port_processes() {
    PORT=$1
    PIDS=$(lsof -t -i :$PORT)
    if [ -n "$PIDS" ]; then
        echo "Killing processes on port $PORT: $PIDS"
        kill -9 $PIDS 2>/dev/null
        sleep 1
    fi
}

# Kill processes on known ports before starting
kill_port_processes 8768 # WebSocket server port
kill_port_processes 8100 # HTTP server port

# Function to kill all background processes started by this script
cleanup() {
    echo "Stopping all background processes..."
    kill $WS_SERVER_PID $MAIN_LISTENER_PID $HTTP_SERVER_PID 2>/dev/null
    echo "Processes stopped."
    exit 0
}

# Trap SIGINT (Ctrl+C) to call the cleanup function
trap cleanup SIGINT

# Navigate to backend and start WebSocket server
cd backend
python ws_server.py &

# Store the PID of the WebSocket server
WS_SERVER_PID=$!

# Wait a moment for the WebSocket server to start
sleep 5

# Start real-time mic listener
python main.py &

# Store the PID of the main listener
MAIN_LISTENER_PID=$!

# Navigate to frontend and start HTTP server
cd ../frontend
python3 -m http.server 8100 &

# Store the PID of the HTTP server
HTTP_SERVER_PID=$!

echo "WebSocket Server PID: $WS_SERVER_PID"
echo "Main Listener PID: $MAIN_LISTENER_PID"
echo "HTTP Server PID: $HTTP_SERVER_PID"
echo "Open http://localhost:8100 in your browser (fullscreen on projector)"

# Keep the script running until manually terminated
wait # Wait for any background process to exit, then cleanup will be called on SIGINT