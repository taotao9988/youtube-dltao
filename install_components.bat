@echo off
pushd "C:\Users\win 10\WorkBuddy\20260510183216"
echo Installing yt-dlp remote components for deno...
"C:\Users\win 10\.workbuddy\binaries\python\envs\ytdl\Scripts\python.exe" -m yt_dlp --install-compat-opts jsc-deno-remote
echo Done.
pause
