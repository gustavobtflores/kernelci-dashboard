#!/bin/sh
set -e

echo "Starting File Dropper Worker..."

# Set Python environment variables
export PYTHONOPTIMIZE=${PYTHONOPTIMIZE:-2}
export PYTHONUNBUFFERED=${PYTHONUNBUFFERED:-1}

# Activate poetry virtual environment
if [ -f "$(poetry env info --path 2>/dev/null)/bin/activate" ]; then
    . "$(poetry env info --path)/bin/activate"
else
    echo "Warning: Could not activate poetry environment, proceeding anyway..."
fi

# Set default values for file dropper parameters
DROP_INTERVAL=${DROP_INTERVAL:-1800}
SUBMISSIONS_DIR=${SUBMISSIONS_DIR:-./submissions}
SUBMISSIONS_ARCHIVE=${SUBMISSIONS_ARCHIVE:-./all_submissions.tgz}
MIN_FILES=${MIN_FILES:-10}
MAX_FILES=${MAX_FILES:-100}

# Verify required files exist
if [ ! -f "$SUBMISSIONS_ARCHIVE" ]; then
    echo "Warning: Submissions archive not found at $SUBMISSIONS_ARCHIVE"
    echo "The file dropper may not function correctly without the archive file."
fi

# Create submissions directory if it doesn't exist
if [ ! -d "$SUBMISSIONS_DIR" ]; then
    echo "Creating submissions directory: $SUBMISSIONS_DIR"
    mkdir -p "$SUBMISSIONS_DIR"
fi

# PID file for the worker process
WORKER_PID=""

# Cleanup function
cleanup() {
    echo ""
    echo "Received shutdown signal, gracefully stopping file dropper worker..."
    if [ -n "$WORKER_PID" ] && kill -0 "$WORKER_PID" 2>/dev/null; then
        echo "Sending SIGTERM to worker process (PID: $WORKER_PID)..."
        kill -TERM "$WORKER_PID" 2>/dev/null || true

        # Wait for graceful shutdown with timeout
        TIMEOUT=30
        COUNT=0
        while kill -0 "$WORKER_PID" 2>/dev/null && [ $COUNT -lt $TIMEOUT ]; do
            sleep 1
            COUNT=$((COUNT + 1))
        done

        # Force kill if still running
        if kill -0 "$WORKER_PID" 2>/dev/null; then
            echo "Worker did not stop gracefully, sending SIGKILL..."
            kill -KILL "$WORKER_PID" 2>/dev/null || true
        fi
    fi
    echo "File dropper worker stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT SIGQUIT

# Start the file dropper worker
echo "Starting file dropper worker with:"
echo "  - Drop interval: ${DROP_INTERVAL}s"
echo "  - Submissions directory: $SUBMISSIONS_DIR"
echo "  - Submissions archive: $SUBMISSIONS_ARCHIVE"
echo ""

# Run the submissions_file_dropper command
poetry run python manage.py submissions_file_dropper \
    --interval "$DROP_INTERVAL" \
    --submissions-dir "$SUBMISSIONS_DIR" \
    --archive-file "$SUBMISSIONS_ARCHIVE" \
    --min-files "$MIN_FILES" \
    --max-files "$MAX_FILES" &

WORKER_PID=$!
echo "File dropper worker started with PID: $WORKER_PID"

# Wait for the worker process
wait "$WORKER_PID"
EXIT_CODE=$?

echo "File dropper worker exited with code: $EXIT_CODE"
exit $EXIT_CODE
