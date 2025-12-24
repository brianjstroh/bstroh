#!/bin/bash
# Start Devstral GPU server for AI coding assistant
# Usage: ./scripts/start_devstral.sh [--wait]
#
# This script starts the Devstral GPU server (g5.xlarge spot instance)
# and optionally waits for it to be ready before returning the endpoint.
#
# The server will auto-shutdown after 60 minutes of inactivity.

set -e

SERVER_NAME="devstral"
WAIT_FOR_READY=false

# Parse arguments
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --wait) WAIT_FOR_READY=true ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
  shift
done

echo "Starting Devstral GPU server..."

# Start the server
RESULT=$(aws lambda invoke \
  --function-name "gpu-${SERVER_NAME}-start" \
  --cli-binary-format raw-in-base64-out \
  /dev/stdout 2>/dev/null)

echo "$RESULT" | jq -r '.body' | jq .

# Extract instance ID
INSTANCE_ID=$(echo "$RESULT" | jq -r '.body' | jq -r '.instanceId // empty')

if [ -z "$INSTANCE_ID" ]; then
  echo "Failed to get instance ID"
  exit 1
fi

if [ "$WAIT_FOR_READY" = false ]; then
  echo ""
  echo "Server starting. Run with --wait to wait for it to be ready."
  echo "Or check status with: aws lambda invoke --function-name gpu-${SERVER_NAME}-status /dev/stdout"
  exit 0
fi

echo ""
echo "Waiting for server to be ready (this takes 5-10 minutes)..."

# Wait for instance to be running and have a public IP
while true; do
  STATUS=$(aws lambda invoke \
    --function-name "gpu-${SERVER_NAME}-status" \
    --cli-binary-format raw-in-base64-out \
    /dev/stdout 2>/dev/null)

  STATE=$(echo "$STATUS" | jq -r '.body' | jq -r '.status // "unknown"')
  IP=$(echo "$STATUS" | jq -r '.body' | jq -r '.instances[0].publicIp // empty')

  echo "  State: $STATE, IP: ${IP:-pending}"

  if [ "$STATE" = "running" ] && [ -n "$IP" ]; then
    break
  fi

  sleep 10
done

echo ""
echo "Instance running at $IP"
echo "Waiting for Ollama to be ready..."

# Wait for Ollama API to respond
ENDPOINT="http://${IP}:11434"
while true; do
  if curl -s --connect-timeout 5 "${ENDPOINT}/api/tags" > /dev/null 2>&1; then
    break
  fi
  echo "  Waiting for Ollama..."
  sleep 10
done

echo ""
echo "=========================================="
echo "Devstral server is ready!"
echo ""
echo "Ollama endpoint: ${ENDPOINT}"
echo ""
echo "Configure VS Code Cline:"
echo "  1. Open Cline settings"
echo "  2. Set API Provider to 'Ollama'"
echo "  3. Set Base URL to: ${ENDPOINT}"
echo "  4. Select model: devstral:24b"
echo ""
echo "The server will auto-shutdown after 60 minutes of inactivity."
echo "To stop manually: aws lambda invoke --function-name gpu-${SERVER_NAME}-stop /dev/stdout"
echo "=========================================="
