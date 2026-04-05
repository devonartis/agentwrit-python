# Demo App v3 — "Three Stories, One Broker" Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a three-panel interactive demo app where users type natural language, LLM agents process it with scoped credentials, and the broker validates every tool call in real-time — across three domains (Healthcare, Trading, DevOps).

**Architecture:** FastAPI + Jinja2 + HTMX + SSE. Single-page app with three panels: agents (left), event stream (center), scope enforcement (right). The user picks a story, types a prompt, and watches the credential lifecycle unfold. Mock data backends, real broker enforcement. One real stock price API for the trading story.

**Tech Stack:** FastAPI, Jinja2, HTMX 2.x, SSE, AgentAuth Python SDK, OpenAI/Anthropic (auto-detected), httpx, uvicorn

**Design doc:** `.plans/designs/2026-04-01-demo-app-design-v3.md`
**Old app reference:** `~/proj/agentauth-app/app/web/` (three-panel layout, SSE, enforcement cards)
**SDK API:** `src/agentauth/app.py` — `get_token()`, `validate_token()`, `delegate()`, `revoke_token()`
**Branch:** `feature/demo-app`

---

## Important Context for the Implementing Agent

### SDK API Quick Reference

```python
from agentauth import AgentAuthApp, ScopeCeilingError, AuthenticationError

# Initialize (authenticates app immediately)
client = AgentAuthApp(broker_url, client_id, client_secret)

# Get scoped token for an agent (handles challenge-response internally)
token: str = client.get_token(agent_name="triage-agent", scope=["patient:read:intake"])

# Validate a token (returns {"valid": bool, "claims": {...}})
result = client.validate_token(token)

# Delegate attenuated scope to another agent
delegated: str = client.delegate(token, to_agent_id="spiffe://...", scope=["patient:read:vitals"])

# Revoke a token
client.revoke_token(token)
```

### Broker Admin API (for app registration at startup)

```python
# 1. Admin auth
resp = httpx.post(f"{broker_url}/v1/admin/auth", json={"secret": admin_secret})
admin_token = resp.json()["access_token"]

# 2. Register app with ceiling
resp = httpx.post(f"{broker_url}/v1/admin/apps",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={"name": "healthcare-app", "scopes": [...ceiling...], "token_ttl": 300})
client_id = resp.json()["client_id"]
client_secret = resp.json()["client_secret"]
```

### Reusable v2 Code (salvage from current `examples/demo-app/`)

- `_chat(client, provider, prompt, max_tokens)` — unified OpenAI/Anthropic call (agents.py:35-55)
- `_extract_json(text)` — handles markdown code blocks (agents.py:61-75)
- `_create_llm_client()` — auto-detect OpenAI/Anthropic from env (app.py:76-94)
- `validate_env()` — check required env vars (app.py:57-73)
- `lifespan()` pattern — startup hooks (app.py:97-166)

### Project Conventions

- **`uv` only** — never pip/poetry. Run: `uv run pytest`, `uv run uvicorn`, etc.
- **Strict types** — every variable, parameter, return annotated. `mypy --strict` on src/.
- **Gates after each commit:** `uv run ruff check .`, `uv run mypy --strict src/`, `uv run pytest tests/unit/`
- **Comments** explain WHY, not WHAT.

---

## Task 1: Scaffold v3 Directory Structure

**Files:**
- Delete: `examples/demo-app/pipeline.py` (v2 batch pipeline — replaced entirely)
- Delete: `examples/demo-app/dashboard.py` (v2 polling dashboard — replaced by SSE)
- Delete: `examples/demo-app/data.py` (v2 financial data — replaced by story modules)
- Delete: `examples/demo-app/templates/index.html` (v2 two-column layout)
- Delete: `examples/demo-app/templates/partials/` (all v2 partials)
- Delete: `examples/demo-app/static/style.css` (v2 styling)
- Keep: `examples/demo-app/app.py` (will be rewritten)
- Keep: `examples/demo-app/agents.py` (will be rewritten, salvaging `_chat` and `_extract_json`)
- Keep: `examples/demo-app/pyproject.toml` (update deps)
- Create directories:
  - `examples/demo-app/stories/`
  - `examples/demo-app/tools/`
  - `examples/demo-app/templates/partials/agent_cards/`
  - `examples/demo-app/static/`

**Step 1: Delete v2 files**

```bash
cd examples/demo-app
rm -f pipeline.py dashboard.py data.py
rm -f templates/index.html
rm -rf templates/partials/
rm -f static/style.css
```

**Step 2: Create v3 directories**

```bash
mkdir -p stories tools templates/partials/agent_cards static
touch stories/__init__.py tools/__init__.py
```

**Step 3: Update pyproject.toml**

Add `htmx` isn't a Python dep (it's a JS CDN include), but ensure these deps are present:

```toml
[project]
name = "agentauth-demo"
version = "0.3.0"
requires-python = ">=3.11"
dependencies = [
    "agentauth @ file:///${PROJECT_ROOT}/../..",
    "openai>=1.0",
    "anthropic>=0.49",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "jinja2>=3.1",
    "httpx>=0.28",
]
```

**Step 4: Commit**

```bash
git add -A examples/demo-app/
git commit -m "chore(demo): scaffold v3 directory structure, remove v2 files"
```

---

## Task 2: Story Data — Healthcare

**Files:**
- Create: `examples/demo-app/stories/healthcare.py`

**Step 1: Write the healthcare story module**

Contains: ceiling, mock patients (5), tool definitions (6), preset prompts (5), agent definitions.

```python
"""Healthcare story — Patient Triage.

Ceiling deliberately excludes patient:read:billing.
Specialist Agent is never registered (C6 trigger).
"""

from __future__ import annotations

from typing import Any

# -- Ceiling (registered with broker when user picks this story) --

CEILING: list[str] = [
    "patient:read:intake",
    "patient:read:vitals",
    "patient:read:history",
    "patient:write:prescription",
    "patient:read:referral",
]

# -- Mock patients --

PATIENTS: dict[str, dict[str, Any]] = {
    "PAT-001": {
        "id": "PAT-001",
        "name": "Lewis Smith",
        "age": 67,
        "intake": {
            "chief_complaint": "Chest pain and shortness of breath",
            "arrival_time": "14:02",
            "triage_notes": "Alert, diaphoretic, BP elevated",
        },
        "vitals": {
            "blood_pressure": "168/95",
            "heart_rate": 102,
            "o2_saturation": 94,
            "temperature": 98.6,
        },
        "history": {
            "conditions": ["Coronary artery disease", "Hypertension", "Hyperlipidemia"],
            "medications": ["Warfarin 5mg daily", "Metoprolol 50mg BID", "Atorvastatin 40mg daily"],
            "allergies": ["Penicillin"],
        },
    },
    "PAT-002": {
        "id": "PAT-002",
        "name": "Maria Garcia",
        "age": 34,
        "intake": {
            "chief_complaint": "Severe migraine, 3 days duration",
            "arrival_time": "09:15",
            "triage_notes": "Photophobia, nausea, no focal deficits",
        },
        "vitals": {
            "blood_pressure": "122/78",
            "heart_rate": 76,
            "o2_saturation": 99,
            "temperature": 98.2,
        },
        "history": {
            "conditions": ["Chronic migraines"],
            "medications": ["Sumatriptan PRN"],
            "allergies": [],
        },
    },
    "PAT-003": {
        "id": "PAT-003",
        "name": "James Chen",
        "age": 45,
        "intake": {
            "chief_complaint": "Routine diabetes follow-up, feeling dizzy",
            "arrival_time": "11:30",
            "triage_notes": "Appears fatigued, glucose 287 on finger stick",
        },
        "vitals": {
            "blood_pressure": "145/92",
            "heart_rate": 88,
            "o2_saturation": 97,
            "temperature": 99.1,
        },
        "history": {
            "conditions": ["Type 2 Diabetes", "Hypertension"],
            "medications": ["Metformin 1000mg BID", "Lisinopril 20mg daily"],
            "allergies": ["Sulfa drugs"],
            "last_a1c": 8.2,
        },
    },
    "PAT-004": {
        "id": "PAT-004",
        "name": "Sarah Johnson",
        "age": 28,
        "intake": {
            "chief_complaint": "Routine prenatal checkup, 32 weeks",
            "arrival_time": "10:00",
            "triage_notes": "No complaints, routine visit",
        },
        "vitals": {
            "blood_pressure": "118/72",
            "heart_rate": 82,
            "o2_saturation": 99,
            "temperature": 98.4,
        },
        "history": {
            "conditions": ["Pregnancy (32 weeks, uncomplicated)"],
            "medications": ["Prenatal vitamins", "Iron supplement"],
            "allergies": [],
        },
    },
    "PAT-005": {
        "id": "PAT-005",
        "name": "Robert Kim",
        "age": 72,
        "intake": {
            "chief_complaint": "Family reports increased confusion",
            "arrival_time": "16:45",
            "triage_notes": "Oriented x1, family at bedside, multiple medication bottles",
        },
        "vitals": {
            "blood_pressure": "132/84",
            "heart_rate": 68,
            "o2_saturation": 96,
            "temperature": 97.8,
        },
        "history": {
            "conditions": ["Early-stage dementia", "Atrial fibrillation", "Osteoarthritis", "GERD"],
            "medications": [
                "Donepezil 10mg daily", "Apixaban 5mg BID",
                "Acetaminophen 500mg TID", "Omeprazole 20mg daily",
                "Amlodipine 5mg daily", "Sertraline 50mg daily",
                "Vitamin D 2000IU daily", "Calcium 600mg BID",
            ],
            "allergies": ["Aspirin", "Codeine"],
        },
    },
}

# -- Agent definitions --

AGENTS: list[dict[str, Any]] = [
    {
        "name": "triage-agent",
        "display_name": "Triage Agent",
        "scope": ["patient:read:intake"],
        "token_type": "own",
        "role": "Classifies urgency and department, routes to specialists",
    },
    {
        "name": "diagnosis-agent",
        "display_name": "Diagnosis Agent",
        "scope": ["patient:read:vitals", "patient:read:history"],
        "token_type": "delegated",
        "delegated_from": "triage-agent",
        "role": "Reads vitals and history, assesses condition",
    },
    {
        "name": "prescription-agent",
        "display_name": "Prescription Agent",
        "scope": ["patient:write:prescription"],
        "token_type": "own",
        "short_ttl": 120,
        "role": "Writes prescriptions. Short TTL — 2 minutes",
    },
    {
        "name": "specialist-agent",
        "display_name": "Specialist Agent",
        "scope": [],
        "token_type": "unregistered",
        "role": "Never registered — delegation rejected (C6)",
    },
]

# -- Tool definitions --

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_patient_intake",
        "description": "Get intake information for a patient (chief complaint, arrival, triage notes).",
        "parameters": {
            "type": "object",
            "properties": {"patient_id": {"type": "string", "description": "Patient ID (e.g. PAT-001)"}},
            "required": ["patient_id"],
        },
        "required_scope": "patient:read:intake",
        "user_bound": True,
    },
    {
        "name": "get_patient_vitals",
        "description": "Get current vital signs for a patient (BP, heart rate, O2, temperature).",
        "parameters": {
            "type": "object",
            "properties": {"patient_id": {"type": "string", "description": "Patient ID (e.g. PAT-001)"}},
            "required": ["patient_id"],
        },
        "required_scope": "patient:read:vitals",
        "user_bound": True,
    },
    {
        "name": "get_patient_history",
        "description": "Get medical history for a patient (conditions, medications, allergies).",
        "parameters": {
            "type": "object",
            "properties": {"patient_id": {"type": "string", "description": "Patient ID (e.g. PAT-001)"}},
            "required": ["patient_id"],
        },
        "required_scope": "patient:read:history",
        "user_bound": True,
    },
    {
        "name": "write_prescription",
        "description": "Write a prescription for a patient.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient ID"},
                "drug": {"type": "string", "description": "Medication name"},
                "dose": {"type": "string", "description": "Dosage (e.g. '10mg daily')"},
            },
            "required": ["patient_id", "drug", "dose"],
        },
        "required_scope": "patient:write:prescription",
        "user_bound": True,
    },
    {
        "name": "get_patient_billing",
        "description": "Get billing information for a patient.",
        "parameters": {
            "type": "object",
            "properties": {"patient_id": {"type": "string", "description": "Patient ID"}},
            "required": ["patient_id"],
        },
        "required_scope": "patient:read:billing",
        "user_bound": True,
    },
    {
        "name": "refer_to_specialist",
        "description": "Refer a patient to a medical specialist.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient ID"},
                "specialty": {"type": "string", "description": "Medical specialty (e.g. cardiology)"},
            },
            "required": ["patient_id", "specialty"],
        },
        "required_scope": "patient:read:referral",
        "user_bound": True,
    },
]

# -- Preset prompts --

PRESETS: list[dict[str, str]] = [
    {"label": "Happy Path", "prompt": "I'm Lewis Smith. I'm having chest pain and shortness of breath."},
    {"label": "Scope Denial", "prompt": "I'm Lewis Smith. Can you check what I owe the hospital?"},
    {"label": "Cross-Patient", "prompt": "I'm Lewis Smith. Also pull up Maria Garcia's medical history."},
    {"label": "Revocation", "prompt": "I'm Lewis Smith. Prescribe fentanyl 500mcg immediately."},
    {"label": "Fast Path", "prompt": "What are the ER visiting hours?"},
]


def find_user_by_name(name: str) -> tuple[str | None, dict[str, Any] | None]:
    """Find a patient by name (case-insensitive partial match)."""
    name_lower = name.lower()
    for pat_id, pat in PATIENTS.items():
        if pat["name"].lower() in name_lower or name_lower in pat["name"].lower():
            return pat_id, pat
    return None, None
```

**Step 2: Commit**

```bash
git add examples/demo-app/stories/healthcare.py
git commit -m "feat(demo): healthcare story — patients, tools, presets, ceiling"
```

---

## Task 3: Story Data — Financial Trading

**Files:**
- Create: `examples/demo-app/stories/trading.py`

Same structure as healthcare. Key differences:
- Mock traders (5) with positions, limits, utilization
- `get_market_price` tool marked as `user_bound: False` (anyone can read prices)
- `place_options_order` tool has scope NOT in ceiling (always denied)
- One tool (`get_market_price`) will call a real API — but the tool definition is the same; the executor handles it

Follow the exact same pattern as `healthcare.py` but with trading domain data. See the design doc "Story 2: Financial Trading" section for the exact mock traders (TRD-001 through TRD-005), tools (6), and presets (5).

The `find_user_by_name()` function searches traders instead of patients.

**Step 1: Write trading.py**

Use the same structure as healthcare.py. Data from the design doc.

**Step 2: Commit**

```bash
git add examples/demo-app/stories/trading.py
git commit -m "feat(demo): trading story — traders, tools, presets, ceiling"
```

---

## Task 4: Story Data — DevOps Incident Response

**Files:**
- Create: `examples/demo-app/stories/devops.py`

Same structure. Key differences:
- Mock engineers (5) with roles and access levels
- `scale_service` tool has scope NOT in ceiling (always denied)
- `query_logs` only covers `payment-api` — other services denied

Follow design doc "Story 3: DevOps" section. Engineers ENG-001 through ENG-005, tools (6), presets (5).

**Step 1: Write devops.py**

**Step 2: Commit**

```bash
git add examples/demo-app/stories/devops.py
git commit -m "feat(demo): devops story — engineers, tools, presets, ceiling"
```

---

## Task 5: Story Registry

**Files:**
- Create: `examples/demo-app/stories/__init__.py`

Unified interface for accessing any story's data by name.

```python
"""Story registry — look up ceiling, agents, tools, users, presets by story name."""

from __future__ import annotations

from typing import Any

from stories import healthcare, trading, devops

_STORIES: dict[str, Any] = {
    "healthcare": healthcare,
    "trading": trading,
    "devops": devops,
}


def get_story(name: str) -> Any:
    """Return a story module by name. Raises KeyError if not found."""
    return _STORIES[name]


def get_story_names() -> list[str]:
    """Return available story names."""
    return list(_STORIES.keys())
```

**Step 1: Write __init__.py**

**Step 2: Commit**

```bash
git add examples/demo-app/stories/__init__.py
git commit -m "feat(demo): story registry — unified access to all three stories"
```

---

## Task 6: Tool Registry & Executor

**Files:**
- Create: `examples/demo-app/tools/definitions.py`
- Create: `examples/demo-app/tools/executor.py`
- Create: `examples/demo-app/tools/stock_api.py`

### definitions.py

Adapts the old app's `tools/definitions.py` pattern. Functions:
- `get_tools_for_story(story_name)` → list of tool dicts
- `get_tool_by_name(story_name, tool_name)` → tool dict or None
- `to_openai_tools(tools)` → OpenAI function-calling format
- `scope_matches(required, agent_scopes, ceiling)` → bool + enforcement level

### executor.py

Mock tool execution. Dispatches by tool name, looks up data from the active story module.

```python
def execute_tool(story_name: str, tool_name: str, args: dict) -> Any:
    """Execute a mock tool. Returns the tool result (dict/string)."""
```

Each tool reads from the story's mock data dicts. Example:
- `get_patient_vitals(patient_id="PAT-001")` → `healthcare.PATIENTS["PAT-001"]["vitals"]`
- `place_order(symbol, qty, side)` → `{"order_id": "ORD-{uuid}", "status": "filled", ...}`
- `restart_service(service, cluster)` → `{"status": "restarted", "new_pid": random_int, ...}`

### stock_api.py

Real stock price API call for the trading story.

```python
import httpx

async def get_stock_price(symbol: str) -> dict[str, Any]:
    """Fetch real stock price from a free API. Returns {"symbol": ..., "price": ..., "source": ...}."""
    # Use a free endpoint (e.g., Yahoo Finance via query, or similar)
    # Fallback to mock data if the API is unreachable
```

**Step 1: Write definitions.py with scope matching logic**

Reference the old app's `_scope_matches_any()` for wildcard and narrowed scope matching.

**Step 2: Write executor.py with all mock tool implementations**

**Step 3: Write stock_api.py**

**Step 4: Commit**

```bash
git add examples/demo-app/tools/
git commit -m "feat(demo): tool registry, mock executor, real stock price API"
```

---

## Task 7: Identity Resolution

**Files:**
- Create: `examples/demo-app/identity.py`

```python
"""Identity resolution — deterministic, before LLM.

Looks up user names in the active story's mock user table.
Returns (user_id, user_record) or (None, None).
"""

from __future__ import annotations

from typing import Any

from stories import get_story


def resolve_identity(story_name: str, text: str) -> tuple[str | None, dict[str, Any] | None]:
    """Find a user mentioned in the text from the active story's user table."""
    story = get_story(story_name)
    return story.find_user_by_name(text)
```

**Step 1: Write identity.py**

**Step 2: Commit**

```bash
git add examples/demo-app/identity.py
git commit -m "feat(demo): identity resolution across story user tables"
```

---

## Task 8: Enforcement Engine

**Files:**
- Create: `examples/demo-app/enforcement.py`

Adapts the old app's `_enforce_tool_call()` from `~/proj/agentauth-app/app/web/pipeline.py:180-298`.

```python
"""Broker-centric tool-call enforcement.

Before any tool executes:
1. Validate token with broker (sig, exp, rev)
2. Check if required scope (optionally narrowed with user_id) is in validated scopes
3. Return allowed/denied with enforcement details

The broker does ALL enforcement. No Python if-statements for access control.
"""

from __future__ import annotations

from typing import Any

from agentauth import AgentAuthApp


def enforce_tool_call(
    client: AgentAuthApp,
    agent_token: str,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_def: dict[str, Any],
    requester_id: str | None,
    ceiling: set[str],
) -> dict[str, Any]:
    """Validate a tool call against the broker.

    Returns dict with:
        status: "allowed" | "scope_denied" | "data_denied"
        scope: the scope that was checked
        enforcement: "ALLOWED" | "HARD_DENY" | "ESCALATION" | "DATA_BOUNDARY"
        broker_checks: {"sig": bool, "exp": bool, "rev": bool, "scope": bool}
        result: tool output (if allowed) or denial message
    """
```

Key logic (from old app):
- If `tool_def["user_bound"]` and `requester_id`: append `:requester_id` to required scope
- Call `client.validate_token(agent_token)` → get claims
- Extract `scope` from claims
- Check if narrowed scope is in validated scopes
- If not: determine HARD_DENY (not in ceiling) vs ESCALATION (in ceiling but not provisioned) vs DATA_BOUNDARY (wrong user ID)

**Step 1: Write enforcement.py**

Reference: `~/proj/agentauth-app/app/web/pipeline.py` lines 180-298 for the pattern.

**Step 2: Commit**

```bash
git add examples/demo-app/enforcement.py
git commit -m "feat(demo): broker-centric tool-call enforcement engine"
```

---

## Task 9: LLM Agent Wrapper

**Files:**
- Rewrite: `examples/demo-app/agents.py`

Salvage from v2: `_chat()`, `_extract_json()`. Add tool-calling loop.

```python
"""LLM agent wrapper — register, call, tool loop.

Supports OpenAI and Anthropic. Each agent:
1. Registers with AgentAuth (gets SPIFFE ID + scoped token)
2. Makes LLM calls with tool definitions
3. Handles tool-call responses in a loop
"""

from __future__ import annotations

from typing import Any


def chat(client: Any, provider: str, messages: list[dict], *,
         tools: list[dict] | None = None, temperature: float = 0.3,
         max_tokens: int = 1024) -> tuple[list[dict] | None, str | None]:
    """Unified LLM call. Returns (tool_calls, text_content).

    If the LLM wants to call tools: tool_calls is a list, text_content may be None.
    If the LLM responds with text: tool_calls is None, text_content is the response.
    """


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON from LLM response, handling markdown code blocks."""
```

The tool-calling loop lives in the pipeline runner, not here. This module provides the primitives: `chat()` and `extract_json()`.

**Step 1: Write agents.py**

Salvage `_chat` from v2 `examples/demo-app/agents.py:35-55`. Extend to support tool calling (OpenAI `tools` parameter, Anthropic `tools` parameter).

**Step 2: Commit**

```bash
git add examples/demo-app/agents.py
git commit -m "feat(demo): LLM agent wrapper — chat with tool support"
```

---

## Task 10: Pipeline Runner

**Files:**
- Create: `examples/demo-app/pipeline.py`

This is the core of the demo. An async generator that yields SSE event dicts.

Adapts the old app's `PipelineRunner` from `~/proj/agentauth-app/app/web/pipeline.py:347-1019`.

```python
"""Pipeline runner — identity-first, triage-driven routing with SSE events.

Yields event dicts that the SSE endpoint streams to the browser.
The JS handler routes each event type to the correct panel.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from agentauth import AgentAuthApp, ScopeCeilingError


class PipelineRunner:
    """Runs the story pipeline, yielding SSE events."""

    def __init__(
        self,
        client: AgentAuthApp,
        llm_client: Any,
        llm_provider: str,
        story_name: str,
        user_input: str,
        requester_id: str | None,
        requester: dict[str, Any] | None,
    ) -> None:
        ...

    async def run(self) -> AsyncGenerator[dict[str, Any], None]:
        """Execute the pipeline, yielding SSE event dicts."""
        # Phase 1: Identity (already resolved by caller)
        # Phase 2: Triage Agent (LLM classification)
        # Phase 3: Route selection
        # Phase 4: Specialist agents with tool loop
        # Phase 5: Safety checks / revocation
        # Phase 6: Audit trail + summary
        ...
```

**Key implementation details:**

1. **Triage Agent** — gets own token, makes LLM call to classify the request, parses JSON response for urgency/department/routing
2. **Route selection** — based on triage output, decide which specialist agents to invoke. Each story can define its own routing rules.
3. **Specialist tool loop** — register agent → get tools for its scope → LLM call with tools → for each tool_call: enforce via broker → execute if allowed → feed result back → repeat until LLM stops calling tools or hits denial
4. **Delegation** — for agents marked `token_type: "delegated"`: get parent token, validate to extract agent_id, call `client.delegate()`
5. **C6 trigger** — for agents marked `token_type: "unregistered"`: attempt delegation, catch the error, emit `delegation_rejected` event
6. **Revocation** — detect safety triggers (dangerous dosage, over-limit trade, overly broad restart), revoke token, validate revoked token to prove it's dead
7. **Cleanup** — fetch audit trail from broker if admin token available, emit summary

**Reference heavily:** `~/proj/agentauth-app/app/web/pipeline.py` for the exact SSE event types and the enforcement flow.

**Step 1: Write pipeline.py**

**Step 2: Commit**

```bash
git add examples/demo-app/pipeline.py
git commit -m "feat(demo): pipeline runner — SSE event generator with tool loop"
```

---

## Task 11: FastAPI App & Routes

**Files:**
- Rewrite: `examples/demo-app/app.py`

```python
"""FastAPI entry point — startup, story registration, SSE streaming."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from agentauth import AgentAuthApp


@dataclass
class AppState:
    """Shared mutable state."""
    broker_url: str = ""
    admin_token: str = ""
    agentauth_client: AgentAuthApp | None = None
    llm_client: Any = None
    llm_provider: str = ""
    active_story: str = ""
    client_id: str = ""
    client_secret: str = ""


# Routes:
# GET  /                          → main page (app.html)
# POST /api/register/{story}     → register story app with broker (HTMX)
# POST /api/run                  → start pipeline run
# GET  /api/stream/{run_id}      → SSE endpoint
# GET  /api/presets/{story}      → preset buttons partial (HTMX)
# GET  /api/agents/{story}       → agent cards partial (HTMX)
```

**Startup (lifespan):**
1. Validate env vars (`AA_ADMIN_SECRET`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
2. Check broker health (`GET /v1/health`)
3. Admin auth (`POST /v1/admin/auth`)
4. Create LLM client (auto-detect provider)
5. Store in AppState — but do NOT register any app yet (that happens when user picks a story)

**Story registration route (`POST /api/register/{story}`):**
1. Register app with broker using the story's ceiling
2. Create `AgentAuthApp` with returned client_id/client_secret
3. Store in AppState
4. Return HTMX partial: agent cards for the selected story

**SSE route (`GET /api/stream/{run_id}`):**
1. Look up run config from `_runs` dict
2. Create `PipelineRunner`
3. Yield events as SSE `data:` lines

**Step 1: Write app.py**

Salvage `validate_env()`, `_create_llm_client()`, `lifespan()` pattern from v2.

**Step 2: Commit**

```bash
git add examples/demo-app/app.py
git commit -m "feat(demo): FastAPI app — routes, startup, story registration"
```

---

## Task 12: Frontend — HTML Template

**Files:**
- Create: `examples/demo-app/templates/app.html`

Single-page layout. Adapt from `~/proj/agentauth-app/app/web/templates/app.html`.

**Structure:**
1. `<head>` — meta, title, inline CSS (or link to style.css), HTMX CDN
2. **Top bar** — brand, story buttons, textarea, RUN button
3. **Three panels** — left (agents), center (event stream), right (enforcement)
4. `<script>` — SSE handler, event routing, UI update functions

**Top bar story buttons use HTMX:**
```html
<button class="scenario-btn"
        hx-post="/api/register/healthcare"
        hx-target="#agent-panel"
        hx-swap="innerHTML"
        onclick="setStory('healthcare', this)">Healthcare</button>
```

**SSE connection uses vanilla JS:**
```javascript
async function runDemo() {
    const resp = await fetch('/api/run', { method: 'POST', body: formData });
    const { run_id } = await resp.json();
    const es = new EventSource(`/api/stream/${run_id}`);
    es.onmessage = (e) => handleEvent(JSON.parse(e.data));
}
```

**Event handler updates all three panels from one event:**
```javascript
function handleEvent(data) {
    switch(data.type) {
        case 'agent_registered': updateAgentCard(data); addStreamEvent(data); break;
        case 'tool_call': addEnforcementCard(data); addStreamEvent(data); break;
        case 'tool_allowed': updateEnforcementCard(data); addStreamEvent(data); break;
        // ... etc
    }
}
```

**Reference:** `~/proj/agentauth-app/app/web/templates/app.html` — copy the three-panel CSS layout, event stream formatting, enforcement card styling, and agent card styling. Adapt the JS event handler for the v3 event types listed in the design doc.

**Step 1: Write app.html with all CSS inline (or in style.css — your choice)**

The old app had all CSS inline in the HTML. This is fine for a demo. But if you prefer a separate file, put it in `static/style.css`.

**Step 2: Commit**

```bash
git add examples/demo-app/templates/ examples/demo-app/static/
git commit -m "feat(demo): frontend — three-panel layout with SSE + HTMX"
```

---

## Task 13: HTMX Partials

**Files:**
- Create: `examples/demo-app/templates/partials/agent_cards/healthcare.html`
- Create: `examples/demo-app/templates/partials/agent_cards/trading.html`
- Create: `examples/demo-app/templates/partials/agent_cards/devops.html`
- Create: `examples/demo-app/templates/partials/presets.html`
- Create: `examples/demo-app/templates/partials/identity.html`

**Agent cards partial (example — healthcare.html):**
```html
<div class="panel-section-label">Agents</div>

<div class="agent-card" id="card-triage-agent">
  <div class="agent-card-header">
    <span class="agent-card-name">Triage Agent</span>
    <span class="agent-status-dot" id="dot-triage-agent"></span>
  </div>
  <div class="agent-spiffe" id="spiffe-triage-agent"></div>
  <div class="agent-scopes" id="scopes-triage-agent"></div>
  <div class="agent-status-text" id="status-triage-agent">Waiting</div>
</div>

<!-- Repeat for diagnosis-agent, prescription-agent, specialist-agent -->
```

**Presets partial (rendered per story):**
```html
{% for preset in presets %}
<button class="scenario-btn" onclick="setPreset('{{ preset.prompt | e }}', this)">
    {{ preset.label }}
</button>
{% endfor %}
```

These are swapped in by HTMX when the user clicks a story button.

**Step 1: Write all partials**

**Step 2: Commit**

```bash
git add examples/demo-app/templates/partials/
git commit -m "feat(demo): HTMX partials — agent cards, presets, identity"
```

---

## Task 14: Wire Everything Together

**Files:**
- Modify: `examples/demo-app/app.py` (final wiring)
- Create: `examples/demo-app/tools/__init__.py` (exports)
- Create: `examples/demo-app/stories/__init__.py` (if not already complete)

Make sure all imports work, the app starts, and HTMX/SSE connections are correct.

**Step 1: Verify imports and module references**

Run:
```bash
cd examples/demo-app && uv run python -c "from app import app; print('OK')"
```

**Step 2: Start the app and verify the page loads**

```bash
cd examples/demo-app
AA_ADMIN_SECRET="live-test-secret-32bytes-long-ok" OPENAI_API_KEY="sk-..." uv run uvicorn app:app --reload
# Open http://localhost:8000 — verify three-panel layout renders
```

**Step 3: Commit**

```bash
git add examples/demo-app/
git commit -m "feat(demo): wire all modules together, app starts"
```

---

## Task 15: Integration Test — Happy Path

**Files:**
- Create: `examples/demo-app/tests/test_smoke.py`

Requires live broker (`/broker up`).

```python
"""Smoke test — verify the demo app starts and processes a happy-path request."""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.integration
def test_app_starts():
    """The demo app responds to GET /."""
    resp = httpx.get(f"{BASE}/")
    assert resp.status_code == 200
    assert "AgentAuth" in resp.text


@pytest.mark.integration
def test_register_healthcare():
    """Registering the healthcare story succeeds."""
    resp = httpx.post(f"{BASE}/api/register/healthcare")
    assert resp.status_code == 200
    assert "triage-agent" in resp.text.lower() or resp.status_code == 200


@pytest.mark.integration
def test_happy_path_healthcare():
    """A happy-path healthcare run completes with events."""
    # Register story first
    httpx.post(f"{BASE}/api/register/healthcare")

    # Start run
    resp = httpx.post(f"{BASE}/api/run", data={
        "story": "healthcare",
        "user_input": "I'm Lewis Smith. I'm having chest pain.",
    })
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    # Consume SSE stream
    events = []
    with httpx.stream("GET", f"{BASE}/api/stream/{run_id}") as stream:
        for line in stream.iter_lines():
            if line.startswith("data: "):
                import json
                events.append(json.loads(line[6:]))
                if events[-1].get("type") == "done":
                    break

    event_types = [e["type"] for e in events]
    assert "identity_resolved" in event_types
    assert "agent_registered" in event_types
    assert "done" in event_types
```

**Step 1: Write test_smoke.py**

**Step 2: Start broker and app, run tests**

```bash
# Terminal 1: broker
/broker up

# Terminal 2: app
cd examples/demo-app
AA_ADMIN_SECRET="live-test-secret-32bytes-long-ok" OPENAI_API_KEY="sk-..." uv run uvicorn app:app --port 8000

# Terminal 3: tests
cd examples/demo-app
uv run pytest tests/test_smoke.py -v -m integration
```

**Step 3: Commit**

```bash
git add examples/demo-app/tests/
git commit -m "test(demo): integration smoke tests — startup, registration, happy path"
```

---

## Task 16: Browser Verification — All Presets

**Use `chrome-devtools` MCP or `playwright` MCP to automate browser testing of all 15 presets.**
Invoke the `chrome-devtools` skill (or `chrome-devtools-cli` for shell scripts) to drive the browser.

The implementing agent MUST use browser automation — not just API calls. The point is to verify that the three-panel UI actually updates correctly: agent cards change state, enforcement cards slide in, event stream populates, summary card appears.

### Setup

1. Start broker: `/broker up`
2. Start app: `cd examples/demo-app && AA_ADMIN_SECRET="..." OPENAI_API_KEY="sk-..." uv run uvicorn app:app --port 8000`
3. Navigate browser to `http://localhost:8000`

### For each story (Healthcare, Trading, DevOps):

**Step 1: Click the story button**
- Verify: agent cards appear in left panel
- Verify: preset buttons appear in top bar
- Verify: event stream shows `[BROKER] App registered: {story}-app`

**Step 2: Run each preset (5 per story = 15 total)**

For each preset:
1. Click the preset button (populates textarea)
2. Click RUN
3. Wait for the `done` event (summary card appears)
4. Verify by checking DOM:

### Healthcare Verification Matrix

| Preset | Left Panel | Center Stream | Right Panel |
|--------|-----------|---------------|-------------|
| Happy Path | Identity green (Lewis Smith). Triage → green. Diagnosis → green (delegated scopes flash). Prescription → green. Specialist → ✗ unreg. | `[BROKER]` registration events. `[TRIAGE]` classification. `[DIAGNOSIS]` working. Tool calls ALLOWED. Delegation rejected for specialist. | Enforcement cards: get_vitals ALLOWED, get_history ALLOWED. Delegation rejected card. Summary: N passed, 1 denied. |
| Scope Denial | Identity green. Triage → green. | `[POLICY]` billing HARD DENY | get_patient_billing → red HARD DENY card. "NOT in ceiling" message. |
| Cross-Patient | Identity green (Lewis Smith). | `[POLICY]` DATA BOUNDARY DENIED | Enforcement card: get_patient_history → red DATA BOUNDARY. scope `patient:read:history:PAT-002` not in token. |
| Revocation | Identity green. Prescription agent → red REVOKED. | `[BROKER]` revocation event. Post-revocation check. | Revocation confirmed card. Summary shows denied. |
| Fast Path | Identity amber (anonymous). | `[SYSTEM]` LLM responds directly. No tool calls. | No enforcement cards. Summary: 0 tool calls. |

### Trading Verification Matrix

| Preset | Left Panel | Center Stream | Right Panel |
|--------|-----------|---------------|-------------|
| Happy Path | Identity green (Alex Rivera). Strategy → green. Order → green (delegated). Risk → green. Settlement → green. Hedging → ✗ unreg. | `[BROKER]` events. Real AAPL price in stream. Order placed. | get_market_price ALLOWED (real data). place_order ALLOWED. Delegation rejected for hedging. |
| Scope Denial | Identity green (Sofia Tanaka). | `[POLICY]` options HARD DENY | place_options_order → red HARD DENY. |
| Cross-Trader | Identity green (Marcus Webb). | `[POLICY]` DATA BOUNDARY | get_positions → red DATA BOUNDARY. `TRD-001` not in token. |
| Revocation | Identity green (Marcus Webb). Order agent → red REVOKED. | `[BROKER]` Risk Agent triggers revocation. | Revocation confirmed. Over-limit message. |
| Fast Path | Identity amber. | AAPL price returned (non-bound tool works). | get_market_price ALLOWED. No user-bound tools called. |

### DevOps Verification Matrix

| Preset | Left Panel | Center Stream | Right Panel |
|--------|-----------|---------------|-------------|
| Happy Path | Identity green (Jordan Lee). Triage → green. Log Analyzer → green (delegated). Remediation → green. Notification → green. Compliance → ✗ unreg. | Full incident flow. Logs queried. Service restarted. Slack sent. | query_logs ALLOWED. restart_service ALLOWED. Delegation rejected for compliance. |
| Scope Denial | Identity green. | `[POLICY]` scale HARD DENY | scale_service → red HARD DENY. |
| Wrong Service | Identity green (Casey Miller). | `[POLICY]` auth-service DENIED | query_logs(service="auth-service") → red DENIED. Only payment-api in ceiling. |
| Revocation | Identity green. Remediation → red REVOKED. | `[BROKER]` safety flag, revocation. | Revocation confirmed. Broad restart blocked. |
| No Access | Identity amber (Sam Brooks not found) or denied. | `[POLICY]` tools denied for unauthorized user. | User-bound tools DENIED. Broker enforcement visible. |

**Step 3: Take a screenshot after each preset run for evidence**

Use `take_screenshot` to capture the three-panel state after each preset completes.

**Step 4: Fix any issues found, commit**

```bash
git add -A examples/demo-app/
git commit -m "fix(demo): issues found during browser preset verification"
```

---

## Task Order & Dependencies

```
Task 1 (scaffold) ──────────────────────────────────────────────────►
Task 2 (healthcare) ─┐
Task 3 (trading) ────┤── can run in parallel after Task 1
Task 4 (devops) ─────┘
Task 5 (story registry) ── after Tasks 2-4
Task 6 (tools) ── after Tasks 2-4 (needs tool defs from stories)
Task 7 (identity) ── after Task 5
Task 8 (enforcement) ── after Task 6
Task 9 (agents.py) ── after Task 1 (standalone)
Task 10 (pipeline) ── after Tasks 7, 8, 9 (uses all of them)
Task 11 (app.py) ── after Task 10
Task 12 (frontend) ── after Task 11 (needs routes to exist)
Task 13 (partials) ── after Task 12
Task 14 (wiring) ── after Tasks 11, 12, 13
Task 15 (integration test) ── after Task 14
Task 16 (manual verification) ── after Task 15
```

**Parallelizable:** Tasks 2, 3, 4 can run simultaneously. Task 9 can run in parallel with 5-8.

**Critical path:** 1 → 2/3/4 → 5 → 6 → 8 → 10 → 11 → 12 → 14 → 15 → 16
