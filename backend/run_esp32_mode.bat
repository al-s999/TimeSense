@echo off
REM Run FastAPI backend bound to 0.0.0.0 for ESP32 access
REM Usage: run_esp32_mode.bat [port]

setlocal enabledelayedexpansion

set PORT=%1
if "%PORT%"=="" set PORT=8000

echo Starting Time Sense Backend in ESP32 mode...
echo Binding to 0.0.0.0:%PORT% (accessible from all network interfaces)
echo.
echo Access URLs:
echo   http://localhost:%PORT%/api/health
echo   http://192.168.x.x:%PORT%/api/access
echo   http://192.168.x.x:%PORT%/api/command
echo   http://192.168.x.x:%PORT%/api/sensor/update
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port %PORT%
