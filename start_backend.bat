@echo off
chcp 65001 >nul
echo ==========================================
echo     V4 Data Generator - Web Backend
chcp 65001 >nul
echo ==========================================
echo.

cd /d "C:\work\roleplay\V4"

REM Use MSYS2 Python which has all dependencies installed
set "PYTHON=C:\tools\msys64\mingw64\bin\python.exe"
set "PIP=C:\tools\msys64\mingw64\bin\pip.exe"

REM Check if MSYS2 Python is available
if not exist "%PYTHON%" (
    echo Error: MSYS2 Python not found at %PYTHON%
    echo Please install MSYS2 and required packages:
    echo   pacman -S mingw-w64-x86_64-python-pip
    echo   pip install tenacity fastapi uvicorn httpx
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
%PYTHON% --version

REM Check if required packages are installed
echo.
echo Checking dependencies...
%PYTHON% -c "import fastapi, uvicorn, tenacity" 2>nul
if errorlevel 1 (
    echo Installing required packages...
    %PIP% install tenacity fastapi uvicorn httpx
)

echo.
echo Starting V4 Web Backend...
echo API: http://localhost:8000
echo WebSocket: ws://localhost:8000/ws
echo Docs: http://localhost:8000/docs
echo.
echo Press CTRL+C to stop
echo.

%PYTHON% -m uvicorn web.backend.main:app --host 0.0.0.0 --port 8000 --reload

pause
