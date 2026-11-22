#!/bin/bash
set -e

BACKUP_DIR="/home/ubuntu/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/crypto_trading_backup_${TIMESTAMP}.tar.gz"
LATEST_LINK="${BACKUP_DIR}/crypto_trading_backup_latest.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "Creating compressed project backup on Oracle VM..."
tar --exclude='crypto-trading/wa_gateway/node_modules' \
    --exclude='*/__pycache__*' \
    --exclude='*.pyc' \
    --exclude='crypto-trading/.git' \
    -czf "$BACKUP_FILE" -C /home/ubuntu crypto-trading

# Create/update 'latest' copy
cp -f "$BACKUP_FILE" "$LATEST_LINK"

echo "Backup created successfully:"
ls -lh "$BACKUP_FILE"
echo ""
echo "All available backups:"
ls -lh "$BACKUP_DIR"
