@echo off
echo ============================================================
echo  SwarmOps Intelligence Platform v2.0 — Startup
echo ============================================================
echo.
echo [1/3] Starting FastAPI server on http://localhost:8000 ...
start "SwarmOps API" cmd /k "cd /d %~dp0 && python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul

echo [2/3] Opening Dashboard in browser...
start http://localhost:8000

echo [3/3] SwarmOps is running!
echo.
echo   Dashboard : http://localhost:8000
echo   API Docs  : http://localhost:8000/docs
echo   WebSocket : ws://localhost:8000/ws/live
echo.
echo Press any key to exit this window (server will keep running).
pause >nul
