@echo off
setlocal EnableExtensions
title Living Morrowind - AI Daemon
cd /d "%~dp0"

echo ==============================================================
echo   LIVING MORROWIND - AI daemon
echo   Keep this window open while you play. Launch OpenMW from MO2.
echo ==============================================================
echo.

rem ---- Find Python 3.10 or newer -----------------------------------------
set "PYEXE="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PYEXE=py -3" && goto :havepython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PYEXE=python" && goto :havepython
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PYEXE=python3" && goto :havepython

echo [ERROR] Python 3.10 or newer was not found.
echo         Install it from https://www.python.org/downloads/
echo         and tick "Add python.exe to PATH" during setup, then run this again.
echo.
pause
exit /b 1

:havepython
rem ---- First-time setup: API key -------------------------------------------
if exist ".env" goto :haveenv
echo First-time setup: Living Morrowind needs a Google Gemini API key.
echo Get one for free at https://aistudio.google.com/  - "Get API key"
echo.
set "APIKEY="
set /p "APIKEY=Paste your Gemini API key here and press Enter: "
if not defined APIKEY goto :nokey
> ".env" echo GEMINI_API_KEY=%APIKEY%
echo.
echo Saved your key to .env in this folder. Edit or delete that file to change it.
echo.
goto :haveenv

:nokey
echo No key entered. Run this file again when you have your key.
pause
exit /b 1

:haveenv
rem ---- Run the daemon -------------------------------------------------------
%PYEXE% main.py
echo.
echo The Living Morrowind daemon has stopped.
pause
