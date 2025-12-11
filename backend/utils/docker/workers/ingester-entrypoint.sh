#!/bin/sh
set -e

echo "Starting Ingester Worker..."

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

export PROMETHEUS_MULTIPROC_DIR=${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus_multiproc_dir}

mkdir -p $PROMETHEUS_MULTIPROC_DIR
rm -rf $PROMETHEUS_MULTIPROC_DIR/*

# Run database migrations
echo "Running database migrations..."
poetry run python manage.py migrate --noinput

# Set default values for ingester parameters
SPOOL_DIR=${SPOOL_DIR:-./submissions}
TREES_FILE=${TREES_FILE:-./trees.yaml}
MAX_WORKERS=${MAX_WORKERS:-5}
CHECK_INTERVAL=${CHECK_INTERVAL:-5}

# Verify required directories exist
if [ ! -d "$SPOOL_DIR" ]; then
    echo "Creating spool directory: $SPOOL_DIR"
    mkdir -p "$SPOOL_DIR"
fi

# Create required subdirectories
mkdir -p "$SPOOL_DIR/archive"
mkdir -p "$SPOOL_DIR/failed"

# Verify trees file exists
if [ ! -f "$TREES_FILE" ]; then
    echo "Warning: Trees file not found at $TREES_FILE"
fi

# PID file for the worker process
WORKER_PID=""

# Cleanup function
cleanup() {
    echo ""
    echo "Received shutdown signal, gracefully stopping ingester worker..."
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
    echo "Ingester worker stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT SIGQUIT

# Start the ingester worker
echo "Starting ingester worker with:"
echo "  - Spool directory: $SPOOL_DIR"
echo "  - Trees file: $TREES_FILE"
echo "  - Max workers: $MAX_WORKERS"
echo "  - Check interval: ${CHECK_INTERVAL}s"
echo ""

# Run the monitor_submissions command
poetry run python manage.py monitor_submissions \
    --spool-dir "$SPOOL_DIR" \
    --trees-file "$TREES_FILE" \
    --max-workers "$MAX_WORKERS" \
    --interval "$CHECK_INTERVAL" &

WORKER_PID=$!
echo "Ingester worker started with PID: $WORKER_PID"

# Wait for the worker process
wait "$WORKER_PID"
EXIT_CODE=$?

echo "Ingester worker exited with code: $EXIT_CODE"
exit $EXIT_CODE
