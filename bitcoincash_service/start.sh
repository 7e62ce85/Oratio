#!/bin/bash
# Start script for the Bitcoin Cash payment service

# Ensure all directories exist
mkdir -p /data

# Initialize the database if needed
python -c "from models import init_db; init_db()"

# Start the application using gunicorn
gunicorn --bind 0.0.0.0:8081 app:app