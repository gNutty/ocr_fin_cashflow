@echo off
setlocal
echo ==========================================
echo    OCR Project Environment Setup
echo ==========================================
echo.

echo 1. Creating Virtual Environment (.venv)...
python -m venv .venv

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to create Virtual Environment. 
    echo Please make sure Python is installed and in your PATH.
    pause
    exit /b %ERRORLEVEL%
)

echo 2. Activating Environment...
call .venv\Scripts\activate.bat

echo 3. Installing/Updating Dependencies...
echo This may take a few minutes...
python -m pip install --upgrade pip
pip install -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ==========================================
echo    Setup Completed Successfully!
echo    You can now run 'run_app.bat'
echo ==========================================
echo.
pause
endlocal
