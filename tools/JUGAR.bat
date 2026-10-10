@echo off
REM Double-click to play: server auto-starts, latest save auto-detected.
REM Uses PowerShell 7 (pwsh): Windows PowerShell 5.1 web requests are broken on this PC.
pwsh -ExecutionPolicy Bypass -File "%~dp0play_desktop.ps1" -Fullscreen
pause
