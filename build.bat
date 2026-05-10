@echo off
chcp 65001 > nul
echo ================================
echo  Building app.py...
echo ================================

cd /d "%~dp0"

echo Step 1: Running make_app.py...
python make_app.py > make_log.txt 2>&1
type make_log.txt

echo.
echo Step 2: Checking syntax...
python -m py_compile app.py > syntax_log.txt 2>&1
if errorlevel 1 (
    echo [SYNTAX ERROR]
    type syntax_log.txt
    echo.
    echo Please copy the error above and send to AI.
) else (
    echo [SYNTAX OK] app.py has no syntax errors.
)

echo.
echo Step 3: Starting Flask...
echo If Flask starts OK, you will see "Running on http://..."
echo.
python app.py > flask_log.txt 2>&1 &
timeout /t 5 > nul
type flask_log.txt

echo.
echo ================================
echo  Logs saved to:
echo   make_log.txt
echo   syntax_log.txt
echo   flask_log.txt
echo ================================
pause
