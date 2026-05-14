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

echo "Starting Plaude Code..."
python src/watcher.py
