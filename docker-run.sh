#!/bin/bash
# Docker-based alternative to run.sh
# Usage: ./docker-run.sh start|stop|restart [flask|gunicorn]

CONTAINER_NAME="cm-testing-webapp"
IMAGE_NAME="cm-testing-webapp"

# Default to gunicorn for production-like behavior
SERVER_TYPE=${2:-gunicorn}

case "$SERVER_TYPE" in
    flask)
        PORT=5001
        ENV_VARS="-e SERVER_TYPE=flask"
        ;;
    gunicorn)
        PORT=8000
        ENV_VARS="-e SERVER_TYPE=gunicorn -e GUNICORN_BIND=0.0.0.0:8000"
        ;;
    *)
        echo "Invalid server type: $SERVER_TYPE"
        echo "Valid options: flask, gunicorn"
        exit 1
        ;;
esac

docker_start() {
    echo "Starting $CONTAINER_NAME with $SERVER_TYPE server on port $PORT"
    
    # Build the image if it doesn't exist
    if ! docker image inspect $IMAGE_NAME > /dev/null 2>&1; then
        echo "Building Docker image..."
        docker build -t $IMAGE_NAME .
    fi
    
    # Stop existing container if running
    docker stop $CONTAINER_NAME > /dev/null 2>&1
    docker rm $CONTAINER_NAME > /dev/null 2>&1
    
    # Start new container
    docker run -d \
        --name $CONTAINER_NAME \
        -p $PORT:$PORT \
        $ENV_VARS \
        -v "$(pwd)/data:/app/data" \
        -v "$(pwd)/uploads:/app/uploads" \
        -v "$(pwd)/log:/app/log" \
        $IMAGE_NAME
    
    if [ $? -eq 0 ]; then
        echo "Container started successfully"
        echo "Application available at: http://localhost:$PORT"
        return 0
    else
        echo "Failed to start container"
        return 1
    fi
}

docker_stop() {
    echo "Stopping $CONTAINER_NAME"
    if docker stop $CONTAINER_NAME; then
        docker rm $CONTAINER_NAME
        echo "Container stopped and removed"
        return 0
    else
        echo "Failed to stop container or container not running"
        return 1
    fi
}

docker_restart() {
    docker_stop
    sleep 2
    docker_start
}

docker_logs() {
    echo "Showing logs for $CONTAINER_NAME (press Ctrl+C to exit)"
    docker logs -f $CONTAINER_NAME
}

docker_status() {
    echo "Container status:"
    docker ps -a --filter name=$CONTAINER_NAME
}

case "$1" in
    start)
        docker_start
        exit $?
        ;;
    stop)
        docker_stop
        exit $?
        ;;
    restart)
        docker_restart
        exit $?
        ;;
    logs)
        docker_logs
        ;;
    status)
        docker_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|status} [flask|gunicorn]"
        echo "Examples:"
        echo "  $0 start flask    # Start with Flask dev server on port 5001"
        echo "  $0 start gunicorn # Start with Gunicorn on port 8000 (default)"
        echo "  $0 logs          # Show container logs"
        echo "  $0 status        # Show container status"
        exit 1
        ;;
esac
