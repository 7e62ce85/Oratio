#!/bin/bash

# Fix for Bitcoin Cash payment service
echo "Starting Bitcoin Cash wallet fix script..."

# Set correct working directory
cd /srv/lemmy/oratio

# Make sure ElectronCash daemon is running
echo "Checking if ElectronCash daemon is running..."
docker-compose ps electron-cash

# Restart ElectronCash container if needed
echo "Restarting the ElectronCash container..."
docker-compose restart electron-cash

# Wait for ElectronCash to initialize
echo "Waiting for ElectronCash to initialize (30 seconds)..."
sleep 30

# Restart the bitcoincash_service
echo "Restarting Bitcoin Cash payment service..."
docker-compose restart bitcoincash-service

# Wait for the service to come up
echo "Waiting for service to initialize (10 seconds)..."
sleep 10

# Check logs for updated balance information
echo "Checking recent logs for balance information..."
docker-compose logs --tail=50 bitcoincash-service | grep "잔액"

echo "Fix script completed."
echo "Please check the payment system status at:"
echo "http://your-server-address:8081/health"

echo "To view detailed logs run:"
echo "docker-compose logs --tail=100 bitcoincash-service"