@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import cryptography; assert cryptography.__version__ == '46.0.5'" >nul 2>&1
if errorlevel 1 (
    echo Preparing the local SCENA upgrade environment...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" scena_upgrade.py %*
if errorlevel 1 goto :error
echo.
pause
endlocal
exit /b 0

:error
echo.
echo SCENA upgrade could not finish. Your previous installation is unchanged.
echo Copy the error above and send it for diagnosis.
pause
endlocal
exit /b 1
