FROM python:3.9-slim

# Install required packages
RUN apt-get update && apt-get install -y \
    git \
    openssl \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Clone Electron Cash from repository
RUN git clone https://github.com/Electron-Cash/Electron-Cash.git /app

WORKDIR /app

# Install Electron Cash dependencies
RUN pip install --no-cache-dir -r contrib/requirements/requirements.txt \
    && pip install --no-cache-dir -r contrib/requirements/requirements-binaries.txt \
    && pip install --no-cache-dir requests flask gunicorn

# Create a symbolic link to make electron-cash command available
RUN ln -s /app/electron-cash /usr/local/bin/electron-cash && chmod +x /app/electron-cash

# Copy start script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Create directories
RUN mkdir -p /root/.electron-cash/wallets

# Expose RPC port
EXPOSE 7777

# Launch Electron Cash with the start script
CMD ["/app/start.sh"]
