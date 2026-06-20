@echo off
title Meeting Audio Recorder - Launcher
echo =======================================================
echo         Meeting Audio Recorder Launcher
echo =======================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python from https://www.python.org/ before running this.
    echo.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [INFO] Python virtual environment 'venv' not found. Creating it...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [INFO] Virtual environment created successfully.
)

echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip

echo [INFO] Installing required packages...
pip install pyaudiowpatch sounddevice numpy soundfile flask

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies. Please check your internet connection.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] All dependencies are ready!
echo [INFO] Starting the Meeting Audio Recorder server...
echo [INFO] The dashboard will open automatically in your browser...
echo.

python app.py

echo.
echo [INFO] Server stopped.
pause
