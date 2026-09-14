@echo off
rem Double-click launcher for the replay-bot review server. The window
rem stays open while the server runs; close it to stop the server.
title OWDB replay-bot review server
cd /d "%~dp0..\.."
node tools/replay_bot/review/server.js --open %*