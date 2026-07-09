@echo off
cd /d "%~dp0"
set "FS=.venv\Scripts\faceit-sync.exe"
if not exist "%FS%" (
  echo ERROR: %FS% not found.
  pause & exit /b 1
)
echo Re-importing everything in matches.txt ^(already-stored matches are skipped^)...
"%FS%" --db faceit.sqlite3 fetch --matches-file matches.txt
echo Rebuilding dashboard...
"%FS%" --db faceit.sqlite3 export --format html --out dashboard.html
echo Opening dashboard...
start "" "dashboard.html"
timeout /t 3 >nul
