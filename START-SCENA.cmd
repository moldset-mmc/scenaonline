@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    set "SCENA_PY=py"
) else (
    set "SCENA_PY=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python environment...
    %SCENA_PY% -m venv .venv
    if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"
python -c "import streamlit, PIL, qrcode, cryptography, importlib.metadata as m; assert streamlit.__version__ == '1.63.0'; assert PIL.__version__ == '12.3.0'; assert m.version('qrcode') == '8.2'; assert cryptography.__version__ == '46.0.5'" >nul 2>&1
if errorlevel 1 (
    echo Installing SCENA dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

echo.
echo Starting SCENA. The correct address will appear below.
echo Do not copy the explanatory text into PowerShell.
python start_scena.py
if errorlevel 1 goto :error
goto :end

:error
echo.
echo SCENA could not start. Copy the error above and send it for diagnosis.
pause
exit /b 1

:end
endlocal
