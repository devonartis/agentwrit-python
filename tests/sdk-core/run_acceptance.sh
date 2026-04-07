#!/usr/bin/env bash
# Run all acceptance tests and capture evidence files.
# Usage: ./tests/sdk-core/run_acceptance.sh

set -euo pipefail

export AGENTAUTH_BROKER_URL=http://127.0.0.1:8080
export AGENTAUTH_CLIENT_ID=sit-d1eeee10a81e
export AGENTAUTH_CLIENT_SECRET=08f1b60f93e6eeb5f7bbe4791981d0c338188d38e117ad70d90797a96a90173a

EVIDENCE_DIR="tests/sdk-core/evidence"
mkdir -p "$EVIDENCE_DIR"

passed=0
failed=0

for script in tests/sdk-core/s[0-9]_*.py; do
    name=$(basename "$script" .py)
    evidence="$EVIDENCE_DIR/$name.txt"

    echo ""
    echo "━━━ Running $script → $evidence ━━━"

    if uv run python "$script" 2>&1 | tee "$evidence"; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi

    # Broker rate limit: 10 req/min per client_id.
    # Each script authenticates separately. Pause to stay under limit.
    sleep 7
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: $passed passed, $failed failed"
echo "  Evidence: $EVIDENCE_DIR/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
