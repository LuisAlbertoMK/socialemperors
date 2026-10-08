@echo off
set NAME=social-emperors_0.04a

:main
call :pyInstaller
mkdir .\dist\%NAME%\saves
REM mods/ and saves/ are read from NEXT TO the exe (see bundle.py MODS_DIR), not from
REM inside the bundle, so the release has to ship them or the game starts with no mods
REM at all and without a mods.txt to enable any.
REM NOTE: the ..\..\ paths above are resolved by pyInstaller against the SPEC directory
REM (build\bundle\), but xcopy resolves against this script's working directory (build\),
REM so this one needs a single ..\ only.
mkdir .\dist\%NAME%\mods
xcopy /E /I /Y "..\mods" ".\dist\%NAME%\mods" >NUL
echo [+] pyInstaller Done.
pause>NUL
exit

:pyInstaller
echo [+] Starting pyInstaller...
pyinstaller ^
 --onedir ^
 --contents-directory "bundle" ^
 --console ^
 --noupx ^
 --noconfirm ^
 --add-data "..\..\assets;assets" ^
 --add-data "..\..\config;config" ^
 --add-data "..\..\stub;stub" ^
 --add-data "..\..\templates;templates" ^
 --add-data "..\..\villages;villages" ^
 --paths ..\. ^
 --workpath .\work ^
 --distpath .\dist ^
 --specpath .\bundle ^
 --icon=..\icon.ico ^
 --name %NAME% ..\server.py
REM --debug bootloader
EXIT /B 0

:clean
echo [+] Cleaning...
rm .\work\*
rm .\work\.*
rmdir .\work
rm .\dist\*
rm .\dist\.*
rmdir .\dist
rm .\bundle\*
rm .\bundle\.*
rmdir .\bundle
echo [+] Cleaning Done.
EXIT /B 0