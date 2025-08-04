#!/bin/bash

# Entrypoint script to choose between Flask development server and Gunicorn
# intended to be used in a Docker container. Logs to stdout/stderr which
# can be captured by Docker logging drivers.

# Default Gunicorn configuration
GUNICORN_WORKERS=${GUNICORN_WORKERS:-4}
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-30}
GUNICORN_KEEPALIVE=${GUNICORN_KEEPALIVE:-2}
GUNICORN_MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-1000}
GUNICORN_BIND=${GUNICORN_BIND:-0.0.0.0:5001}

if [ "$SERVER_TYPE" = "gunicorn" ]; then
    echo "Starting with Gunicorn..."
    echo "Workers: $GUNICORN_WORKERS"
    echo "Timeout: $GUNICORN_TIMEOUT"
    echo "Keep-alive: $GUNICORN_KEEPALIVE"
    echo "Max requests: $GUNICORN_MAX_REQUESTS"
    echo "Bind: $GUNICORN_BIND"
    exec gunicorn \
        --bind $GUNICORN_BIND \
        --workers $GUNICORN_WORKERS \
        --timeout $GUNICORN_TIMEOUT \
        --keep-alive $GUNICORN_KEEPALIVE \
        --max-requests $GUNICORN_MAX_REQUESTS \
        --access-logfile - \
        --error-logfile - \
        --disable-redirect-access-to-syslog \
        wsgi:app
elif [ "$SERVER_TYPE" = "flask" ]; then
    echo "Starting with Flask development server..."
    exec python app.py
else
    echo "Unknown SERVER_TYPE: $SERVER_TYPE"
    echo "Valid options are: flask, gunicorn"
    exit 1
fi
