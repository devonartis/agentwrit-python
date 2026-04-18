#!/bin/sh
set -e

# Wait for broker to be healthy
echo "Waiting for broker at ${AGENTWRIT_BROKER_URL}..."
until curl -sf "${AGENTWRIT_BROKER_URL}/v1/health" > /dev/null 2>&1; do
    sleep 1
done
echo "Broker is ready."

# Auto-register app if no client credentials provided
if [ -z "${AGENTWRIT_CLIENT_ID}" ] || [ -z "${AGENTWRIT_CLIENT_SECRET}" ]; then
    echo "No client credentials — registering app with broker..."

    if [ -z "${AGENTWRIT_ADMIN_SECRET}" ]; then
        echo "ERROR: AGENTWRIT_ADMIN_SECRET required for auto-registration"
        exit 1
    fi

    # Authenticate as admin
    ADMIN_TOKEN=$(curl -sf -X POST "${AGENTWRIT_BROKER_URL}/v1/admin/auth" \
        -H "Content-Type: application/json" \
        -d "{\"secret\":\"${AGENTWRIT_ADMIN_SECRET}\"}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

    # Register the demo app
    APP_JSON=$(curl -sf -X POST "${AGENTWRIT_BROKER_URL}/v1/admin/apps" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -d '{
            "name": "medassist-demo",
            "scopes": [
                "read:records:*", "write:records:*", "read:labs:*",
                "write:prescriptions:*", "read:formulary:*",
                "read:billing:*", "write:billing:*", "read:insurance:*"
            ],
            "token_ttl": 1800
        }')

    export AGENTWRIT_CLIENT_ID=$(echo "${APP_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['client_id'])")
    export AGENTWRIT_CLIENT_SECRET=$(echo "${APP_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['client_secret'])")

    echo "App registered: ${AGENTWRIT_CLIENT_ID}"
fi

echo "Starting MedAssist AI on port 5000..."
exec uv run uvicorn demo.app:app --host 0.0.0.0 --port 5000
