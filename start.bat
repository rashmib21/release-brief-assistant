@echo off
REM Build the frontend and start the app on http://localhost:8000 (Windows)
cd /d "%~dp0frontend" || exit /b 1
call npm ci || exit /b 1
call npm run build || exit /b 1
cd /d "%~dp0backend" || exit /b 1
pip install -r requirements.txt || exit /b 1
python -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',8000))==0 else 1)" && (
  echo Port 8000 is already used by an old server. Close it first, then run this file again.
  echo To find it: netstat -ano ^| findstr :8000   then: taskkill /PID the-number /F
  pause
  exit /b 1
)
python -m uvicorn app.main:app --port 8000
