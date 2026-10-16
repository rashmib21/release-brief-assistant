#!/bin/sh
# Build the frontend and start the app on http://localhost:8000 (Linux / macOS / Git Bash)
set -e
cd "$(dirname "$0")/frontend" && npm ci && npm run build
cd ../backend && pip install -r requirements.txt
if python -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',8000))==0 else 1)"; then
  echo "Port 8000 is already used by an old server. Close it first, then run this script again."; exit 1
fi
python -m uvicorn app.main:app --port 8000
