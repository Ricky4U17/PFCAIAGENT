@echo off
REM PFC AI Agent — Windows startup script
REM Usage: Double-click start.bat or run from terminal

echo.
echo ========================================
echo   PFC AI Agent v2.2  -- Local Start
echo ========================================
echo.

REM Check for API key
if "%ANTHROPIC_API_KEY%"=="" (
  echo Note: ANTHROPIC_API_KEY not set.
  echo PDF extraction will be unavailable.
  echo All other features work without it.
  echo.
)

echo [1/4] Setting up Python virtual environment...
cd backend
if not exist venv (
  python -m venv venv
  echo       Created virtual environment
)

call venv\Scripts\activate.bat
pip install -r requirements.txt -q --disable-pip-version-check

echo [2/4] Starting backend on http://localhost:8000 ...
start "PFC-Backend" cmd /k "venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

timeout /t 3 /nobreak >nul

echo [3/4] Installing frontend dependencies...
cd ..\frontend
call npm install --silent

echo [4/4] Starting frontend on http://localhost:5173 ...
start "PFC-Frontend" cmd /k "npm run dev"

timeout /t 3 /nobreak >nul
echo.
echo ========================================
echo  PFC AI Agent is running!
echo.
echo  Frontend: http://localhost:5173
echo  Backend:  http://localhost:8000
echo  API docs: http://localhost:8000/docs
echo.
echo  Close the two server windows to stop.
echo ========================================
echo.
pause
