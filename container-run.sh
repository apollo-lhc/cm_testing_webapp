#!/bin/bash
# filepath: container-run.sh
# Universal script for Docker or Singularity
# Usage: ./container-run.sh start|stop [flask|gunicorn] [docker|singularity]

CONTAINER_NAME="cm-testing-webapp"
RUNTIME=${3:-docker}  # Default to docker

# Detect available runtime if not specified
if [ "$RUNTIME" = "auto" ]; then
    if command -v docker &> /dev/null; then
        RUNTIME="docker"
    elif command -v singularity &> /dev/null; then
        RUNTIME="singularity"
    else
        echo "Neither Docker nor Singularity found"
        exit 1
    fi
fi

SERVER_TYPE=${2:-gunicorn}

case "$SERVER_TYPE" in
    flask)
        PORT=5001
        ;;
    gunicorn)
        PORT=8000
        ;;
esac

if [ "$RUNTIME" = "docker" ]; then
    # Use existing Docker logic
    source ./docker-run.sh "$1" "$2"
elif [ "$RUNTIME" = "singularity" ]; then
    # Use Singularity logic
    source ./singularity-run.sh "$1" "$2"
fi