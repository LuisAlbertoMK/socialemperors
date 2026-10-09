@echo off
set NAME=social-emperors_0.03a

:main
REM Run "launcher_build.bat clean" to wipe the pyInstaller caches. A stale or
REM half-deleted cache is what makes the build look for files that are not there
REM anymore (base_library.zip).
if /I "%1"=="clean" (
  call :clean
  exit /b 0
)
call :pyInstaller
echo [+] Building Done!
pause>NUL
exit

:pyInstaller
echo [+] Starting pyInstaller...
pyinstaller --onefile ^
 --console ^
 --add-data "..\..\assets;assets" ^
 --add-data "..\..\stub;stub" ^
 --add-data "..\..\templates;templates" ^
 --add-data "..\..\villages;villages" ^
 --add-data "..\..\config;config" ^
 --paths ..\..\. ^
 --workpath .\work ^
 --distpath .\dist ^
 --specpath .\bundle ^
 --noconfirm ^
 --icon=..\icon.ico ^
 --name %NAME% ..\server.py
REM --debug bootloader
echo [+] pyInstaller Done.
EXIT /B 0

:clean
REM cmd has no rm, and the old lines here used it, so this routine failed silently
REM and left the caches behind. rmdir /s /q is the Windows equivalent.
echo [+] Cleaning...
if exist .\work rmdir /s /q .\work
if exist .\dist rmdir /s /q .\dist
if exist .\bundle rmdir /s /q .\bundle
echo [+] Cleaning Done.
EXIT /B 0