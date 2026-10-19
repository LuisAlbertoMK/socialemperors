@echo off
set NAME=social-emperors_0.05a

:main
REM Run "launcher_build.bat clean" to wipe the pyInstaller caches. A stale or
REM half-deleted cache is what makes the build look for files that are not there
REM anymore (base_library.zip).
if /I "%1"=="clean" (
  call :clean
  exit /b 0
)
call :pyInstaller
REM mods/ and saves/ are read from NEXT TO the exe (see bundle.py MODS_DIR), not
REM from inside the onefile bundle. Without this copy the launcher starts with
REM no mods at all and without a mods.txt to enable any.
mkdir .\dist\saves
mkdir .\dist\mods
xcopy /E /I /Y "..\mods" ".\dist\mods" >NUL
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