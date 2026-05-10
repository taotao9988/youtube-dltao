@echo off
cd /d "%~dp0"
echo Checking app.py syntax...
python -m py_compile app.py 2>syntax_error.txt
if %errorlevel% equ 0 (
    echo SYNTAX OK
    python app.py 2>flask_error.txt
) else (
    echo SYNTAX ERROR - see syntax_error.txt
    type syntax_error.txt
)
pause
