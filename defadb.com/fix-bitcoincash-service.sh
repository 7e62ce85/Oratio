#!/bin/bash
# Fix for ContainerConfig error in Docker Compose

# Stop and remove the existing problematic container
echo "Stopping and removing bitcoincash-service container..."
docker stop bitcoincash-service 2>/dev/null || true
docker rm bitcoincash-service 2>/dev/null || true

# Clean any corrupted images
echo "Cleaning up potentially corrupted images..."
docker images | grep "bitcoincash-service" | awk '{print $3}' | xargs -r docker rmi -f

# Force rebuild the image
echo "Rebuilding bitcoincash-service image..."
cd /srv/lemmy/defadb.com
docker-compose build --no-cache bitcoincash-service

# Start just this service
echo "Starting bitcoincash-service..."
docker-compose up -d bitcoincash-service

echo "Service restart completed."