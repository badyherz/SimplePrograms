@echo off

REM  Prerequisite: pyinstaller is installed.
REM  pip install pyinstaller

cd /d "%~dp0"

set SCRIPT_NAME=SP_exe_search

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --onefile --noconsole --icon=..\..\assets\logoSP.ico --paths "..\.." --add-data "..\..\assets\footer.png;assets" %SCRIPT_NAME%.py

echo.
echo Done! The .exe can be found in the folder "dist".
echo %~dp0dist\%SCRIPT_NAME%.exe
pause