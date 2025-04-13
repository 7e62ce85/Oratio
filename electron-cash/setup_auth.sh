#!/bin/bash

# Setup authentication for Electron Cash RPC server
echo "[$(date +"%Y-%m-%d %H:%M:%S")] Setting up RPC authentication..."

# Configuration directory
CONFIG_DIR="/root/.electron-cash"
CONFIG_FILE="$CONFIG_DIR/config"
RPC_PORT=7777

# Create config directory if it doesn't exist
mkdir -p "$CONFIG_DIR"

# Generate random credentials if they don't exist or are invalid
if [ ! -f "$CONFIG_FILE" ] || ! grep -q "rpcuser" "$CONFIG_FILE" || ! grep -q "rpcpassword" "$CONFIG_FILE" ; then
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] Creating new RPC credentials..."
    
    # Generate random username and password
    RPC_USER="bchrpc"
    RPC_PASSWORD=$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 16)
    
    # Save to config file
    cat > "$CONFIG_FILE" << EOL
{
    "rpcuser": "$RPC_USER",
    "rpcpassword": "$RPC_PASSWORD",
    "rpcport": $RPC_PORT,
    "rpchost": "0.0.0.0"
}
EOL
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] RPC credentials created."
else
    # Extract existing credentials
    RPC_USER=$(grep -oP '"rpcuser":\s*"\K[^"]+' "$CONFIG_FILE")
    RPC_PASSWORD=$(grep -oP '"rpcpassword":\s*"\K[^"]+' "$CONFIG_FILE")
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] Using existing RPC credentials."
fi

# Save credentials to shared file that can be mounted by bitcoincash-service
echo "ELECTRON_CASH_USER=$RPC_USER" > /shared/electron_cash_auth.env
echo "ELECTRON_CASH_PASSWORD=$RPC_PASSWORD" >> /shared/electron_cash_auth.env
echo "ELECTRON_CASH_URL=http://electron-cash:$RPC_PORT" >> /shared/electron_cash_auth.env

# Set permissions
chmod 600 /shared/electron_cash_auth.env

echo "[$(date +"%Y-%m-%d %H:%M:%S")] RPC authentication setup complete. Credentials saved to /shared/electron_cash_auth.env"