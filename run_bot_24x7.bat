@echo off
title CoinDCX Autonomous Trading Bot - 24/7 Engine
color 0A
cd /d "%~dp0"

echo =====================================================================
echo   COINDCX AUTONOMOUS 24/7 TRADING BOT & DASHBOARD LAUNCHER
echo =====================================================================
echo.
echo Local Dashboard URL: http://localhost:5001
echo Auto-restart watchdog is active (bot will restart if interrupted).
echo Press Ctrl + C to stop the bot.
echo.

:loop
echo [%date% %time%] Starting server and autonomous bot...
python server.py
echo [%date% %time%] Warning: Server process ended. Restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto loop
