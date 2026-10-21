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
    
    # Reset and pull latest code
    git reset --hard origin/$BRANCH
    
    # Install any new dependencies if requirements.txt changed
    if [ -f "requirements.txt" ]; then
        pip install --no-cache-dir -r requirements.txt --quiet 2>/dev/null || pip3 install --no-cache-dir -r requirements.txt --quiet 2>/dev/null
    fi

    # Restart server.py process
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting server.py..."
    pkill -9 -f "server.py" 2>/dev/null
    sleep 1

    # Restart in background
    if command -v python3 >/dev/null 2>&1; then
        nohup python3 server.py > server.log 2>&1 &
    else
        nohup python server.py > server.log 2>&1 &
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bot updated and successfully running on port 5000!"
fi
