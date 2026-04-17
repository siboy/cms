#!/bin/bash
set -e

echo "=========================================="
echo "  CMS - Collaborative DOCX Editor"
echo "=========================================="
echo "Starting at $(date)"

# Sanity check: cms depends on /home/databoks/flask/razan
if [ ! -d "/home/databoks/flask/razan" ]; then
  echo "[FATAL] /home/databoks/flask/razan not found."
  echo "        CMS requires flask project mounted at /home/databoks/flask"
  exit 1
fi

if [ ! -f "/home/databoks/flask/.env" ]; then
  echo "[FATAL] /home/databoks/flask/.env not found."
  exit 1
fi

export PYTHONPATH="/home/databoks/flask:${PYTHONPATH}"
export CMS_FLASK_ROOT="/home/databoks/flask"

cd /home/databoks/cms

echo "Starting Flask server on port 8879..."
exec flask --app app run -h 0.0.0.0 -p 8879 --debugger --with-threads
