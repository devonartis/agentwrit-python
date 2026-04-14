# Broker Setup Guide

> **Purpose:** Set up the broker so the [sample apps](sample-app-mini-max.md) can run.
> The apps need specific scope ceilings configured per app.
> **Audience:** Operators registering apps, or developers verifying their app's ceiling.
> **Prerequisites:** Broker running. See [Getting Started: Operator](../broker/docs/getting-started-operator.md) for broker deployment.

---

## Overview

Every app needs a registered scope ceiling. The ceiling is the **maximum** scope any agent created by that app can request. If an app requests a scope outside its ceiling, the broker returns `403` and no token is issued.

The app **cannot** discover its own ceiling — the operator sets it when registering the app, and the broker enforces it silently at agent creation time. You must track ceilings outside the broker.

---

## Step 1: Register the App

Register the app once. Replace the scopes with what your operator approved.

### Option A: Using aactl (recommended)

```bash
export AACTL_BROKER_URL="http://localhost:8080"
export AACTL_ADMIN_SECRET="your-admin-secret"

aactl app register \
  --name sample-apps \
  --scopes "read:data:*,write:data:*,read:customers:*,write:orders:*,read:files:*,write:files:*,read:monitoring:*,send:webhooks:*,read:billing:*,write:notes:*,read:audit:all,delete:customers:*,read:logs:*"
```

### Option B: Using raw HTTP (admin API)

Admin auth is not part of the SDK. Use `aactl` or raw HTTP:

```bash
# 1. Get admin token
ADMIN_TOKEN=$(curl -s -X POST "http://localhost:8080/v1/admin/auth" \
  -H "Content-Type: application/json" \
  -d '{"secret": "your-admin-secret"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Register app with the full ceiling
curl -X POST "http://localhost:8080/v1/admin/apps" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "name": "sample-apps",
    "scopes": ["read:data:*","write:data:*","read:customers:*","write:orders:*","read:files:*","write:files:*","read:monitoring:*","send:webhooks:*","read:billing:*","write:notes:*","read:audit:all","delete:customers:*","read:logs:*"]
  }'
```

Save the `client_id` and `client_secret` from the response. The `client_secret` is shown only once.

---

## Step 2: Set Environment Variables

```bash
export AGENTWRIT_BROKER_URL="http://localhost:8080"
export AGENTWRIT_CLIENT_ID="sample-apps"
export AGENTWRIT_CLIENT_SECRET="your-client-secret"
```

---

## Scope Ceiling Reference Per App

Each app requests specific scopes. The **app's ceiling** must cover them, or the broker rejects the agent creation.

### App 1: File Access Gate

```
Ceiling needed:           read:files:*, write:files:*
Scopes requested by app:   read:files:report-q3
```

The app reads files `report-q3` and `audit-log`. The ceiling must include `read:files:*`.

### App 2: Customer API Gateway

```
Ceiling needed:           read:customers:*
Scopes requested by app:  read:customers:customer-42, read:customers:customer-99
```

The app fetches customer records by ID. The ceiling must include `read:customers:*`.

### App 3: LLM Tool Executor

```
Ceiling needed:           read:customers:*, write:orders:*, delete:customers:*, read:audit:all
Scopes requested by app:  read:customers:customer-42, write:orders:customer-42
                          (delete:customers:* and read:audit:all are intentionally not requested —
                           this is what the app tests as denied)
```

The app exercises scope enforcement. It needs `delete:customers:*` and `read:audit:all` in the ceiling **only to demonstrate denials** — the app intentionally does not request them, so the broker blocks them.

### App 4: Data Pipeline Runner

```
Ceiling needed:           read:data:*, write:data:*
Scopes requested by app:  read:data:source-batch-101, read:data:source-batch-102,
                          write:data:dest-batch-101, write:data:dest-batch-102
```

The pipeline reads from source partitions and writes to destination partitions. The ceiling must include `read:data:*` and `write:data:*`.

### App 5: Audit Log Reader

```
Scope ceiling:            N/A — no agent scopes needed
What it uses:            Admin auth only (aactl or raw HTTP admin API)
                          POST /v1/admin/auth with AACTL_ADMIN_SECRET
                          GET /v1/audit/events with admin Bearer token
```

The SDK is not used. The app uses raw HTTP to authenticate as admin and read events. The SDK (`AgentWritApp`) only handles app-level operations — it has no admin auth path.

### App 6: Token Lifecycle Manager

```
Ceiling needed:           read:data:*
Scopes requested by app:  read:data:sync-source
```

The worker reads from a sync source. The ceiling must include `read:data:*`.

### App 7: Multi-Tenant Agent Factory

```
Ceiling needed:           read:data:*
Scopes requested by app:  read:data:invoices:{tenant_id}, read:data:reports:{tenant_id}
                          (tenant IDs are substituted at runtime: acme-corp, globex)
```

The factory substitutes tenant IDs at runtime. The ceiling must include `read:data:*` — the specific `{tenant_id}` identifiers are not in the ceiling.

### App 8: Webhook Dispatcher

```
Ceiling needed:           send:webhooks:*
Scopes requested by app:  send:webhooks:order-confirmation
```

The app sends outbound webhooks. The ceiling must include `send:webhooks:*`.

### App 9: Scope Ceiling Guard

```
Ceiling needed:           read:data:test, read:data:*, write:data:*, admin:revoke:*, read:logs:*
                          (intentionally includes out-of-bounds scopes for testing)
Scopes requested by app:  read:data:test          — inside ceiling → should succeed
                          admin:revoke:asterisk   — outside ceiling → BLOCKED (403)
                          read:logs:system        — outside ceiling → BLOCKED (403)
```

The purpose of this app is to demonstrate the broker blocking requests that exceed the ceiling. Without `admin:revoke:*` and `read:logs:*` in the ceiling, the app cannot show the blocking behavior.

### App 10: Renewal with Revocation Detection

```
Ceiling needed:           read:monitoring:*
Scopes requested by app:  read:monitoring:alerts
```

The continuous agent reads monitoring alerts. The ceiling must include `read:monitoring:*`.

---

## Complete Ceiling for All Apps

To run every app without modification, register the app with this ceiling:

### aactl

```bash
aactl app update sample-apps \
  --scopes "read:data:*,write:data:*,read:customers:*,write:orders:*,read:files:*,write:files:*,read:monitoring:*,send:webhooks:*,read:billing:*,write:notes:*,read:audit:all,delete:customers:*,read:logs:*"
```

### HTTP

```bash
curl -X POST "http://localhost:8080/v1/admin/apps/sample-apps" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sample-apps",
    "scopes": ["read:data:*","write:data:*","read:customers:*","write:orders:*","read:files:*","write:files:*","read:monitoring:*","send:webhooks:*","read:billing:*","write:notes:*","read:audit:all","delete:customers:*","read:logs:*"]
  }'
```

---

## Broker Start Command

```bash
AA_ADMIN_SECRET="your-admin-secret" \
AA_DB_PATH="/tmp/agentwrit.db" \
AA_DEFAULT_TTL="300" \
AA_MAX_TTL="600" \
./broker
```

| Flag | Purpose |
|------|---------|
| `AA_ADMIN_SECRET` | Admin password for operator tasks (app registration, revocation, audit) |
| `AA_DB_PATH` | SQLite database path — audit log and revocation data |
| `AA_DEFAULT_TTL` | Default agent token TTL in seconds (300 = 5 minutes) |
| `AA_MAX_TTL` | Maximum TTL any token can be issued with (clamping ceiling) |

---

## Quick Verification

```bash
# Broker is up
curl http://localhost:8080/v1/health

# App auth works
curl -X POST "http://localhost:8080/v1/app/auth" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "sample-apps", "client_secret": "your-client-secret"}'
# Returns: {"access_token": "...", "expires_in": 1800}

# List apps (admin)
aactl app list
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|--------|-------|-----|
| `401` on app auth | Wrong `client_id` or `client_secret` | Re-register the app and save the credentials |
| `403` on agent creation | Requested scope outside app ceiling | Extend the app ceiling with `aactl app update`, or narrow the requested scope |
| `403` on admin auth | Wrong `AACTL_ADMIN_SECRET` | Restart the broker with the correct secret |
| `Connection refused` | Broker not running | `./broker` or `docker compose up` |
| App 5 returns empty events | Admin token expired | Re-run the aactl command or re-authenticate |
| App 9 shows all `PASS` | Ceiling is too wide — all test scopes are allowed | Narrow the ceiling so `admin:revoke:*` and `read:logs:*` are outside it |
