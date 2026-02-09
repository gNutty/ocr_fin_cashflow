@echo off
setlocal

echo Checking for virtual environment...

if exist ".venv\Scripts\activate.bat" (
    echo Activating .venv...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo Activating venv...
    call venv\Scripts\activate.bat
) else (
    echo.
    echo ---------------------------------------------------------
    echo [ERROR] No virtual environment found!
    echo [TIP] Please run 'setup_env.bat' first to install dependencies.
    echo ---------------------------------------------------------
    echo.
    pause
    exit /b 1
)

echo Starting Streamlit App (app.py)...
python -m streamlit run app.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo ---------------------------------------------------------
    echo [ERROR] Application failed to start.
    echo ---------------------------------------------------------
    echo Reasons might be:
    echo 1. Streamlit is not installed.
    echo 2. Virtual environment is not set up correctly.
    echo.
    echo [TIP] Please run 'setup_env.bat' first to install all dependencies.
    echo ---------------------------------------------------------
    pause
)

endlocal
