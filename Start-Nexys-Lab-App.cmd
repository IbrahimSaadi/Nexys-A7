@echo off
setlocal
title Nexys Lab - App
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
  echo Extract the complete portable package first.
  pause
  exit /b 1
)
"runtime\python\python.exe" desktop.py
if errorlevel 1 (
  echo.
  echo Could not open the app. If it is already running, use its existing window.
  echo Otherwise read the error above or use Start-Nexys-Lab.cmd.
  pause
)
