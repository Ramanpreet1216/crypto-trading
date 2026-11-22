@echo off
echo ==============================================================================
echo [AUTO-DEPLOY] Syncing CoinDCX Trading Bot & Dashboard to GitHub...
echo ==============================================================================
cd /d "%~dp0"
git add .
git commit -m "Auto-deploy: Update bot, dashboard, and strategies"
git push origin main
echo.
echo ==============================================================================
echo [SUCCESS] Pushed to GitHub successfully!
echo.
echo Oracle Cloud VM auto-sync is active:
echo - VM pulls new commits automatically within 60 seconds
echo - server.py automatically restarts in the background
echo.
echo Open Live Dashboard: http://80.225.247.119:5000/
echo ==============================================================================
pause
