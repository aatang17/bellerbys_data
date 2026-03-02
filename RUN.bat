@echo off
REM Double-click this (Windows) to start the app and open it in your browser.
REM First time: takes 1-2 minutes to install. Leave the window open while using the app.

cd /d "%~dp0"

if not exist "venv" (
  echo First-time setup: creating environment...
  python -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call venv\Scripts\activate.bat
)

if not exist ".env" (
  echo.
  echo *** FIRST-TIME SETUP ***
  echo Copy .env.example to .env and add your Gemini API key.
  echo Get a free key at: https://aistudio.google.com/app/apikey
  echo.
  if exist .env.example copy .env.example .env
  start notepad .env
  echo After saving .env, double-click RUN.bat again.
  pause
  exit /b 0
)

echo Starting app... Open http://localhost:8000 in your browser.
timeout /t 2 /nobreak >nul
start http://localhost:8000
uvicorn app:app --host 127.0.0.1 --port 8000
pause
