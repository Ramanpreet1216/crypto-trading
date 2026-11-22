#!/bin/bash
# ==============================================================================
# One-time Setup Script: Installs 1-Minute Auto-Sync on Oracle Cloud Instance
# Run once inside the project directory on Oracle Cloud VM:
#   bash setup_oracle_autodeploy.sh
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/sync_from_github.sh"

chmod +x "$SYNC_SCRIPT"

# Configure crontab to run every minute
CRON_JOB="* * * * * /bin/bash $SYNC_SCRIPT >> $SCRIPT_DIR/sync_cron.log 2>&1"

# Check if cron job is already installed
(crontab -l 2>/dev/null | grep -F "$SYNC_SCRIPT") >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "[*] Auto-sync cron job is already active!"
else
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "[+] SUCCESS: Auto-sync installed! Oracle will now check GitHub every 60 seconds and auto-update."
fi

echo "[*] Crontab active schedule:"
crontab -l | grep "sync_from_github.sh"
