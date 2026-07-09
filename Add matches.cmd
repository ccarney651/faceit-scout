@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "FS=.venv\Scripts\faceit-sync.exe"
if not exist "%FS%" (
  echo ERROR: %FS% not found. Open this folder's setup first.
  pause & exit /b 1
)
echo ==================================================
echo   FACEIT-sync : add match^(es^)
echo ==================================================
echo Paste one or more FACEIT match URLs or IDs, space-separated,
echo then press Enter.  ^(Right-click in this window to paste.^)
echo.
set "URLS="
set /p "URLS=Matches: "
if "!URLS!"=="" ( echo No input given. & timeout /t 3 ^>nul & exit /b 0 )
echo.
echo Importing ^(re-runs are safe; finished matches are skipped^)...
"%FS%" --db faceit.sqlite3 fetch --matches !URLS!
rem remember them for future full rebuilds
for %%U in (!URLS!) do echo %%U>> matches.txt
echo.
echo Rebuilding dashboard...
"%FS%" --db faceit.sqlite3 export --format html --out dashboard.html
echo Opening dashboard...
start "" "dashboard.html"
echo.
echo Done. You can close this window.
timeout /t 4 >nul
