"""API routes — LLM-driven request processing with dynamic agent spawning.

The LLM decides which tools to call. AgentWrit agents are spawned
dynamically based on the tools the LLM selects. scope_is_subset gates
every tool call. The full execution trace is returned to the UI.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from openai import OpenAI

from agentwrit import (
    Agent,
    AgentWritApp,
    DelegatedToken,
    scope_is_subset,
    validate,
)
from agentwrit.errors import AgentWritError, AuthorizationError
from demo.config import DemoConfig
from demo.data.patients import get_patient, list_patients
from demo.pipeline.tools import TOOLS, execute_tool, scopes_for_tools

router = APIRouter(prefix="/api")

# Which tools belong to which agent category — used to dynamically
# determine which agent to spawn when the LLM picks a tool
TOOL_TO_CATEGORY: dict[str, str] = {
    "get_patient_records": "clinical",
    "write_clinical_notes": "clinical",
    "get_lab_results": "clinical",
    "check_drug_interactions": "prescription",
    "write_prescription": "prescription",
    "get_billing_history": "billing",
    "get_insurance_coverage": "billing",
    "generate_billing_codes": "billing",
    "file_insurance_claim": "billing",
}

SYSTEM_PROMPT = """You are a healthcare assistant at MedAssist AI. You help staff with patient data.

You have access to medical records, lab results, prescriptions, billing, and insurance tools.
Use them based on what the user asks for. Always include the patient_id in tool calls.

If a request involves multiple areas (e.g. records AND billing), call tools from each area.
If the user mentions another patient's ID, try to look up their data too.
Be thorough — call all relevant tools for the request."""


@dataclass
class TraceStep:
    """One step in the execution trace shown to the user."""

    step_type: str
    label: str
    detail: dict[str, Any] = field(default_factory=dict)
    status: str = "info"  # info, success, denied, error, warning

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_type": self.step_type,
            "label": self.label,
            "detail": self.detail,
            "status": self.status,
            "timestamp": time.time(),
        }


@router.post("/request")
async def process_request(request: Request) -> JSONResponse:
    """Process a user request using LLM tool-calling with dynamic agent spawning.

    Flow:
    1. User provides patient_id + free-form request text
    2. LLM receives ALL 9 tools and decides which to call
    3. For each tool the LLM calls, we dynamically spawn the right
       agent category (clinical/billing/prescription) if not already spawned
    4. scope_is_subset gates every tool call — denials shown in trace
    5. Full execution trace returned: agent creation, tool calls, scope
       checks, delegation, cleanup
    """
    body = await request.json()
    patient_id: str = body.get("patient_id", "").strip()
    request_text: str = body.get("request", "").strip()

    cfg = DemoConfig.from_env()
    trace: list[TraceStep] = []
    agents: dict[str, Agent] = {}  # category -> Agent
    aa_app: AgentWritApp | None = None

    try:
        # ── Validate input ─────────────────────────────────────
        if not patient_id:
            trace.append(TraceStep("validation", "No patient ID provided",
                                   {"message": "Enter a patient ID (dropdown or type one)"}, "error"))
            return JSONResponse({"trace": [s.to_dict() for s in trace]})

        if not request_text:
            trace.append(TraceStep("validation", "No request provided",
                                   {"message": "Describe what you need"}, "error"))
            return JSONResponse({"trace": [s.to_dict() for s in trace]})

        # ── Patient lookup ─────────────────────────────────────
        patient = get_patient(patient_id)
        if patient:
            trace.append(TraceStep("patient_lookup",
                                   f"Patient found: {patient['name']} ({patient_id})",
                                   {"patient_id": patient_id, "name": patient["name"],
                                    "dob": patient["dob"], "found": True}, "success"))
        else:
            trace.append(TraceStep("patient_lookup",
                                   f"Patient {patient_id} NOT FOUND",
                                   {"patient_id": patient_id, "found": False,
                                    "known_patients": [p["patient_id"] for p in list_patients()]},
                                   "warning"))

        # ── Connect to broker ──────────────────────────────────
        aa_app = AgentWritApp(
            broker_url=cfg.broker_url,
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
        )

        health = aa_app.health()
        trace.append(TraceStep("broker_health",
                               f"Broker: {health.status} v{health.version}",
                               {"status": health.status, "version": health.version,
                                "uptime": health.uptime, "db_connected": health.db_connected},
                               "success"))

        # ── LLM tool-calling loop ──────────────────────────────
        llm_client = OpenAI(
            base_url=cfg.llm_base_url,
            api_key=cfg.llm_api_key,
        )

        all_tool_schemas = [t.openai_schema() for t in TOOLS.values()]

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Patient ID: {patient_id}\n\nRequest: {request_text}"},
        ]

        trace.append(TraceStep("llm_start",
                               f"LLM processing request (model: {cfg.llm_model})",
                               {"model": cfg.llm_model, "base_url": cfg.llm_base_url,
                                "tools_available": list(TOOLS.keys()),
                                "request": request_text}, "info"))

        clinical_agent: Agent | None = None
        delegated_rx_token: DelegatedToken | None = None

        for iteration in range(10):
            response = llm_client.chat.completions.create(
                model=cfg.llm_model,
                messages=messages,
                tools=all_tool_schemas,
                tool_choice="auto",
            )

            choice = response.choices[0]

            # LLM done — final text response
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                if choice.message.content:
                    trace.append(TraceStep("llm_response", "LLM final response",
                                           {"content": choice.message.content}, "info"))
                break

            messages.append(choice.message.model_dump())

            # Process each tool call the LLM made
            for tool_call in choice.message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                tool_def = TOOLS.get(fn_name)
                if not tool_def:
                    messages.append({"role": "tool", "tool_call_id": tool_call.id,
                                     "content": json.dumps({"error": f"Unknown tool: {fn_name}"})})
                    continue

                # What patient is this tool call for?
                tool_pid = fn_args.get("patient_id", patient_id)
                category = TOOL_TO_CATEGORY.get(fn_name, "clinical")

                # ── Dynamically spawn agent if needed ──────────
                if category not in agents:
                    cat_tools = [n for n, c in TOOL_TO_CATEGORY.items() if c == category]
                    agent_scopes = scopes_for_tools(cat_tools, patient_id)

                    # Clinical agent also gets write:prescriptions so it
                    # can delegate to the prescription agent
                    if category == "clinical":
                        agent_scopes.append(f"write:prescriptions:{patient_id}")

                    task_id = f"{category}-{patient_id}-{int(time.time())}"

                    try:
                        agent = aa_app.create_agent(
                            orch_id="medassist",
                            task_id=task_id,
                            requested_scope=agent_scopes,
                            max_ttl=300,
                        )
                        agents[category] = agent

                        if category == "clinical":
                            clinical_agent = agent

                        trace.append(TraceStep("agent_created",
                                               f"{category.upper()} agent spawned",
                                               {"agent_id": agent.agent_id,
                                                "spiffe_id": agent.agent_id,
                                                "scope": agent.scope,
                                                "tools": cat_tools,
                                                "task_id": agent.task_id,
                                                "orch_id": agent.orch_id,
                                                "expires_in": agent.expires_in,
                                                "token_preview": agent.access_token[:30] + "...",
                                                "category": category,
                                                "trigger": f"LLM called {fn_name}"},
                                               "success"))

                        # Validate token — show claims
                        val = validate(cfg.broker_url, agent.access_token)
                        if val.valid and val.claims:
                            trace.append(TraceStep("token_validated",
                                                   f"{category.upper()} token validated",
                                                   {"valid": True,
                                                    "sub": val.claims.sub,
                                                    "scope": val.claims.scope,
                                                    "jti": val.claims.jti,
                                                    "orch_id": val.claims.orch_id,
                                                    "task_id": val.claims.task_id,
                                                    "category": category}, "info"))

                    except AgentWritError as e:
                        trace.append(TraceStep("agent_error",
                                               f"Failed to create {category} agent: {e}",
                                               {"error": str(e), "category": category}, "error"))
                        messages.append({"role": "tool", "tool_call_id": tool_call.id,
                                         "content": json.dumps({"error": f"Agent creation failed: {e}"})})
                        continue

                # ── Handle delegation for prescription writes ──
                if fn_name == "write_prescription" and clinical_agent and category == "prescription":
                    rx_agent = agents.get("prescription")
                    if rx_agent and delegated_rx_token is None:
                        deleg_scope = [f"write:prescriptions:{patient_id}"]
                        try:
                            delegated_rx_token = clinical_agent.delegate(
                                delegate_to=rx_agent.agent_id,
                                scope=deleg_scope,
                            )
                            trace.append(TraceStep("delegation",
                                                   "Clinical delegated write:prescriptions to Rx agent",
                                                   {"delegator_id": clinical_agent.agent_id,
                                                    "delegator_scope": clinical_agent.scope,
                                                    "delegate_id": rx_agent.agent_id,
                                                    "delegated_scope": deleg_scope,
                                                    "token_preview": delegated_rx_token.access_token[:30] + "...",
                                                    "chain": [{"agent": r.agent, "scope": r.scope,
                                                               "delegated_at": r.delegated_at}
                                                              for r in delegated_rx_token.delegation_chain],
                                                    "expires_in": delegated_rx_token.expires_in},
                                                   "success"))
                        except AuthorizationError as e:
                            trace.append(TraceStep("delegation_denied",
                                                   "Delegation denied by broker",
                                                   {"error": str(e),
                                                    "delegator": clinical_agent.agent_id,
                                                    "delegate": rx_agent.agent_id,
                                                    "scope": deleg_scope}, "denied"))

                # ── Scope check ────────────────────────────────
                agent = agents[category]
                effective_scope = list(agent.scope)

                # Add delegated scope if this is the prescription agent
                if category == "prescription" and delegated_rx_token:
                    effective_scope.append(f"write:prescriptions:{patient_id}")

                required = tool_def.required_scope(tool_pid)
                authorized = scope_is_subset(required, effective_scope)

                if authorized:
                    output = execute_tool(fn_name, fn_args)
                    trace.append(TraceStep("tool_call",
                                           f"{fn_name} — AUTHORIZED",
                                           {"tool": fn_name,
                                            "patient_id": tool_pid,
                                            "args": fn_args,
                                            "authorized": True,
                                            "required_scope": required,
                                            "held_scope": effective_scope,
                                            "agent_id": agent.agent_id,
                                            "output": json.loads(output),
                                            "category": category}, "success"))
                    messages.append({"role": "tool", "tool_call_id": tool_call.id,
                                     "content": output})
                else:
                    denial = (f"ACCESS DENIED: '{fn_name}' requires {required} "
                              f"but {category} agent holds {effective_scope}")
                    trace.append(TraceStep("scope_denied",
                                           f"{fn_name} — ACCESS DENIED",
                                           {"tool": fn_name,
                                            "patient_id": tool_pid,
                                            "args": fn_args,
                                            "authorized": False,
                                            "required_scope": required,
                                            "held_scope": effective_scope,
                                            "agent_id": agent.agent_id,
                                            "reason": denial,
                                            "category": category}, "denied"))
                    messages.append({"role": "tool", "tool_call_id": tool_call.id,
                                     "content": denial})

        # ── Cleanup: release all agents ────────────────────────
        for category, agent in agents.items():
            token_before = agent.access_token

            # Renew first to demo lifecycle
            old_token = agent.access_token
            try:
                agent.renew()
                trace.append(TraceStep("token_renewed",
                                       f"{category.upper()} token renewed",
                                       {"agent_id": agent.agent_id,
                                        "old_preview": old_token[:30] + "...",
                                        "new_preview": agent.access_token[:30] + "...",
                                        "new_expires_in": agent.expires_in,
                                        "category": category}, "info"))

                # Confirm old token is dead
                old_val = validate(cfg.broker_url, old_token)
                trace.append(TraceStep("token_validated",
                                       f"Old {category} token confirmed dead",
                                       {"valid": old_val.valid, "error": old_val.error,
                                        "context": "old_token_after_renewal"},
                                       "success" if not old_val.valid else "warning"))
            except AgentWritError:
                pass

            # Release
            token_before = agent.access_token
            try:
                agent.release()
                trace.append(TraceStep("token_released",
                                       f"{category.upper()} agent released",
                                       {"agent_id": agent.agent_id,
                                        "spiffe_id": agent.agent_id,
                                        "task_id": agent.task_id,
                                        "category": category}, "info"))
            except AgentWritError as e:
                trace.append(TraceStep("release_error",
                                       f"Release failed: {e}",
                                       {"error": str(e), "agent_id": agent.agent_id}, "error"))

            # Confirm released token is dead
            dead = validate(cfg.broker_url, token_before)
            trace.append(TraceStep("post_release_validation",
                                   f"Token dead after release: {not dead.valid}",
                                   {"agent_id": agent.agent_id, "valid": dead.valid,
                                    "error": dead.error},
                                   "success" if not dead.valid else "warning"))

        # ── Summary ────────────────────────────────────────────
        trace.append(TraceStep("complete",
                               "Request complete — all agents released, tokens dead",
                               {"patient_id": patient_id,
                                "agents_spawned": list(agents.keys()),
                                "agents_count": len(agents)}, "success"))

    except Exception as e:
        trace.append(TraceStep("error", f"Error: {type(e).__name__}: {e}",
                               {"error": str(e), "type": type(e).__name__}, "error"))
    finally:
        if aa_app:
            aa_app.close()

    return JSONResponse({"trace": [s.to_dict() for s in trace]})


# ── Admin Revocation ───────────────────────────────────────────

@router.post("/revoke")
async def revoke_agent(
    level: str = Query(...),
    target: str = Query(...),
) -> dict[str, object]:
    """Admin revocation endpoint for the operator panel."""
    cfg = DemoConfig.from_env()

    auth_resp = httpx.post(
        f"{cfg.broker_url}/v1/admin/auth",
        json={"secret": cfg.admin_secret},
        timeout=10,
    )
    auth_resp.raise_for_status()
    admin_token = auth_resp.json()["access_token"]

    revoke_resp = httpx.post(
        f"{cfg.broker_url}/v1/revoke",
        json={"level": level, "target": target},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    return revoke_resp.json()


# ── Audit Events ───────────────────────────────────────────────

@router.get("/audit/events")
async def get_audit_events(
    limit: int = Query(50),
    event_type: str | None = Query(None),
    agent_id: str | None = Query(None),
) -> dict[str, object]:
    """Fetch audit events from the broker."""
    cfg = DemoConfig.from_env()

    auth_resp = httpx.post(
        f"{cfg.broker_url}/v1/admin/auth",
        json={"secret": cfg.admin_secret},
        timeout=10,
    )
    auth_resp.raise_for_status()
    admin_token = auth_resp.json()["access_token"]

    params: dict[str, str | int] = {"limit": limit}
    if event_type:
        params["event_type"] = event_type
    if agent_id:
        params["agent_id"] = agent_id

    events_resp = httpx.get(
        f"{cfg.broker_url}/v1/audit/events",
        params=params,
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    return events_resp.json()


# ── Info endpoints ─────────────────────────────────────────────

@router.get("/tools")
async def get_tools() -> dict[str, object]:
    """List all tools with their scope templates."""
    return {
        "tools": {
            name: {"name": t.name, "description": t.description,
                    "scope_template": t.scope_template}
            for name, t in TOOLS.items()
        },
    }


@router.get("/patients")
async def get_patients() -> dict[str, object]:
    """List known patients."""
    return {"patients": list_patients()}
