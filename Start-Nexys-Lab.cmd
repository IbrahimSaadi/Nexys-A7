@echo off
setlocal
title Nexys Lab - VHDL Simulator
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
  echo This is the source edition, not the portable Windows package.
  echo Download Nexys-Lab-Windows-x64.zip from this project's GitHub Releases.
  echo See README.md for running the source edition with your own Python.
  pause
  exit /b 1
)
if not exist "runtime\ghdl\bin\ghdl.exe" (
  echo GHDL is missing. Extract the ENTIRE portable ZIP before starting.
  pause
  exit /b 1
)
rem The portable edition always uses the simulator shipped alongside it.
set "GHDL_PATH=%~dp0runtime\ghdl\bin\ghdl.exe"
echo Starting Nexys Lab. Keep this window open while using the application.
echo Press Ctrl+C in this window to stop the server.
"runtime\python\python.exe" server.py --open-browser
if errorlevel 1 (
  echo.
  echo Nexys Lab could not start. Read the error above.
  pause
)
