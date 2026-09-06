@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scena_telegram_setup.py %*
) else (
    where py >nul 2>&1
    if errorlevel 1 (
        python scena_telegram_setup.py %*
    ) else (
        py -3 scena_telegram_setup.py %*
    )
)

echo.
pause
endlocal
