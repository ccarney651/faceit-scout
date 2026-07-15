@echo off
cd /d "%~dp0"
set "OW=.venv\Scripts\owscout.exe"
if not exist "%OW%" (
  echo ERROR: %OW% not found. Install with:  .venv\Scripts\pip install -e .[capture]
  pause & exit /b 1
)
if "%~1"=="" (
  echo Usage: "Capture replay.cmd" ^<demo_code^> [--side-a-team "Team Name"] [--speed 4]
  echo   1) Paste the code into the OW replay client, set playback to 4x, alt-tab back.
  echo   2) This samples the map and stores comp observations.
  pause & exit /b 1
)
set "CODE=%~1"
shift
echo Context for %CODE%:
"%OW%" --db owscout.sqlite3 --faceit-db faceit.sqlite3 code show %CODE%
echo.
echo Set the replay to 4x now, then press a key to start sampling...
pause >nul
"%OW%" --db owscout.sqlite3 --faceit-db faceit.sqlite3 capture --code %CODE% --speed 4 %1 %2 %3 %4
pause
