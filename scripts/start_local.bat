@echo off
setlocal
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\asx_feed_env\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Python environment not found: %PYTHON%
  echo Create the environment and install requirements.txt first.
  pause
  exit /b 1
)

if not exist "%ROOT%\frontend\package.json" (
  echo Frontend package.json not found: %ROOT%\frontend\package.json
  pause
  exit /b 1
)

echo Starting backend in a new terminal...
start "ASX backend" /D "%ROOT%" cmd.exe /k ""%PYTHON%" -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000"

echo Starting frontend in a new terminal...
start "ASX frontend" /D "%ROOT%\frontend" cmd.exe /k "npm.cmd run dev"

echo.
echo Backend:  http://localhost:8000/health
echo Frontend: http://localhost:3000
echo Admin:    http://localhost:3000/admin
echo Keep both service terminals open while using the application.
endlocal