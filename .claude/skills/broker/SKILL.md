---
name: broker
description: Use when needing to start, stop, or check the AgentAuth core broker for integration testing, live verification, or acceptance tests
---

# Broker Management

Manage the AgentAuth core broker Docker stack for local SDK testing.

## Usage

- `/broker up` — Start the broker
- `/broker down` — Stop the broker
- `/broker status` — Check if broker is running and healthy

## Instructions

Parse the argument from the skill invocation. Default to `status` if no argument given.

### Configuration

| Variable | Default | Override |
|----------|---------|----------|
| `AA_ADMIN_SECRET` | `live-test-secret-32bytes-long-ok` | Pass as second arg: `/broker up mysecret` |
| `AA_HOST_PORT` | `8080` | Set env var before invoking |
| Core project path | `~/proj/agentauth-core` | — |

### `up`

```bash
export AA_ADMIN_SECRET="${SECRET:-live-test-secret-32bytes-long-ok}"
cd ~/proj/agentauth-core
./scripts/stack_up.sh
```

After stack_up completes, run a health check:

```bash
curl -sf http://127.0.0.1:${AA_HOST_PORT:-8080}/v1/health
```

Report success or failure clearly. If health check fails, wait 3 seconds and retry once — the broker may need a moment after `docker compose up -d`.

### `down`

```bash
cd ~/proj/agentauth-core
./scripts/stack_down.sh
```

### `status`

```bash
curl -sf http://127.0.0.1:${AA_HOST_PORT:-8080}/v1/health
```

Report whether the broker is reachable. If not, suggest `/broker up`.

## Output Format

Always announce the action and result:

```
Broker: [action] — [result]
```

Examples:
- `Broker: up — healthy at http://127.0.0.1:8080`
- `Broker: down — stack removed`
- `Broker: status — not reachable (run /broker up)`
