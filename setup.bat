@echo off

:: Check if Python 3.12 is installed
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.12 is not installed. Please install it and try again.
    pause
    exit /b 1
)

:: Initialize and update git submodules
git submodule init
git submodule update

:: Set up virtual environment with Python 3.12
py -3.12 -m venv .\venv
call .\venv\Scripts\activate.bat

:: Upgrade pip and install required packages
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt