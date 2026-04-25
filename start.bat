@echo off
cd /d "%~dp0backend"
start /b "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8001"
uv run uvicorn main:app --port 8001
