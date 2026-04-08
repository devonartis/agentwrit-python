# FIX_NOW.md — Critical Design Flaw & Immediate Remediation

## 🚨 CRITICAL DESIGN FLAW: Scope Authority Mismatch

### **The Problem**
The current `v0.3.0` rewrite contains a high-severity architectural bug in the `AgentCreationOrchestrator`. 

In `src/agentauth/orchestrator.py`, the `Agent` object is instantiated using the `requested_scope` (the user's **intent**) rather than the `scope` actually granted by the Broker (the **truth**).

```python
# CURRENT BROKEN IMPLEMENTATION
return Agent(
    ...,
    scope=requested_scope, # <<------ ERROR: This is just what the user asked for.
    ...
)
```

### **Why this is "Terrible" (The Silent Failure)**
If a user requests a scope that exceeds their `launch_token` ceiling, the Broker will correctly attenuate the scope (e.g., User asks for `write:*`, Broker grants `read:*`). 

Because the SDK currently echoes the user's request back into the `Agent` object, the developer's code will believe they have `write` permissions:
1. `if "write:*" in agent.scope:` returns **TRUE** (based on the lie).
2. `agent.perform_action()` is called.
3. **The actual network call fails with a 403 Forbidden** because the underlying JWT only has `read`.

This creates a "Silent Failure" where the SDK's state is out of sync with the cryptographic reality, leading to massive developer frustration and untrustworthy code.

---

## 🛠 Immediate Fix Plan

### **1. Update Orchestrator Logic**
Modify `src/agentauth/orchestrator.py` to extract the scope from the Broker's registration response.

**Target Change:**
```python
# FROM:
scope=requested_scope,

# TO:
scope=reg_data.get("scope", []), # Use the Broker's truth
```

### **2. Verify Broker API Contract**
Ensure the Broker's `/v1/register` endpoint is documented to return the granted `scope` in the response body. (Refer to `broker/docs/api.md`).

---

## 📝 Full Technical Review (Summary of Findings)

**Reviewer Note:** This review was triggered by the identification of a major design flaw where the SDK modeled "Intent" instead of "Authority."

| Category | Status | Finding |
| :--- | :--- | :--- |
| **Architecture** | ⚠️ **CRITICAL** | `Agent` object uses `requested_scope` instead of Broker-granted scope. Breaks the "Source of Truth" principle. |
| **Security** | ⚠️ **HIGH** | SDK state can diverge from JWT claims, leading to incorrect permission checks in client code. |
| **Reliability** | ✅ **GOOD** | Lazy authentication and session management are correctly implemented. |
| **Type Safety** | ✅ **EXCELLENT** | Strict `mypy` compliance and strong typing throughout. |
| **Observability** | ✅ **GOOD** | Error handling uses `ProblemDetail` (RFC 7807) correctly. |

**Verdict:** The rewrite is architecturally sound in its *structure* (Orchestrator, Transport, App) but fundamentally broken in its *data integrity*. The fix is mandatory before any further development or testing.
