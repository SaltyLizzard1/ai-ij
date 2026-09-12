@echo off
rem Double-click "button": score any photos that have no blur record yet,
rem refresh the photo index, and show what changed. Safe to run any time.
setlocal
cd /d "%~dp0\.."
call ".venv\Scripts\activate.bat"
social-pipeline score
echo.
social-pipeline status
echo.
pause
