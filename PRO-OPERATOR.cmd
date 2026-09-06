@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scena_pro_operator.py
) else (
    where py >nul 2>&1
    if errorlevel 1 (
        python scena_pro_operator.py
    ) else (
        py -3 scena_pro_operator.py
    )
)
echo.
pause
endlocal
