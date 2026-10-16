#!/usr/bin/env bash

# Path to your backend script
SCRAPER_PATH="/mnt/SSD2/Seanime/ANIserver.py"

cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Shutting down local scraper API (PID: $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null
    fi
}

# Catch termination signals to stop python backend on exit
trap cleanup EXIT INT TERM

echo "Starting local scraper service on port 43222..."
python "$SCRAPER_PATH" &
SERVER_PID=$!

sleep 2

# Check if the Python backend is still running
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "❌ ERROR: Local scraper API failed to start or crashed! Aborting Seanime."
    exit 1
fi

echo "✅ Scraper API running (PID: $SERVER_PID)."
echo "Starting Seanime..."
/mnt/SSD2/Seanime/seanime
