@echo off
cd /d "%~dp0"
set "OW=.venv\Scripts\owscout.exe"
if not exist "%OW%" (
  echo ERROR: %OW% not found. Install with:  .venv\Scripts\pip install -e .[capture]
  pause & exit /b 1
)
echo Learn HUD hero refs -- the reliable way to build/upgrade the library.
echo.
echo   1. Custom game: cycle through every hero you want to cover.
echo   2. Open the replay, scrub so ONE hero shows in the spectator top-bar.
echo   3. Press ENTER here to grab; confirm the guess (ENTER) or type the name.
echo   4. Repeat for each hero. The tool grabs at your calibrated resolution.
echo.
"%OW%" --db owscout.sqlite3 --faceit-db faceit.sqlite3 refs learn %*
echo.
echo Verifying library...
"%OW%" --db owscout.sqlite3 --faceit-db faceit.sqlite3 refs verify
pause
