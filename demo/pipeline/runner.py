"""Encounter pipeline — orchestrates agents through a patient encounter.

Creates agents with granular per-patient scopes derived from their tools,
runs LLM tool-use loops with scope checks on every call, and yields
SSE events that the UI streams in real-time.

Key demo moments surfaced by this runner:
- Agent SPIFFE IDs shown at creation (identity)
- Scope badges per agent (least privilege)
- scope_is_subset() check before every tool call (enforcement)
- Billing agent denied read:records (isolation)
- Clinical → Prescription delegation (authority narrowing)
- Token renewal mid-encounter (lifecycle)
- Release + validate proving tokens are dead (cleanup)
- Cross-patient denial when scenario triggers it
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import OpenAI

from agentwrit import (
    Agent,
    AgentWritApp,
    DelegatedToken,
    scope_is_subset,
    validate,
)
from agentwrit.errors import AgentWritError, AuthorizationError
from demo.pipeline.agents import billing, clinical, prescription
from demo.pipeline.tools import (
    TOOLS,
    execute_tool,
    get_tools_for_role,
    scopes_for_tools,
)


@dataclass
class PipelineEvent:
    """A single event emitted by the pipeline for SSE streaming."""

    event_type: str  # agent_created, tool_call, scope_denied, delegation, ...
    agent_role: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        payload = {
            "event_type": self.event_type,
            "agent_role": self.agent_role,
            "timestamp": self.timestamp,
            **self.data,
        }
        return f"data: {json.dumps(payload)}\n\n"


@dataclass
class ScenarioConfig:
    """Controls what the pipeline does for different demo scenarios."""

    patient_id: str
    scenario: str = "happy_path"
    cross_patient_id: str | None = None  # for cross-patient demo
    short_ttl: int | None = None  # for token expiry demo
    trigger_revoke: bool = False  # for emergency revoke demo


def _run_llm_tool_loop(
    openai_client: OpenAI,
    system_prompt: str,
    user_message: str,
    tool_schemas: list[dict[str, Any]],
    agent_scope: list[str],
    patient_id: str,
    agent_role: str,
) -> list[PipelineEvent]:
    """Run an OpenAI tool-use loop. Returns events for each tool call."""
    events: list[PipelineEvent] = []

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for _iteration in range(8):
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tool_schemas if tool_schemas else None,
            tool_choice="auto" if tool_schemas else None,
        )

        choice = response.choices[0]

        if choice.finish_reason == "stop" or not choice.message.tool_calls:
            if choice.message.content:
                events.append(PipelineEvent(
                    event_type="llm_response",
                    agent_role=agent_role,
                    data={"content": choice.message.content},
                ))
            break

        messages.append(choice.message.model_dump())

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            tool_def = TOOLS.get(fn_name)
            if not tool_def:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps({"error": f"Unknown tool: {fn_name}"}),
                })
                continue

            tool_patient_id = fn_args.get("patient_id", patient_id)
            required = tool_def.required_scope(tool_patient_id)
            authorized = scope_is_subset(required, agent_scope)

            if authorized:
                output = execute_tool(fn_name, fn_args)
                events.append(PipelineEvent(
                    event_type="tool_call",
                    agent_role=agent_role,
                    data={
                        "tool": fn_name,
                        "patient_id": tool_patient_id,
                        "authorized": True,
                        "required_scope": required,
                        "held_scope": agent_scope,
                        "output_preview": output[:200],
                    },
                ))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": output,
                })
            else:
                denial_msg = (
                    f"ACCESS DENIED: Tool '{fn_name}' requires scope {required} "
                    f"but this agent only holds {agent_scope}. "
                    f"This agent is not authorized to access this data."
                )
                events.append(PipelineEvent(
                    event_type="scope_denied",
                    agent_role=agent_role,
                    data={
                        "tool": fn_name,
                        "patient_id": tool_patient_id,
                        "authorized": False,
                        "required_scope": required,
                        "held_scope": agent_scope,
                        "reason": denial_msg,
                    },
                ))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": denial_msg,
                })

    return events


def run_encounter(
    app: AgentWritApp,
    config: ScenarioConfig,
    openai_api_key: str,
    admin_secret: str,
) -> list[PipelineEvent]:
    """Run the full encounter pipeline. Returns all events in order.

    For SSE streaming, the route handler iterates over these events
    and yields them to the client.
    """
    events: list[PipelineEvent] = []
    pid = config.patient_id
    openai_client = OpenAI(api_key=openai_api_key)
    agents_created: list[Agent] = []

    # ── Health Check ───────────────────────────────────────────
    health = app.health()
    events.append(PipelineEvent(
        event_type="health_check",
        agent_role="system",
        data={
            "status": health.status,
            "version": health.version,
            "uptime": health.uptime,
            "db_connected": health.db_connected,
            "audit_events_count": health.audit_events_count,
        },
    ))

    # ── Phase 1: Clinical Review Agent ─────────────────────────
    # The clinical agent needs its own tool scopes PLUS write:prescriptions
    # so it can delegate prescription authority to the Rx agent later.
    # This is the key demo: the clinical agent holds the authority but
    # passes only the narrow slice to the prescription sub-agent.
    clinical_tool_names = ["get_patient_records", "write_clinical_notes", "get_lab_results"]
    clinical_scopes = scopes_for_tools(clinical_tool_names, pid)
    clinical_scopes.append(f"write:prescriptions:{pid}")

    ttl = config.short_ttl or 300

    clinical_agent = app.create_agent(
        orch_id="medassist",
        task_id=f"encounter-{pid}",
        requested_scope=clinical_scopes,
        max_ttl=ttl,
    )
    agents_created.append(clinical_agent)

    events.append(PipelineEvent(
        event_type="agent_created",
        agent_role="clinical",
        data={
            "agent_id": clinical_agent.agent_id,
            "spiffe_id": clinical_agent.agent_id,
            "scope": clinical_agent.scope,
            "tools": clinical_tool_names,
            "scopes_from_tools": clinical_scopes,
            "expires_in": clinical_agent.expires_in,
            "access_token_preview": clinical_agent.access_token[:20] + "...",
            "task_id": clinical_agent.task_id,
            "orch_id": clinical_agent.orch_id,
        },
    ))

    # Validate the clinical agent's token to show claims
    clinical_validation = validate(app.broker_url, clinical_agent.access_token)
    if clinical_validation.valid and clinical_validation.claims:
        events.append(PipelineEvent(
            event_type="token_validated",
            agent_role="clinical",
            data={
                "valid": True,
                "claims": {
                    "iss": clinical_validation.claims.iss,
                    "sub": clinical_validation.claims.sub,
                    "scope": clinical_validation.claims.scope,
                    "orch_id": clinical_validation.claims.orch_id,
                    "task_id": clinical_validation.claims.task_id,
                    "jti": clinical_validation.claims.jti,
                    "exp": clinical_validation.claims.exp,
                    "iat": clinical_validation.claims.iat,
                },
            },
        ))

    from demo.data.patients import get_patient
    patient = get_patient(pid)
    patient_name = patient["name"] if patient else pid

    user_msg = (
        f"Please review patient {patient_name} (ID: {pid}). "
        f"Check their medical records and lab results, then write "
        f"clinical notes for today's encounter."
    )

    # Cross-patient scenario: tell the LLM to also try another patient
    if config.scenario == "cross_patient" and config.cross_patient_id:
        user_msg += (
            f"\n\nAlso, please check the records for patient "
            f"{config.cross_patient_id} — they are a family member "
            f"and the patient wants to know their status."
        )

    clinical_tools = get_tools_for_role("clinical")
    tool_schemas = [t.openai_schema() for t in clinical_tools]

    llm_events = _run_llm_tool_loop(
        openai_client=openai_client,
        system_prompt=clinical.SYSTEM_PROMPT,
        user_message=user_msg,
        tool_schemas=tool_schemas,
        agent_scope=clinical_agent.scope,
        patient_id=pid,
        agent_role="clinical",
    )
    events.extend(llm_events)

    # Token renewal demo — show the agent renewing mid-encounter
    old_token = clinical_agent.access_token
    clinical_agent.renew()
    events.append(PipelineEvent(
        event_type="token_renewed",
        agent_role="clinical",
        data={
            "agent_id": clinical_agent.agent_id,
            "old_token_preview": old_token[:20] + "...",
            "new_token_preview": clinical_agent.access_token[:20] + "...",
            "new_expires_in": clinical_agent.expires_in,
        },
    ))

    # Verify old token is now dead
    old_validation = validate(app.broker_url, old_token)
    events.append(PipelineEvent(
        event_type="token_validated",
        agent_role="clinical",
        data={
            "valid": old_validation.valid,
            "context": "old_token_after_renewal",
            "error": old_validation.error,
        },
    ))

    # ── Token Expiry scenario: skip rest, wait for expiry ──────
    if config.scenario == "token_expiry" and config.short_ttl:
        events.append(PipelineEvent(
            event_type="waiting_for_expiry",
            agent_role="clinical",
            data={
                "ttl": config.short_ttl,
                "message": f"Waiting {config.short_ttl + 2}s for token to expire naturally...",
            },
        ))
        time.sleep(config.short_ttl + 2)
        expiry_result = validate(app.broker_url, clinical_agent.access_token)
        events.append(PipelineEvent(
            event_type="token_expired",
            agent_role="clinical",
            data={
                "valid": expiry_result.valid,
                "error": expiry_result.error,
                "message": "Token expired naturally — broker rejected it",
            },
        ))
        return events

    # ── Phase 2: Prescription Agent (Delegated) ────────────────
    # Extract clinical recommendation for prescription from LLM output
    clinical_output = ""
    for e in llm_events:
        if e.event_type == "llm_response":
            clinical_output = e.data.get("content", "")

    if config.scenario != "emergency_revoke":
        rx_base_scopes = scopes_for_tools(["check_drug_interactions"], pid)

        rx_agent = app.create_agent(
            orch_id="medassist",
            task_id=f"prescription-{pid}",
            requested_scope=rx_base_scopes,
            max_ttl=ttl,
        )
        agents_created.append(rx_agent)

        events.append(PipelineEvent(
            event_type="agent_created",
            agent_role="prescription",
            data={
                "agent_id": rx_agent.agent_id,
                "spiffe_id": rx_agent.agent_id,
                "scope": rx_agent.scope,
                "tools": ["check_drug_interactions"],
                "scopes_from_tools": rx_base_scopes,
                "expires_in": rx_agent.expires_in,
                "access_token_preview": rx_agent.access_token[:20] + "...",
                "task_id": rx_agent.task_id,
                "orch_id": rx_agent.orch_id,
                "note": "Base scope only — prescription write comes via delegation",
            },
        ))

        # Clinical agent delegates write:prescriptions:{pid} to prescription agent
        delegated_scope = [f"write:prescriptions:{pid}"]
        try:
            delegated: DelegatedToken = clinical_agent.delegate(
                delegate_to=rx_agent.agent_id,
                scope=delegated_scope,
            )
            events.append(PipelineEvent(
                event_type="delegation",
                agent_role="clinical",
                data={
                    "delegator_id": clinical_agent.agent_id,
                    "delegator_scope": clinical_agent.scope,
                    "delegate_id": rx_agent.agent_id,
                    "delegated_scope": delegated_scope,
                    "delegated_token_preview": delegated.access_token[:20] + "...",
                    "delegation_chain": [
                        {
                            "agent": rec.agent,
                            "scope": rec.scope,
                            "delegated_at": rec.delegated_at,
                        }
                        for rec in delegated.delegation_chain
                    ],
                    "expires_in": delegated.expires_in,
                    "message": (
                        f"Clinical agent delegated {delegated_scope} to prescription agent. "
                        f"Authority narrowed: clinical has {len(clinical_agent.scope)} scopes, "
                        f"prescription gets exactly 1 via delegation."
                    ),
                },
            ))

            # Validate the delegated token to show its claims
            deleg_validation = validate(app.broker_url, delegated.access_token)
            if deleg_validation.valid and deleg_validation.claims:
                events.append(PipelineEvent(
                    event_type="token_validated",
                    agent_role="prescription",
                    data={
                        "valid": True,
                        "context": "delegated_token",
                        "claims": {
                            "sub": deleg_validation.claims.sub,
                            "scope": deleg_validation.claims.scope,
                            "orch_id": deleg_validation.claims.orch_id,
                            "task_id": deleg_validation.claims.task_id,
                            "jti": deleg_validation.claims.jti,
                        },
                    },
                ))

            # Prescription agent uses BOTH its base scope + delegated scope
            rx_effective_scope = rx_base_scopes + delegated_scope

        except AuthorizationError as e:
            events.append(PipelineEvent(
                event_type="delegation_denied",
                agent_role="clinical",
                data={
                    "error": str(e),
                    "problem": {
                        "type": e.problem.type,
                        "title": e.problem.title,
                        "detail": e.problem.detail,
                        "status": e.problem.status,
                        "error_code": e.problem.error_code,
                    },
                },
            ))
            rx_effective_scope = rx_base_scopes

        # Run prescription LLM
        rx_tools = get_tools_for_role("prescription")
        rx_tool_schemas = [t.openai_schema() for t in rx_tools]

        rx_user_msg = (
            f"Patient {patient_name} (ID: {pid}) needs a prescription review. "
            f"Clinical notes: {clinical_output[:500]}... "
            f"Check for drug interactions and write any needed prescriptions."
        )

        rx_events = _run_llm_tool_loop(
            openai_client=openai_client,
            system_prompt=prescription.SYSTEM_PROMPT,
            user_message=rx_user_msg,
            tool_schemas=rx_tool_schemas,
            agent_scope=rx_effective_scope,
            patient_id=pid,
            agent_role="prescription",
        )
        events.extend(rx_events)

    # ── Phase 3: Billing Agent (Isolated) ──────────────────────
    if config.scenario != "emergency_revoke":
        billing_tool_names = [
            "get_billing_history",
            "get_insurance_coverage",
            "generate_billing_codes",
            "file_insurance_claim",
        ]
        billing_scopes = scopes_for_tools(billing_tool_names, pid)

        billing_agent = app.create_agent(
            orch_id="medassist",
            task_id=f"billing-{pid}",
            requested_scope=billing_scopes,
            max_ttl=ttl,
        )
        agents_created.append(billing_agent)

        events.append(PipelineEvent(
            event_type="agent_created",
            agent_role="billing",
            data={
                "agent_id": billing_agent.agent_id,
                "spiffe_id": billing_agent.agent_id,
                "scope": billing_agent.scope,
                "tools": billing_tool_names,
                "scopes_from_tools": billing_scopes,
                "expires_in": billing_agent.expires_in,
                "access_token_preview": billing_agent.access_token[:20] + "...",
                "task_id": billing_agent.task_id,
                "orch_id": billing_agent.orch_id,
                "isolation_note": (
                    "Billing agent has NO read:records scope — "
                    "cannot access medical records. HIPAA isolation enforced."
                ),
            },
        ))

        # Billing LLM — includes get_patient_records in its tools,
        # but its scope won't allow it. The LLM will try, get denied.
        billing_tools = get_tools_for_role("billing")
        billing_tool_schemas = [t.openai_schema() for t in billing_tools]

        billing_user_msg = (
            f"Process billing for patient {patient_name} (ID: {pid}). "
            f"Check their insurance coverage, review billing history, "
            f"generate billing codes for today's encounter, and file an insurance claim. "
            f"You may want to review the patient's clinical records to determine "
            f"the correct billing codes."
        )

        billing_events = _run_llm_tool_loop(
            openai_client=openai_client,
            system_prompt=billing.SYSTEM_PROMPT,
            user_message=billing_user_msg,
            tool_schemas=billing_tool_schemas,
            agent_scope=billing_agent.scope,
            patient_id=pid,
            agent_role="billing",
        )
        events.extend(billing_events)

    # ── Emergency Revoke Scenario ──────────────────────────────
    if config.scenario == "emergency_revoke" or config.trigger_revoke:
        events.append(PipelineEvent(
            event_type="breach_detected",
            agent_role="system",
            data={
                "message": "BREACH DETECTED — revoking all agents for this encounter",
                "task_target": f"encounter-{pid}",
            },
        ))

        # Authenticate as admin and revoke by task
        try:
            admin_resp = httpx.post(
                f"{app.broker_url}/v1/admin/auth",
                json={"secret": admin_secret},
                timeout=10,
            )
            admin_resp.raise_for_status()
            admin_token = admin_resp.json()["access_token"]

            revoke_resp = httpx.post(
                f"{app.broker_url}/v1/revoke",
                json={"level": "task", "target": f"encounter-{pid}"},
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=10,
            )
            revoke_data = revoke_resp.json()

            events.append(PipelineEvent(
                event_type="revocation",
                agent_role="system",
                data={
                    "level": "task",
                    "target": f"encounter-{pid}",
                    "revoked": revoke_data.get("revoked", False),
                    "count": revoke_data.get("count", 0),
                },
            ))
        except Exception as e:
            events.append(PipelineEvent(
                event_type="revocation_error",
                agent_role="system",
                data={"error": str(e)},
            ))

        # Verify all tokens are now dead
        for agent in agents_created:
            result = validate(app.broker_url, agent.access_token)
            events.append(PipelineEvent(
                event_type="post_revoke_validation",
                agent_role="system",
                data={
                    "agent_id": agent.agent_id,
                    "valid": result.valid,
                    "error": result.error,
                    "message": (
                        "Token is DEAD — broker rejected it"
                        if not result.valid
                        else "WARNING: Token still valid after revocation"
                    ),
                },
            ))

        return events

    # ── Phase 4: Cleanup ───────────────────────────────────────
    for agent in agents_created:
        token_before = agent.access_token
        try:
            agent.release()
            events.append(PipelineEvent(
                event_type="token_released",
                agent_role="system",
                data={
                    "agent_id": agent.agent_id,
                    "spiffe_id": agent.agent_id,
                    "task_id": agent.task_id,
                },
            ))
        except AgentWritError as e:
            events.append(PipelineEvent(
                event_type="release_error",
                agent_role="system",
                data={"agent_id": agent.agent_id, "error": str(e)},
            ))

        # Validate released token to prove it's dead
        result = validate(app.broker_url, token_before)
        events.append(PipelineEvent(
            event_type="post_release_validation",
            agent_role="system",
            data={
                "agent_id": agent.agent_id,
                "valid": result.valid,
                "error": result.error,
            },
        ))

    events.append(PipelineEvent(
        event_type="encounter_complete",
        agent_role="system",
        data={
            "patient_id": pid,
            "agents_used": len(agents_created),
            "message": "All agents released and tokens confirmed dead.",
        },
    ))

    return events
