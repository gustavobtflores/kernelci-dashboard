#!/bin/sh
set -e

echo "Starting Aggregator Worker..."

# Set Python environment variables
export PYTHONOPTIMIZE=${PYTHONOPTIMIZE:-2}
export PYTHONUNBUFFERED=${PYTHONUNBUFFERED:-1}

# Activate poetry virtual environment
if [ -f "$(poetry env info --path 2>/dev/null)/bin/activate" ]; then
    . "$(poetry env info --path)/bin/activate"
else
    echo "Warning: Could not activate poetry environment, proceeding anyway..."
fi

# Handle environment variables from files (Docker secrets support)
file_env() {
    local var="$1"
    local def="${2:-}"
    local fileVar="${var}_FILE"
    local fileVal=$(eval echo \$"${fileVar}")
    local val=$(eval echo \$"${var}")

    if [ -n "$val" ] && [ -n "$fileVal" ]; then
        echo >&2 "error: both $var and $fileVar are set (but are exclusive)"
        exit 1
    elif [ -f "$fileVal" ]; then
        val=$(cat "$fileVal")
    elif [ -z "$val" ]; then
        val="$def"
    fi
    export "$var"="$val"
}

file_env DB_DEFAULT_PASSWORD

# Set default values for file dropper parameters
AGGREGATOR_INTERVAL=${AGGREGATOR_INTERVAL:-300}
AGGREGATOR_AMOUNT=${AGGREGATOR_AMOUNT:-10000}

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
echo "Starting aggregator worker with:"
echo "  - Aggregation interval: ${AGGREGATOR_INTERVAL}s"
echo ""

# Run the submissions_file_dropper command
poetry run python manage.py process_pending_aggregations \
    --interval "$AGGREGATOR_INTERVAL" \
    --batch-size "$AGGREGATOR_AMOUNT" \
    --loop &

WORKER_PID=$!
echo "File dropper worker started with PID: $WORKER_PID"

# Wait for the worker process
wait "$WORKER_PID"
EXIT_CODE=$?

echo "File dropper worker exited with code: $EXIT_CODE"
exit $EXIT_CODE
