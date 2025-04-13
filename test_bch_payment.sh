#!/bin/bash
# Test script for Bitcoin Cash payment service
# This script will run the test_payment.py script inside the Docker container

echo "===== TESTING BITCOIN CASH PAYMENT SERVICE ====="
echo "Running tests inside Docker container..."

# Make the test script executable
chmod +x /srv/lemmy/defadb.com/bitcoincash_service/test_payment.py

# Run the test script inside the Docker container
docker exec -it $(docker ps -q -f name=bitcoincash) python3 /app/test_payment.py

echo "===== END OF TESTS ====="