#!/bin/bash

# Function to kill processes on specific ports
kill_port_processes() {
    PORT=$1
    PIDS=$(lsof -t -i :$PORT 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "Killing processes on port $PORT: $PIDS"
        kill -9 $PIDS 2>/dev/null
        sleep 1
    fi
}

# Cleanup function for Docker
cleanup_docker() {
    echo "Stopping Docker containers..."
    docker-compose down
    echo "Docker containers stopped."
    exit 0
}

# Cleanup function for local execution
cleanup_local() {
    echo "Stopping all background processes..."
    kill $WS_SERVER_PID $HTTP_SERVER_PID 2>/dev/null
    echo "Processes stopped."
    exit 0
}

# Check for command-line argument
if [ "$1" == "docker" ]; then
    echo "Running with Docker..."
    trap cleanup_docker SIGINT
    
    # Ensure .env file exists
    if [ ! -f "config/.env" ]; then
        echo "config/.env file not found. Please create it."
        exit 1
    fi

    # Kill processes on known ports before starting
    kill_port_processes 8768
    kill_port_processes 8100

    docker compose up --build
    
    # Keep the script running until manually terminated
    wait

else
    echo "Running locally..."
    trap cleanup_local SIGINT

    # Kill processes on known ports before starting
    kill_port_processes 8768
    kill_port_processes 8100

    # Create and activate virtual environment
    VENV_DIR=".venv"
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi

    echo "Activating virtual environment..."
    source "$VENV_DIR"/bin/activate

    # Install Python dependencies
    echo "Installing Python dependencies from backend/requirements.txt..."
    pip install -r backend/requirements.txt

    # Navigate to backend and start WebSocket server
    cd backend
    "$VENV_DIR"/bin/python backend/main.py &
    WS_SERVER_PID=$!
    cd ..

    # Wait a moment for the backend to start
    sleep 5

    # Navigate to frontend and start HTTP server
    cd frontend
    "$VENV_DIR"/bin/python3 -m http.server 8100 &
    HTTP_SERVER_PID=$!
    cd ..

    echo "WebSocket Server PID: $WS_SERVER_PID"
    echo "HTTP Server PID: $HTTP_SERVER_PID"
    echo "Open http://localhost:8100 in your browser"

    # Keep the script running until manually terminated
    wait
fi