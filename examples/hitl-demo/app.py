"""AgentAuth SDK Demo -- Data Pipeline with HITL Approval.

Scenario: A data analysis agent needs to:
  1. Get read credentials (automatic -- no human needed)
  2. Read customer data and analyze it
  3. Request write credentials to save results (HITL -- human must approve)
  4. Human reviews what the agent wants to write and approves or denies
  5. If approved, agent writes results with the approved credential
  6. Agent finishes and revokes all its credentials

This exercises every SDK capability in a realistic workflow:
  - AgentAuthClient init (app auth)
  - get_token with read scope (immediate)
  - get_token with write scope (HITL gate)
  - HITLApprovalRequired exception handling
  - Approval flow with principal identity
  - Token validation (show claims)
  - Self-revocation (credential cleanup)

Setup:
    cd examples/hitl-demo
    export AGENTAUTH_BROKER_URL=http://127.0.0.1:8080
    export AGENTAUTH_CLIENT_ID=<client_id>
    export AGENTAUTH_CLIENT_SECRET=<client_secret>
    uv run uvicorn examples.hitl-demo.app:app --port 5001 --reload
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests as http_requests
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agentauth import AgentAuthClient, HITLApprovalRequired, ScopeCeilingError
from agentauth.errors import AgentAuthError

app = FastAPI(title="AgentAuth SDK Demo")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

BROKER_URL: str = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
CLIENT_ID: str | None = os.environ.get("AGENTAUTH_CLIENT_ID")
CLIENT_SECRET: str | None = os.environ.get("AGENTAUTH_CLIENT_SECRET")

sdk_client: AgentAuthClient | None = None
init_error: str | None = None

if CLIENT_ID and CLIENT_SECRET:
    try:
        sdk_client = AgentAuthClient(
            broker_url=BROKER_URL, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        )
    except AgentAuthError as exc:
        init_error = str(exc)
else:
    init_error = "Set AGENTAUTH_CLIENT_ID and AGENTAUTH_CLIENT_SECRET"

# Simulated data the agent "reads" and "writes"
SAMPLE_RECORDS: list[dict[str, str]] = [
    {"id": "cust-001", "name": "Acme Corp", "revenue": "$2.4M", "risk": "low"},
    {"id": "cust-002", "name": "TechStart Inc", "revenue": "$890K", "risk": "medium"},
    {"id": "cust-003", "name": "Global Widgets", "revenue": "$12.1M", "risk": "low"},
]

# Track pipeline state per session (simple in-memory)
pipeline_state: dict[str, dict[str, object]] = {}


def _error_html(msg: str) -> str:
    return f'<div class="result-panel result-error"><strong>Error:</strong> {msg}</div>'


def _validate_token(token: str) -> dict[str, object]:
    resp = http_requests.post(
        f"{BROKER_URL}/v1/token/validate", json={"token": token}, timeout=10
    )
    return resp.json()


def _get_admin_token() -> str | None:
    secret: str | None = os.environ.get("AGENTAUTH_ADMIN_SECRET")
    if not secret:
        return None
    resp = http_requests.post(
        f"{BROKER_URL}/v1/admin/auth", json={"secret": secret}, timeout=10
    )
    if resp.status_code == 200:
        return resp.json()["access_token"]
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {
        "broker_url": BROKER_URL,
        "client_id": CLIENT_ID or "(not set)",
        "sdk_ready": sdk_client is not None,
        "init_error": init_error,
    })


@app.post("/htmx/get-token", response_class=HTMLResponse)
def htmx_get_token(
    request: Request,
    agent_name: str = Form(...),
    scope: str = Form(...),
    task_id: str = Form(""),
    orch_id: str = Form(""),
    approval_token: str = Form(""),
) -> HTMLResponse:
    """Get a token — the core SDK call. Scope determines what happens."""
    if sdk_client is None:
        return HTMLResponse(_error_html(init_error or "SDK not ready"))

    scope_list: list[str] = [s.strip() for s in scope.split(",")]
    try:
        token: str = sdk_client.get_token(
            agent_name, scope_list,
            task_id=task_id or None, orch_id=orch_id or None,
            approval_token=approval_token if approval_token else None,
        )
        claims: dict[str, object] = _validate_token(token)
        return templates.TemplateResponse(request, "partials/token_result.html", {
            "token": token,
            "claims": claims.get("claims", {}),
            "scope": scope_list,
        })
    except HITLApprovalRequired as exc:
        return templates.TemplateResponse(request, "partials/hitl_approval.html", {
            "approval_id": exc.approval_id,
            "expires_at": exc.expires_at,
            "agent_name": agent_name,
            "scope": scope,
            "task_id": task_id,
            "orch_id": orch_id,
        })
    except ScopeCeilingError as exc:
        return templates.TemplateResponse(request, "partials/scope_error.html", {
            "error": str(exc),
            "scope": scope_list,
        })
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/approve", response_class=HTMLResponse)
def htmx_approve(
    request: Request,
    approval_id: str = Form(...),
    principal: str = Form(...),
    agent_name: str = Form(...),
    scope: str = Form(...),
    task_id: str = Form(""),
    orch_id: str = Form(""),
) -> HTMLResponse:
    """Approve HITL request and auto-retry get_token."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))

    app_token: str = sdk_client._ensure_app_token()  # noqa: SLF001
    resp = http_requests.post(
        f"{BROKER_URL}/v1/app/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {app_token}"},
        json={"principal": principal},
        timeout=10,
    )
    if resp.status_code != 200:
        return HTMLResponse(_error_html(f"Approval failed: {resp.text}"))

    approval_token: str = resp.json()["approval_token"]
    scope_list: list[str] = [s.strip() for s in scope.split(",")]
    try:
        token: str = sdk_client.get_token(
            agent_name, scope_list,
            task_id=task_id or None, orch_id=orch_id or None,
            approval_token=approval_token,
        )
        claims: dict[str, object] = _validate_token(token)
        return templates.TemplateResponse(request, "partials/token_result.html", {
            "token": token,
            "claims": claims.get("claims", {}),
            "scope": scope_list,
            "approved_by": principal,
        })
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/deny", response_class=HTMLResponse)
def htmx_deny(
    request: Request,
    approval_id: str = Form(...),
) -> HTMLResponse:
    """Deny a HITL request."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))
    app_token: str = sdk_client._ensure_app_token()  # noqa: SLF001
    http_requests.post(
        f"{BROKER_URL}/v1/app/approvals/{approval_id}/deny",
        headers={"Authorization": f"Bearer {app_token}"},
        json={"reason": "Denied by demo user"},
        timeout=10,
    )
    return HTMLResponse(
        '<div class="result-panel result-denied">'
        '<strong>Denied.</strong> No credential issued. The broker audit trail records this denial.'
        '</div>'
    )


@app.post("/htmx/delegate", response_class=HTMLResponse)
def htmx_delegate(
    request: Request,
    delegator_token: str = Form(...),
    delegate_agent: str = Form(...),
    delegate_scope: str = Form(...),
) -> HTMLResponse:
    """Delegate scope from one agent to another (C7)."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))

    # First register the delegate agent so it has a SPIFFE ID
    try:
        delegate_token: str = sdk_client.get_token(
            delegate_agent, ["read:data:logs"], task_id="delegation"
        )
        delegate_claims: dict[str, object] = _validate_token(delegate_token)
        delegate_sub: str = str(delegate_claims.get("claims", {}).get("sub", ""))  # type: ignore[union-attr]

        scope_list: list[str] = [s.strip() for s in delegate_scope.split(",")]
        delegated: str = sdk_client.delegate(
            token=delegator_token.strip(),
            to_agent_id=delegate_sub,
            scope=scope_list,
            ttl=120,
        )
        delegated_claims: dict[str, object] = _validate_token(delegated)
        return templates.TemplateResponse(request, "partials/delegate_result.html", {
            "delegated_token": delegated,
            "delegated_claims": delegated_claims.get("claims", {}),
            "delegate_agent": delegate_agent,
            "delegate_scope": scope_list,
            "delegate_sub": delegate_sub,
        })
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/validate", response_class=HTMLResponse)
def htmx_validate(request: Request, token: str = Form(...)) -> HTMLResponse:
    """Validate a token (C3 zero-trust)."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))
    try:
        result: dict[str, object] = sdk_client.validate_token(token.strip())
        return templates.TemplateResponse(request, "partials/validate_result.html", {"result": result})
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/revoke", response_class=HTMLResponse)
def htmx_revoke(request: Request, token: str = Form(...)) -> HTMLResponse:
    """Revoke a token (C4)."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))
    try:
        sdk_client.revoke_token(token.strip())
        return HTMLResponse(
            '<div class="result-panel result-ok">'
            '<strong>Revoked.</strong> Token JTI marked invalid. '
            'Click "Validate After Revoke" to confirm the broker now rejects it. '
            '<span class="badge badge-c4" style="margin-left:4px;">C4 Revocation</span>'
            '</div>'
        )
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/audit", response_class=HTMLResponse)
def htmx_audit(request: Request) -> HTMLResponse:
    """Show recent audit events (C5)."""
    admin_token: str | None = _get_admin_token()
    if not admin_token:
        return HTMLResponse(_error_html("Set AGENTAUTH_ADMIN_SECRET to view audit trail"))

    resp = http_requests.get(
        f"{BROKER_URL}/v1/audit/events",
        headers={"Authorization": f"Bearer {admin_token}"},
        params={"limit": "15"},
        timeout=10,
    )
    if resp.status_code != 200:
        return HTMLResponse(_error_html(f"Audit query failed: {resp.text}"))

    events: list[dict[str, object]] = resp.json().get("events", [])
    return templates.TemplateResponse(request, "partials/audit_trail.html", {"events": events})


# Remove old step-based endpoints below this line
@app.post("/htmx/step1-read-creds", response_class=HTMLResponse)
def step1_get_read_credentials(request: Request, task_name: str = Form("quarterly-analysis")) -> HTMLResponse:
    """Step 1: Agent requests read:data:* credentials (automatic, no approval)."""
    if sdk_client is None:
        return HTMLResponse(_error_html(init_error or "SDK not ready"))
    try:
        read_token: str = sdk_client.get_token(
            f"{task_name}-reader", ["read:data:*"], task_id=task_name, orch_id="demo-pipeline"
        )
        claims: dict[str, object] = _validate_token(read_token)
        pipeline_state["current"] = {"read_token": read_token, "task_name": task_name}
        return templates.TemplateResponse(request, "partials/step1_result.html", {
            "token": read_token,
            "claims": claims.get("claims", {}),
            "task_name": task_name,
        })
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/step2-read-data", response_class=HTMLResponse)
def step2_read_data(request: Request) -> HTMLResponse:
    """Step 2: Agent uses read credentials to access data."""
    state: dict[str, object] | None = pipeline_state.get("current")
    if not state or not state.get("read_token"):
        return HTMLResponse(_error_html("No read token. Run Step 1 first."))
    # Simulated data read (in a real app, the agent would call a data API with the JWT)
    return templates.TemplateResponse(request, "partials/step2_result.html", {
        "records": SAMPLE_RECORDS,
        "analysis": "3 customers analyzed. 1 medium-risk account (TechStart Inc) flagged for review.",
    })


@app.post("/htmx/step3-write-creds", response_class=HTMLResponse)
def step3_request_write_credentials(request: Request) -> HTMLResponse:
    """Step 3: Agent requests write:data:* credentials (HITL gate triggers)."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))
    state: dict[str, object] | None = pipeline_state.get("current")
    task_name: str = str(state.get("task_name", "analysis")) if state else "analysis"
    try:
        write_token: str = sdk_client.get_token(
            f"{task_name}-writer", ["write:data:records"], task_id=task_name, orch_id="demo-pipeline"
        )
        # If we get here, write scope was NOT HITL-gated (shouldn't happen with our test app)
        pipeline_state["current"]["write_token"] = write_token  # type: ignore[index]
        return templates.TemplateResponse(request, "partials/step3_token.html", {"token": write_token})
    except HITLApprovalRequired as exc:
        pipeline_state["current"]["approval_id"] = exc.approval_id  # type: ignore[index]
        return templates.TemplateResponse(request, "partials/step3_hitl.html", {
            "approval_id": exc.approval_id,
            "expires_at": exc.expires_at,
            "task_name": task_name,
            "analysis": "TechStart Inc flagged as medium-risk. Agent wants to write risk assessment to customer record.",
        })
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/step4-approve", response_class=HTMLResponse)
def step4_approve(
    request: Request,
    approval_id: str = Form(...),
    principal: str = Form(...),
    task_name: str = Form("analysis"),
) -> HTMLResponse:
    """Step 4: Human approves the write request."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))

    app_token: str = sdk_client._ensure_app_token()  # noqa: SLF001
    resp = http_requests.post(
        f"{BROKER_URL}/v1/app/approvals/{approval_id}/approve",
        headers={"Authorization": f"Bearer {app_token}"},
        json={"principal": principal},
        timeout=10,
    )
    if resp.status_code != 200:
        return HTMLResponse(_error_html(f"Approval failed: {resp.text}"))

    approval_token: str = resp.json()["approval_token"]

    try:
        write_token: str = sdk_client.get_token(
            f"{task_name}-writer", ["write:data:records"],
            task_id=task_name, orch_id="demo-pipeline",
            approval_token=approval_token,
        )
        claims: dict[str, object] = _validate_token(write_token)
        pipeline_state["current"]["write_token"] = write_token  # type: ignore[index]
        return templates.TemplateResponse(request, "partials/step4_result.html", {
            "token": write_token,
            "claims": claims.get("claims", {}),
            "principal": principal,
        })
    except AgentAuthError as exc:
        return HTMLResponse(_error_html(str(exc)))


@app.post("/htmx/step4-deny", response_class=HTMLResponse)
def step4_deny(
    request: Request,
    approval_id: str = Form(...),
    reason: str = Form("Risk assessment not approved"),
) -> HTMLResponse:
    """Step 4 (alt): Human denies the write request."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))
    app_token: str = sdk_client._ensure_app_token()  # noqa: SLF001
    http_requests.post(
        f"{BROKER_URL}/v1/app/approvals/{approval_id}/deny",
        headers={"Authorization": f"Bearer {app_token}"},
        json={"reason": reason},
        timeout=10,
    )
    return HTMLResponse(
        '<div class="result-panel result-denied">'
        '<strong>Denied.</strong> The agent cannot write results. '
        'The read credential can still be revoked in Step 5.</div>'
    )


@app.post("/htmx/step5-cleanup", response_class=HTMLResponse)
def step5_cleanup(request: Request) -> HTMLResponse:
    """Step 5: Agent finishes and revokes all credentials."""
    if sdk_client is None:
        return HTMLResponse(_error_html("SDK not ready"))
    state: dict[str, object] | None = pipeline_state.get("current")
    if not state:
        return HTMLResponse(_error_html("No pipeline state. Start from Step 1."))

    revoked: list[str] = []
    for key in ("read_token", "write_token"):
        token: object = state.get(key)
        if token and isinstance(token, str):
            try:
                sdk_client.revoke_token(token)
                revoked.append(key.replace("_", " "))
            except AgentAuthError:
                pass  # already revoked or expired

    # Verify revocation
    verified: list[dict[str, object]] = []
    for key in ("read_token", "write_token"):
        token = state.get(key)
        if token and isinstance(token, str):
            result: dict[str, object] = _validate_token(str(token))
            verified.append({"name": key, "valid": result.get("valid", False)})

    pipeline_state.pop("current", None)
    return templates.TemplateResponse(request, "partials/step5_result.html", {
        "revoked": revoked,
        "verified": verified,
    })
