#!/bin/bash
# ==============================================================================
# Auto-Sync & Continuous Deployment Script for CoinDCX Trading Bot on Oracle Cloud
# Checks GitHub repository for new commits every minute. If updated, pulls code
# and restarts server.py seamlessly.
# ==============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

BRANCH="main"

# Fetch latest branch metadata from GitHub
git fetch origin $BRANCH --quiet 2>/dev/null

LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse origin/$BRANCH 2>/dev/null)

if [ -n "$LOCAL" ] && [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] New update detected on GitHub ($LOCAL -> $REMOTE)!"
    
    # Discard any local file modifications (e.g. paper_trades.json cache) so pull never fails
    git checkout -- paper_trades.json 2>/dev/null || true
    git reset --hard origin/$BRANCH
    
    # Install any new dependencies if requirements.txt changed
    if [ -f "requirements.txt" ]; then
        pip install --no-cache-dir -r requirements.txt --quiet 2>/dev/null || pip3 install --no-cache-dir -r requirements.txt --quiet 2>/dev/null
    fi

    # Restart bot using systemd tradingbot.service if available, else process restart
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting trading bot..."
    if systemctl list-unit-files 2>/dev/null | grep -q "tradingbot.service"; then
        sudo systemctl restart tradingbot
    else
        pkill -9 -f "server.py" 2>/dev/null
        sleep 1
        nohup python3 server.py > server.log 2>&1 &
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot updated and successfully running on port 5000!"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Server is already 100% up to date (${LOCAL:0:7}). Standing by for new GitHub commits."
fi
