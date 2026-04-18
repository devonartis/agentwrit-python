#!/usr/bin/env bash
# Run all acceptance tests using pytest with session-scoped fixture.
# This avoids rate limiting by sharing one AgentWritApp across all tests.
#
# Usage:
#   ./tests/sdk-core/run_acceptance.sh          # Run with existing broker
#   ./tests/sdk-core/run_acceptance.sh --up     # Start broker if not running

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export AGENTWRIT_BROKER_URL="${AGENTWRIT_BROKER_URL:-http://127.0.0.1:8080}"

if [[ -z "${AGENTWRIT_CLIENT_ID:-}" || -z "${AGENTWRIT_CLIENT_SECRET:-}" ]]; then
    echo "Error: AGENTWRIT_CLIENT_ID and AGENTWRIT_CLIENT_SECRET must be set." >&2
    echo "Register a test app via the broker admin API, or export them before running this script." >&2
    exit 1
fi

# Check if broker is running
broker_up() {
    curl -sf "${AGENTWRIT_BROKER_URL}/v1/health" > /dev/null 2>&1
}

# Parse arguments
START_BROKER=false
PYTEST_ARGS=()

for arg in "$@"; do
    if [[ "$arg" == "--up" ]]; then
        START_BROKER=true
    else
        PYTEST_ARGS+=("$arg")
    fi
done

# Start broker if requested and not running
if [[ "$START_BROKER" == "true" ]]; then
    if ! broker_up; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Starting broker..."
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        "${REPO_ROOT}/broker/scripts/stack_up.sh"
        echo "Waiting for broker to be ready..."
        for i in {1..30}; do
            if broker_up; then
                echo "Broker is ready!"
                break
            fi
            sleep 1
        done
    fi
fi

# Verify broker is running
if ! broker_up; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ERROR: Broker is not running!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Start the broker with:"
    echo "  ./broker/scripts/stack_up.sh"
    echo ""
    echo "Or use --up flag to start it automatically:"
    echo "  ./tests/sdk-core/run_acceptance.sh --up"
    echo ""
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Running AgentWrit SDK Acceptance Tests"
echo "  Broker: ${AGENTWRIT_BROKER_URL}"
echo "  Client: ${AGENTWRIT_CLIENT_ID}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create evidence directory
mkdir -p "${SCRIPT_DIR}/evidence"

# Run acceptance tests with pytest
# Session-scoped fixture ensures single app auth (avoids 429 rate limit)
cd "${REPO_ROOT}"
uv run pytest tests/integration/test_acceptance_stories.py \
    -v \
    -s \
    -m integration \
    --tb=short \
    --continue-on-collection-errors \
    ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"} 2>&1 | tee "${SCRIPT_DIR}/evidence/test_run.log"

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $EXIT_CODE -eq 0 ]]; then
    echo "  All acceptance tests PASSED"
else
    echo "  Some acceptance tests FAILED"
fi
echo "  Evidence: tests/sdk-core/evidence/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $EXIT_CODE
