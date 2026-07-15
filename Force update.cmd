@echo off
cd /d "%~dp0"
set "FS=.venv\Scripts\faceit-sync.exe"
if not exist "%FS%" (
  echo ERROR: %FS% not found.
  pause & exit /b 1
)
echo ==================================================
echo   FACEIT-sync : FORCE update (backfills replay codes)
echo ==================================================
echo Unlike the normal update, this re-fetches matches already stored so that
echo replay codes published AFTER a match was first ingested get picked up.
echo (Matches must be FINISHED on FACEIT; codes live ~7 days.)
echo.
echo Re-seeding known matches from matches.txt...
"%FS%" --db faceit.sqlite3 fetch --matches-file matches.txt --force-refresh
echo.
echo Re-checking every division for new + updated matches...
"%FS%" --db faceit.sqlite3 fetch --force-refresh
echo.
echo Rebuilding dashboard...
"%FS%" --db faceit.sqlite3 export --format html --out dashboard.html
echo Opening dashboard...
start "" "dashboard.html"
echo.
echo Done. Today's codes should now be present (if the matches are finished).
timeout /t 4 >nul
