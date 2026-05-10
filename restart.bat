@echo off
pushd "%~dp0"
echo Killing old process...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul
echo Starting YouTube DL Server...
"C:\Users\win 10\.workbuddy\binaries\python\envs\ytdl\Scripts\python.exe" app.py
