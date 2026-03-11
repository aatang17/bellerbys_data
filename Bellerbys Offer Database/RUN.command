#!/bin/bash
# Double-click this (Mac) to start the app and open it in your browser.
# First time: takes 1–2 minutes to install. Leave the window open while using the app.

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "First-time setup: creating environment..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
else
  source venv/bin/activate
fi

if [ ! -f ".env" ]; then
  echo ""
  echo "*** FIRST-TIME SETUP ***"
  echo "Copy .env.example to .env and add your Gemini API key."
  echo "Get a free key at: https://aistudio.google.com/app/apikey"
  echo ""
  cp -n .env.example .env 2>/dev/null || true
  open -e .env 2>/dev/null || echo "Open the .env file in this folder and add GEMINI_API_KEY=your_key"
  echo "After saving .env, double-click RUN.command again."
  exit 0
fi

echo "Starting app... Open http://localhost:8000 in your browser."
sleep 2
open "http://localhost:8000" 2>/dev/null || true
uvicorn app:app --host 127.0.0.1 --port 8000
