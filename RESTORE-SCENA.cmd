@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scena_restore.py
) else (
    where py >nul 2>&1
    if errorlevel 1 (
        python scena_restore.py
    ) else (
        py scena_restore.py
    )
)
echo.
pause
endlocal
