@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_URL=http://127.0.0.1:5173"
set "API_URL=http://127.0.0.1:8000/health"
set "BUNDLED_ROOT=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies"
set "BUNDLED_NODE_BIN=%BUNDLED_ROOT%\node\bin"
set "FALLBACK_PNPM=%BUNDLED_ROOT%\bin\fallback\pnpm.cmd"

rem Prefer the project-tested bundled Node runtime when it is available.
if exist "%BUNDLED_NODE_BIN%\node.exe" set "PATH=%BUNDLED_NODE_BIN%;%PATH%"

if /I "%~1"=="--check" goto check_only

call :ensure_environment
if errorlevel 1 goto failed

call :is_url_ready "%API_URL%"
if errorlevel 1 (
    echo Starting the local API at http://127.0.0.1:8000 ...
    start "AI Intel API" /D "%~dp0" cmd /k ""%~dp0.venv\Scripts\python.exe" -m ai_intel.main"
) else (
    echo The local API is already running.
)

call :is_url_ready "%APP_URL%"
if errorlevel 1 (
    echo Starting the local web interface at %APP_URL% ...
    start "AI Intel Web" /D "%~dp0web" cmd /k ""%PNPM%" dev"
) else (
    echo The local web interface is already running.
)

echo Waiting for the system interface to become ready ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(90); $apiReady=$false; $webReady=$false; do { try { $apiReady=(Invoke-WebRequest -UseBasicParsing -Uri '%API_URL%' -TimeoutSec 2).StatusCode -eq 200 } catch { $apiReady=$false }; try { $webStatus=(Invoke-WebRequest -UseBasicParsing -Uri '%APP_URL%' -TimeoutSec 2).StatusCode; $webReady=$webStatus -ge 200 -and $webStatus -lt 400 } catch { $webReady=$false }; if (-not ($apiReady -and $webReady)) { Start-Sleep -Milliseconds 500 } } while ((Get-Date) -lt $deadline -and -not ($apiReady -and $webReady)); if ($apiReady -and $webReady) { exit 0 } else { exit 1 }"
if errorlevel 1 goto timed_out

echo Opening %APP_URL% ...
start "" "%APP_URL%"
echo Ready. Close the "AI Intel API" and "AI Intel Web" windows to stop the system.
timeout /t 3 /nobreak >nul
exit /b 0

:check_only
call :ensure_environment
if errorlevel 1 exit /b 1
echo Python:
"%~dp0.venv\Scripts\python.exe" --version
echo Node:
node --version
echo pnpm:
call "%PNPM%" --version
echo Startup prerequisites are ready.
exit /b 0

:ensure_environment
where node.exe >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js was not found.
    echo Install a compatible Node.js runtime or restore the bundled Codex runtime.
    exit /b 1
)

node -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit(((major===20&&minor>=19)||(major===22&&minor>=12)||major>22)?0:1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: The available Node.js version is not compatible with the current Vite toolchain.
    echo Use Node 20.19+, Node 22.12+, or a newer release.
    exit /b 1
)

if not exist "%~dp0.venv\Scripts\python.exe" goto bootstrap
if not exist "%~dp0web\node_modules" goto bootstrap
goto resolve_pnpm

:bootstrap
echo Project dependencies are missing. Preparing the local environment ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 (
    echo ERROR: Project setup did not complete successfully.
    exit /b 1
)

:resolve_pnpm
set "PNPM="
for /f "delims=" %%P in ('where pnpm.cmd 2^>nul') do if not defined PNPM set "PNPM=%%P"
if defined PNPM exit /b 0
if exist "%FALLBACK_PNPM%" (
    set "PNPM=%FALLBACK_PNPM%"
    exit /b 0
)

echo ERROR: pnpm was not found.
echo Install pnpm 11.19.0 or restore the bundled Codex runtime.
exit /b 1

:is_url_ready
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $status=(Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec 2).StatusCode; if ($status -ge 200 -and $status -lt 400) { exit 0 } } catch {}; exit 1" >nul 2>&1
exit /b %ERRORLEVEL%

:timed_out
echo ERROR: The interface did not become ready within 90 seconds.
echo Check the "AI Intel API" and "AI Intel Web" windows for the error details.
pause
exit /b 1

:failed
echo Startup failed. Review the message above, then run start.bat again.
pause
exit /b 1
