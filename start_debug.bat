@echo off
pushd "%~dp0"
echo Starting YouTube DL Server...
echo.
"C:\Users\win 10\.workbuddy\binaries\python\envs\ytdl\Scripts\python.exe" app.py 2>&1
echo.
echo Exit code: %errorlevel%
pause
popd
