@echo off
cd /d "%~dp0"
set "FS=.venv\Scripts\faceit-sync.exe"
if not exist "%FS%" (
  echo ERROR: %FS% not found.
  pause & exit /b 1
)
echo ==================================================
echo   FACEIT-sync : pull new matches from the league
echo ==================================================
echo Checking every known team for new matches ^(no API key needed^)...
"%FS%" --db faceit.sqlite3 fetch
echo.
echo Rebuilding dashboard...
"%FS%" --db faceit.sqlite3 export --format html --out dashboard.html
echo Opening dashboard...
start "" "dashboard.html"
echo.
echo Done. New matches ^(if any^) are imported and the dashboard is refreshed.
timeout /t 4 >nul
