@echo off
REM Double-click to play: server auto-starts, latest save auto-detected.
REM Uses PowerShell 7 (pwsh): Windows PowerShell 5.1 web requests are broken on this PC.
REM Fullscreen is NOT default: the game hides its UI at any stage size other
REM than 760x600, even letterboxed (verified 2026-10-15). Windowed exact size
REM is the working setup; pass -Fullscreen -Scale show-all -ForceScale only to test.
pwsh -ExecutionPolicy Bypass -File "%~dp0play_desktop.ps1"
pause
