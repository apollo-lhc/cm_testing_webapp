#!/bin/bash

# run with . ./gen_secret_key.sh

# Set output file
KEY_FILE="flask_secret_key"

# Generate 64-character hex key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Write to file with secure permissions
echo "$SECRET_KEY" > "$KEY_FILE"
chmod 600 "$KEY_FILE"

# Export it to the current shell environment
export FLASK_SECRET_KEY="$SECRET_KEY"

# Optional: confirm
echo "FLASK_SECRET_KEY has been generated, saved to ./$KEY_FILE, and exported."
