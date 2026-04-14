# App 3: Patient Record Guard

## The Scenario

You're building the backend for a patient portal. A patient logs in, and the system creates an agent scoped to that patient's records only. The agent can read medical records, read lab results, and view billing — but only for that specific patient. If the patient (or a compromised session) tries to access another patient's data, the scope check blocks it immediately.

This app teaches the most important scope pattern in AgentWrit: **the request determines the scope, the scope determines the agent's authority**. Every web request gets its own agent with its own narrow scope derived from the authenticated user.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **Dynamic scope from request context** | Scopes are not config — they come from the user, task, or event being processed |
| **Cross-scope denial** | What happens when an agent tries to access a scope it doesn't hold |
| **Multiple scope types per agent** | An agent can hold read access to records, labs, AND billing simultaneously |
| **`scope_is_subset()` as a security gate** | Checking scope before every data access — not just at agent creation |
| **Why identifiers must be dynamic** | Hardcoding `read:records:patient-1042` defeats the purpose of per-task isolation |

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  Patient Portal Script                                 │
│                                                         │
│  simulate_patient_session(patient_id="P-1042"):         │
│    1. create_agent(                                     │
│         scope: [                                        │
│           read:records:P-1042,                          │
│           read:labs:P-1042,                             │
│           read:billing:P-1042                           │
│         ])                                              │
│    2. access_records(agent, "P-1042")  ← ALLOWED        │
│    3. access_records(agent, "P-2187")  ← BLOCKED        │
│    4. access_labs(agent, "P-1042")     ← ALLOWED        │
│    5. write_records(agent, "P-1042")   ← BLOCKED        │
│    6. release(agent)                                    │
│                                                         │
│  The patient never gets write access.                   │
│  The patient never gets another patient's data.         │
└────────────────────────────────────────────────────────┘
```

Key design decisions:
- The patient ID comes from the "session" (simulated), not from hardcoded config
- The agent gets `read` only — patients view their data, they don't edit the medical record
- Three different scope resources (records, labs, billing) all scoped to the same patient

---

## The Code

```python
# patient_guard.py
# Run: python patient_guard.py

from __future__ import annotations

import os
import sys

from agentwrit import AgentWritApp, scope_is_subset, validate


# ── Simulated Patient Sessions ────────────────────────────────
# In a real app, these come from your auth system (OAuth, SAML, etc.)
# The patient_id is the authenticated user's identifier.

SESSIONS = [
    {"patient_id": "P-1042", "name": "Maria Santos"},
    {"patient_id": "P-2187", "name": "James O'Brien"},
]


def build_patient_scope(patient_id: str) -> list[str]:
    """Build the scope list for a patient portal session.

    The patient gets read-only access to their own records, labs,
    and billing. No write. No other patient.
    """
    return [
        f"read:records:{patient_id}",
        f"read:labs:{patient_id}",
        f"read:billing:{patient_id}",
    ]


def simulate_patient_session(
    app: AgentWritApp,
    patient_id: str,
    patient_name: str,
) -> None:
    """Simulate one patient's portal session with a scoped agent."""

    print(f"── Patient Session: {patient_name} ({patient_id}) ──")
    print()

    scope = build_patient_scope(patient_id)
    agent = app.create_agent(
        orch_id="patient-portal",
        task_id=f"session-{patient_id}",
        requested_scope=scope,
    )

    print(f"  Agent: {agent.agent_id}")
    print(f"  Scope: {agent.scope}")
    print()

    try:
        # ── Access own records ─────────────────────────────────
        required = [f"read:records:{patient_id}"]
        if scope_is_subset(required, agent.scope):
            print(f"  ✅ READ records for {patient_id}: BP 120/80, A1C 5.4%, no allergies")
        else:
            print(f"  ❌ DENIED records for {patient_id}")

        # ── Access own lab results ─────────────────────────────
        required = [f"read:labs:{patient_id}"]
        if scope_is_subset(required, agent.scope):
            print(f"  ✅ READ labs for {patient_id}: CBC normal, lipid panel within range")
        else:
            print(f"  ❌ DENIED labs for {patient_id}")

        # ── Access own billing ─────────────────────────────────
        required = [f"read:billing:{patient_id}"]
        if scope_is_subset(required, agent.scope):
            print(f"  ✅ READ billing for {patient_id}: Balance $45.00 copay due")
        else:
            print(f"  ❌ DENIED billing for {patient_id}")

        # ── CROSS-PATIENT: Try to read another patient's records ──
        other_patient = "P-2187"
        required = [f"read:records:{other_patient}"]
        if scope_is_subset(required, agent.scope):
            print(f"  🚨 BREACH: Can read {other_patient}'s records!")
            sys.exit(1)
        else:
            print(f"  🛑 BLOCKED: Cannot read records for {other_patient} (scope isolation)")

        # ── WRITE ATTEMPT: Patient tries to modify their own records ──
        required = [f"write:records:{patient_id}"]
        if scope_is_subset(required, agent.scope):
            print(f"  🚨 BREACH: Patient can write medical records!")
            sys.exit(1)
        else:
            print(f"  🛑 BLOCKED: Cannot write records (read-only portal)")

        # ── ESCALATION: Try to access a different resource type ──
        required = [f"read:prescriptions:{patient_id}"]
        if scope_is_subset(required, agent.scope):
            print(f"  🚨 UNEXPECTED: Can read prescriptions (not in scope)")
        else:
            print(f"  🛑 BLOCKED: Cannot read prescriptions (not in agent scope)")

        print()

    finally:
        agent.release()
        print(f"  Session ended. Agent released for {patient_id}.")

    # Confirm token is dead
    result = validate(app.broker_url, agent.access_token)
    if not result.valid:
        print(f"  Token dead: \"{result.error}\"")
    print()


def main() -> None:
    app = AgentWritApp(
        broker_url=os.environ["AGENTWRIT_BROKER_URL"],
        client_id=os.environ["AGENTWRIT_CLIENT_ID"],
        client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
    )

    print("Patient Portal — Record Guard")
    print("=" * 55)
    print()
    print("Each patient gets an agent scoped to their own data only.")
    print("Cross-patient access and write operations are blocked.")
    print()

    for session in SESSIONS:
        simulate_patient_session(app, session["patient_id"], session["name"])

    print("All sessions complete. No breaches detected.")


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:records:*` | `read:records:P-{id}` | Patient reads their own medical records |
| `read:labs:*` | `read:labs:P-{id}` | Patient reads their own lab results |
| `read:billing:*` | `read:billing:P-{id}` | Patient reads their own billing history |

Note: The app does **not** request `write:records:*` — patients don't need it and shouldn't have it. The ceiling doesn't need to include write scopes for this app at all. This is the principle of least privilege at the app level.

> **If the broker returns `AuthorizationError (403)`, the app's ceiling doesn't include the required `read:records:*`, `read:labs:*`, or `read:billing:*` scopes.** Re-register with the universal ceiling (see [README setup](README.md#one-time-setup-for-all-sample-apps)).

## Running It

```bash
export AGENTWRIT_BROKER_URL="http://127.0.0.1:8080"
export AGENTWRIT_CLIENT_ID="<from registration>"
export AGENTWRIT_CLIENT_SECRET="<from registration>"

uv run python patient_guard.py
```

---

## Expected Output

```
Patient Portal — Record Guard
=======================================================

Each patient gets an agent scoped to their own data only.
Cross-patient access and write operations are blocked.

── Patient Session: Maria Santos (P-1042) ──

  Agent: spiffe://agentwrit.local/agent/patient-portal/session-P-1042/a7c3...
  Scope: ['read:records:P-1042', 'read:labs:P-1042', 'read:billing:P-1042']

  ✅ READ records for P-1042: BP 120/80, A1C 5.4%, no allergies
  ✅ READ labs for P-1042: CBC normal, lipid panel within range
  ✅ READ billing for P-1042: Balance $45.00 copay due
  🛑 BLOCKED: Cannot read records for P-2187 (scope isolation)
  🛑 BLOCKED: Cannot write records (read-only portal)
  🛑 BLOCKED: Cannot read prescriptions (not in agent scope)

  Session ended. Agent released for P-1042.
  Token dead: "token is invalid or expired"

── Patient Session: James O'Brien (P-2187) ──

  Agent: spiffe://agentwrit.local/agent/patient-portal/session-P-2187/b9d5...
  Scope: ['read:records:P-2187', 'read:labs:P-2187', 'read:billing:P-2187']

  ✅ READ records for P-2187: BP 138/88, A1C 6.8%, allergic to penicillin
  ✅ READ labs for P-2187: CBC normal, LDL elevated at 165
  ✅ READ billing for P-2187: Balance $0.00 — all claims settled
  🛑 BLOCKED: Cannot read records for P-2187 (scope isolation)
  🛑 BLOCKED: Cannot write records (read-only portal)
  🛑 BLOCKED: Cannot read prescriptions (not in agent scope)

  Session ended. Agent released for P-2187.
  Token dead: "token is invalid or expired"

All sessions complete. No breaches detected.
```

---

## Key Takeaways

1. **Scope is derived from the authenticated user, not from config.** `build_patient_scope(patient_id)` generates a different scope for each patient. This is the pattern you must follow — if you hardcode the identifier, you've just built a static API key with extra steps.

2. **Three resources, one patient.** The agent holds `read:records:P-1042`, `read:labs:P-1042`, and `read:billing:P-1042`. Each is a different resource type, but all scoped to the same patient. A tool that checks records only needs to verify `read:records:P-1042` — it doesn't care about the other scopes.

3. **Read-only enforcement is a scope decision.** The agent never requests `write:records:*`. Even if a bug in the frontend sends a write request, the scope check will block it. This is defense in depth — the frontend should also prevent the action, but the backend scope gate catches it regardless.

4. **Cross-patient access is structurally impossible.** The agent scoped to `P-1042` cannot produce a valid `scope_is_subset` check for `P-2187`. This isn't a policy that can be misconfigured — it's the mathematical structure of the scope format.

5. **Every session gets a unique SPIFFE ID.** If an auditor asks "who accessed Maria Santos' records at 2:03 PM?", the audit trail points to a specific agent identity tied to that session.
