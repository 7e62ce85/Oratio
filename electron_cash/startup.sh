#!/bin/bash
set -e

# Create the electron cash directory if it doesn't exist
mkdir -p /root/.electron-cash

# Create or update the config file with proper RPC settings
cat > /root/.electron-cash/config << EOF
{
    "rpcuser": "${RPC_USER}",
    "rpcpassword": "${RPC_PASSWORD}",
    "rpcport": 7777,
    "rpchost": "0.0.0.0",
    "rpcallowip": "0.0.0.0/0",
    "fee_factor": 5
}
EOF

# Make the config readable only by the owner for security
chmod 600 /root/.electron-cash/config

echo "[$(date)] Starting Electron Cash daemon..."
echo "[$(date)] RPC credentials configured with user: ${RPC_USER}"

# Install Electron Cash since it's not available
echo "[$(date)] Installing Electron Cash..."
pip install electron-cash

# Start the Electron Cash daemon
echo "[$(date)] Starting Electron Cash daemon with installed package..."
electron-cash daemon start --rpcuser=${RPC_USER} --rpcpassword=${RPC_PASSWORD} --rpcport=7777 --rpchost=0.0.0.0

# Wait for daemon to start
sleep 5

# Create wallet if it doesn't exist
if [ ! -f "/root/.electron-cash/wallets/default_wallet" ]; then
    echo "[$(date)] Creating new wallet..."
    electron-cash create -w default_wallet
fi

# Load wallet
echo "[$(date)] Loading wallet..."
electron-cash daemon load_wallet -w default_wallet

# Keep the container running
tail -f /dev/null