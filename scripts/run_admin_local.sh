#!/bin/bash
# Run the admin portal locally for development/testing

set -e

cd "$(dirname "$0")/../admin_app"

echo "Starting admin portal locally..."
echo "Access at: http://127.0.0.1:5000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Set Flask to debug mode and run
export FLASK_APP=app.py
export FLASK_DEBUG=1

uv run python -m flask run --host=127.0.0.1 --port=5000
