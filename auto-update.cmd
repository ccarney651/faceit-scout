@echo off
rem Silent auto-update for Windows Task Scheduler: pull new league matches,
rem rebuild the dashboard, and (if this folder is a git repo) publish it.
rem No browser opens. All output is appended to auto-update.log.
setlocal
cd /d "%~dp0"
set "FS=.venv\Scripts\faceit-sync.exe"
if not exist docs mkdir docs

echo ================================================>> auto-update.log
echo [%date% %time%] auto-update start>> auto-update.log

"%FS%" --db faceit.sqlite3 fetch>> auto-update.log 2>&1
"%FS%" --db faceit.sqlite3 export --format html --out docs\index.html>> auto-update.log 2>&1

rem If this folder has been turned into a git repo with a remote (GitHub Pages),
rem commit and push so the hosted site updates. Skipped harmlessly otherwise.
git rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel%==0 (
  git add docs\index.html>> auto-update.log 2>&1
  git commit -m "Auto-update dashboard">> auto-update.log 2>&1
  git push>> auto-update.log 2>&1
  echo [%date% %time%] pushed to host>> auto-update.log
)
echo [%date% %time%] done>> auto-update.log
