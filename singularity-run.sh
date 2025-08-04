#!/bin/bash
# filepath: singularity-run.sh
# Singularity-based alternative to docker-run.sh
# Usage: ./singularity-run.sh start|stop [flask|gunicorn]

CONTAINER_NAME="cm-testing-webapp"
IMAGE_NAME="cm-testing-webapp.sif"
PID_FILE="./singularity-webapp.pid"

SERVER_TYPE=${2:-gunicorn}

case "$SERVER_TYPE" in
    flask)
        PORT=5001
        ENV_VARS="SERVER_TYPE=flask"
        ;;
    gunicorn)
        PORT=8000
        ENV_VARS="SERVER_TYPE=gunicorn,GUNICORN_BIND=0.0.0.0:8000"
        ;;
    *)
        echo "Invalid server type: $SERVER_TYPE"
        exit 1
        ;;
esac

singularity_start() {
    echo "Starting $CONTAINER_NAME with $SERVER_TYPE server on port $PORT"
    
    # Build image if it doesn't exist
    if [ ! -f "$IMAGE_NAME" ]; then
        echo "Building Singularity image..."
        singularity build $IMAGE_NAME docker-daemon://cm-testing-webapp:latest
    fi
    
    # Stop existing instance
    singularity_stop
    
    # Start in background
    SINGULARITYENV_SERVER_TYPE=$SERVER_TYPE \
    singularity run \
        --bind "$(pwd)/data:/app/data" \
        --bind "$(pwd)/uploads:/app/uploads" \
        --bind "$(pwd)/log:/app/log" \
        $IMAGE_NAME &
    
    echo $! > $PID_FILE
    echo "Container started with PID $(cat $PID_FILE)"
}

singularity_stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat $PID_FILE)
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            rm $PID_FILE
            echo "Container stopped"
        fi
    fi
}