#!/bin/sh
# Simple script to generate and set FLASK_SECRET_KEY locally for dev
# Run with: . ./gen_key.sh

# Generate a 64-character hex key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Export it to the current shell environment
export FLASK_SECRET_KEY="$SECRET_KEY"

# Print to confirm
echo "FLASK_SECRET_KEY has been set:"
echo "$FLASK_SECRET_KEY"

