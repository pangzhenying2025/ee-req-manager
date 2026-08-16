@echo off
setlocal
cd /d "%~dp0"

set "APP_PYTHON=%CD%\.venv\Scripts\python.exe"
if exist "%APP_PYTHON%" goto ready

echo Creating the project Python environment...
where uv >nul 2>nul
if errorlevel 1 goto no_uv
uv venv .venv --python 3.11
if errorlevel 1 goto install_failed
uv pip install --python "%APP_PYTHON%" -r requirements.txt
if errorlevel 1 goto install_failed

:ready
if /I "%~1"=="--check" goto check
echo Starting EE Requirements and Architecture Manager...
set "LAN_IP="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ip = Get-NetIPConfiguration ^| Where-Object { $_.NetAdapter.Status -eq 'Up' -and $_.IPv4DefaultGateway } ^| ForEach-Object { $_.IPv4Address.IPAddress } ^| Where-Object { $_ -notlike '127.*' -and $_ -notlike '169.254.*' -and $_ -notlike '198.18.*' } ^| Select-Object -First 1; if ($ip) { $ip }"`) do set "LAN_IP=%%I"
echo.
echo Local URL: http://127.0.0.1:8501
if defined LAN_IP echo LAN URL:   http://%LAN_IP%:8501
if not defined LAN_IP echo LAN URL:   Not detected - check the active Ethernet or Wi-Fi connection.
echo Other computers on the same LAN can open the LAN URL in a browser.
echo If they cannot connect, allow TCP port 8501 in Windows Firewall.
echo.
echo Press Ctrl+C to stop the service.
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%CD%\scripts\open_app_browser.ps1" -Url "http://127.0.0.1:8501"
"%APP_PYTHON%" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
if errorlevel 1 goto run_failed
goto end

:check
"%APP_PYTHON%" -c "import streamlit; print('Startup check OK: Streamlit ' + streamlit.__version__)"
exit /b %errorlevel%

:no_uv
echo ERROR: uv was not found. Install uv and run this file again.
goto failed

:install_failed
echo ERROR: Failed to install the project environment. Check the network and retry.
goto failed

:run_failed
echo ERROR: The application stopped because Streamlit returned an error.

:failed
pause
exit /b 1

:end
pause
endlocal
