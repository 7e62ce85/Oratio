# Lemmy and Payment System 

This project details the implementation of a **Lemmy** community platform and a **BitcoinCash Payment Service** on a DigitalOcean Droplet. The services run in Docker containers with Nginx configured as a reverse proxy with SSL applied.

## Table of Contents

- [Project Overview](#project-overview)
- [Components](#components)
- [Installation and Deployment](#installation-and-deployment)
  - [1. DigitalOcean and DNS Setup](#1-digitalocean-and-dns-setup)
  - [2. Lemmy Installation](#2-lemmy-installation)
  - [3. BitcoinCash Payment Service Implementation](#3-bitcoincash-payment-service-implementation)
  - [4. Nginx and SSL Configuration](#4-nginx-and-ssl-configuration)
- [Payment System Operation](#payment-system-operation)
- [Current Status and Issues](#current-status-and-issues)
- [Troubleshooting and FAQ](#troubleshooting-and-faq)

## Project Overview

Key objectives of this project:

- **Lemmy Platform**: Operating a decentralized social community
- **BitcoinCash Payment Service**: Enabling users to charge account credits using BCH
- **Secure Implementation**: Enhanced security through Nginx reverse proxy and SSL

## Components

- **Lemmy**: Docker Compose-based community platform (Rust backend)
- **BitcoinCash Payment Service**: Python Flask API service
- **ElectronCash**: BCH wallet management container (optional)
- **Direct Payment Processing Module**: Transaction verification through external APIs
- **Nginx**: Reverse proxy, HTTPS redirection, domain-specific configuration
- **Docker and Docker Compose**: Container-based deployment

## Installation and Deployment

### 1. DigitalOcean and DNS Setup

1. **Creating a Droplet**
   - Shared CPU, 1GB RAM, Debian 12 x64, Singapore region
   - SSH access: `ssh root@[DROPLET_IP]`

2. **DNS Configuration**
   - Add A records:
     - `defadb.com` → Droplet IP
     - `www.defadb.com` → Droplet IP
     - `payments.defadb.com` → Droplet IP

### 2. Lemmy Installation

1. **Install Basic Packages**
   ```bash
   apt update && apt upgrade -y
   apt install -y curl wget git vim docker.io docker-compose
   ```

2. **Lemmy Configuration**
   ```bash
   mkdir -p /srv/lemmy/defadb.com
   cd /srv/lemmy/defadb.com
   # Configure lemmy.hjson and docker-compose.yml files
   ```

3. **Launch Lemmy**
   ```bash
   docker-compose up -d
   ```

### 3. BitcoinCash Payment Service Implementation

1. **Directory Structure**
   ```bash
   mkdir -p /srv/lemmy/defadb.com/bitcoincash_service
   mkdir -p /srv/lemmy/defadb.com/electron_cash
   mkdir -p /srv/lemmy/defadb.com/data/bitcoincash
   ```

2. **Flask Application Development**
   - app.py: Payment API endpoint implementation
   - direct_payment.py: External BCH API integration
   - transaction_monitor.py: Transaction monitoring tool

3. **Key Features**:
   - Invoice generation and QR code display
   - Payment confirmation via BCH address
   - User credit management
   - Lemmy system integration

4. **ElectronCash Configuration**:
   - Dockerfile and startup script creation
   - Wallet management and RPC interface setup

5. **Execution Method**
   ```bash
   docker-compose up -d bitcoincash-service electron-cash
   ```

### 4. Nginx and SSL Configuration

1. **Nginx Configuration**
   - Domain-specific reverse proxy settings
   - HTTP → HTTPS redirection

2. **SSL Certificate Issuance**
   ```bash
   certbot certonly --standalone -d defadb.com -d www.defadb.com
   certbot certonly --standalone -d payments.defadb.com
   ```

3. **Apply Configuration**
   ```bash
   docker-compose restart proxy
   ```

## Payment System Operation

1. **Invoice Generation**
   - Access payment page: `https://payments.defadb.com/generate_invoice?amount=0.001&user_id=1`
   - BCH address and QR code display

2. **Payment Processing - Direct Mode**
   - User transfers directly to specified BCH address (Coinomi wallet)
   - System verifies transaction through external API
   - Credits added to user account

3. **Payment Processing - ElectronCash Mode**
   - User transfers BCH to address generated by ElectronCash
   - Transaction confirmation and verification count management via ElectronCash RPC
   - Credits added to user account and funds forwarded to main wallet

4. **Manual Verification Tools**
   - Manual transaction verification and processing in case of API connection issues

## Current Status and Issues

### 1. Implemented Features

- ✅ Lemmy community platform installation and execution
- ✅ Basic structure of BitcoinCash payment service
- ✅ Nginx reverse proxy and SSL configuration
- ✅ Invoice generation and QR code display
- ✅ Direct payment mode implementation (using external API)

### 2. Current Issues

1. **ElectronCash Container Instability**
   - Continuous restarting state (interactive prompt issues during wallet creation)
   - Wallet creation commands not functioning properly in Docker environment
   - Solution attempts: Non-interactive wallet creation script, startup script modification

2. **API Connection Issues**
   - Connection failures to external BCH APIs (DNS resolution errors)
   - Affected APIs: rest.bitcoin.com, bch-chain.api.btc.com, api.blockchair.com
   - Error message: "Failed to establish a new connection: [Errno -2] Name or service not known"
   - Solution attempts: Docker DNS configuration changes, direct IP address usage implementation

3. **Actual Payment Processing Failures**
   - System fails to recognize transactions when BCH is sent
   - Invoices expire or remain in 'pending' state
   - Solution attempts: Manual transaction verification tool, API test script implementation

4. **Nginx Configuration Errors**
   - Rate limiting configuration issue: "invalid zone size "zone=api" in nginx.conf"
   - Solution attempt: Specifying zone size (zone=api:10m)

### 3. Future Improvement Directions

1. **ElectronCash Alternative Solutions**
   - Transition to more stable payment verification methods using only external APIs
   - Try multiple APIs (Bitcoin.com, Blockchair, etc.) to improve availability

2. **Network and DNS Issue Resolution**
   - Improve Docker container network settings
   - Force usage of external DNS servers (8.8.8.8, 1.1.1.1)

3. **Manual Management Tool Improvements**
   - Expand payment monitoring and manual verification tools
   - Implement automated transaction verification procedures

## Troubleshooting and FAQ

### Common Issues

1. **ElectronCash Container Errors**
   - Direct payment mode automatically activates when container restarts
   - Error checking: `docker-compose logs electron-cash`
   - Solution: Set `DIRECT_MODE=True` in app.py

2. **API Connection Issues**
   - Error checking: `docker-compose logs -f bitcoincash-service`
   - Testing: `docker-compose exec bitcoincash-service python /app/test_api_connection.py`
   - Solutions:
     - Docker DNS configuration: Add DNS servers to `/etc/docker/daemon.json`
     - Direct IP calls: Use bypass_dns_request function in direct_payment.py

3. **Payment Verification Failures**
   - Manual verification: `docker-compose exec bitcoincash-service python /app/transaction_monitor.py tx`
   - Pending invoice check: `docker-compose exec bitcoincash-service python /app/transaction_monitor.py list`
   - Manual approval: `docker-compose exec bitcoincash-service python /app/transaction_monitor.py confirm [INVOICE_ID]`

4. **Database Management**
   - SQLite installation: `docker-compose exec bitcoincash-service apt-get update && apt-get install -y sqlite3`
   - Data verification: `docker-compose exec bitcoincash-service sqlite3 /data/payments.db`

### Operation Tips

1. **Security Enhancement**
   - Change all passwords (configured in .env file)
   - Set up regular wallet backups

2. **Monitoring**
   - Regular log checks: `docker-compose logs -f`
   - Utilize transaction monitoring tools

3. **General Maintenance**
   - SSL certificate renewal check: `certbot renew --dry-run`
   - Docker container status monitoring: `docker ps`
