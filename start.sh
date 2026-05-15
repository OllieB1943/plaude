#!/bin/bash
# Plaude Code — start everything
set -e

cd "$(dirname "$0")"

# Check config exists
if [ ! -f config.json ]; then
  echo "No config.json found. Run: python setup.py"
  exit 1
fi

# Check token exists
if [ ! -f token.json ]; then
  echo "Not authenticated. Run: python setup.py"
  exit 1
fi

PYTHON=$(which python3.13 2>/dev/null || which python3 2>/dev/null || echo "python3")
echo "Starting Plaude Code..."
$PYTHON -m src.watcher
