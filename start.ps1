Set-Location "$PSScriptRoot\backend"
Start-Job { Start-Sleep 4; Start-Process "http://localhost:8001" } | Out-Null
uv run uvicorn main:app --port 8001
