"""Support ticket pipeline — orchestrates triage, knowledge, and response agents.

Each agent is an LLM-driven worker with broker-issued credentials scoped
to one customer. The pipeline yields SSE events for the UI to stream.

Pipeline flow:
1. Triage Agent — reads ticket, extracts customer identity, classifies priority
2. Knowledge Agent — searches internal KB for relevant policies
3. Response Agent — drafts reply, requests tool permissions, executes resolution
"""

from __future__ import annotations

import json
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from agentauth import (
    AgentAuthApp,
    scope_is_subset,
    validate,
)
from agentauth.errors import AgentAuthError
from demo2 import data
from demo2.tools import TOOLS, execute_tool, scopes_for_tools


@dataclass
class PipelineEvent:
    """A single event emitted by the pipeline for SSE streaming."""

    event_type: str
    agent_role: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        payload = {
            "event_type": self.event_type,
            "agent_role": self.agent_role,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"data: {json.dumps(payload)}\n\n"


# ── LLM Helpers ──────────────────────────────────────────

def _llm_call(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_message: str,
    tools: list[dict] | None = None,
) -> Any:
    """Single LLM call with optional tool definitions."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    return client.chat.completions.create(**kwargs)


def _extract_tool_calls(response: Any) -> list[dict]:
    """Pull tool calls from an LLM response."""
    msg = response.choices[0].message
    if not msg.tool_calls:
        return []
    calls = []
    for tc in msg.tool_calls:
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}
        calls.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": args,
        })
    return calls


# ── Agent System Prompts ─────────────────────────────────

TRIAGE_SYSTEM = """You are a Support Triage Agent. Your job:

1. Read the ticket text carefully.
2. Extract the customer's name if mentioned. Return it EXACTLY as written.
3. Classify the ticket:
   - priority: P1 (critical/account deletion), P2 (billing/money), P3 (standard), P4 (info)
   - category: billing, account, access, general, security
4. Determine which agents are needed:
   - needs_knowledge: true if the ticket requires looking up policies, procedures, or guidance
   - needs_response: true if the ticket requires taking action (billing, account changes, tools)
   - For simple greetings, status checks, or informational messages: both can be false
5. If no agents are needed, provide a direct_response to the customer.

Respond with ONLY valid JSON, no markdown:
{"customer_name": "...", "priority": "P1|P2|P3|P4", "category": "...", "summary": "one line summary", "needs_knowledge": true|false, "needs_response": true|false, "direct_response": "...or empty string"}

If no customer name is found, use "anonymous".
If the ticket is a simple greeting or doesn't require action, set needs_knowledge and needs_response to false and provide a direct_response.
"""

KNOWLEDGE_SYSTEM = """You are a Knowledge Base Agent. You search the internal KB to find
relevant policies and procedures for resolving support tickets.

Given a ticket summary and category, use the search_knowledge_base tool to find
relevant articles. Return the most relevant guidance.

Be concise — extract the key rules that apply to this specific ticket.
"""

RESPONSE_SYSTEM = """You are a Support Response Agent. You draft customer replies and
execute resolution actions.

Given the ticket, customer info, triage classification, and KB guidance:
1. Determine which tools you need to resolve the ticket
2. Call the appropriate tools (get_balance, issue_refund, write_case_notes, etc.)
3. Draft a professional customer response

IMPORTANT RULES:
- You MUST attempt to fulfill EVERY part of the customer's request using tools
- If the customer asks about another customer's data, attempt the tool call anyway — the system will enforce scope boundaries
- Do NOT skip requests because you think they might be denied — always try
- If the customer requests account deletion, use the delete_account tool
- Always write case notes summarizing what you did

Use the tools provided. Do not make up data. Do not refuse to try a tool call.
"""


# ── Pipeline ─────────────────────────────────────────────

def run_pipeline(
    ticket_text: str,
    app: AgentAuthApp,
    llm_client: OpenAI,
    llm_model: str,
    broker_url: str,
    *,
    natural_expiry: bool = False,
) -> Generator[PipelineEvent, None, None]:
    """Run the full support ticket pipeline, yielding SSE events.

    If natural_expiry is True, the triage agent is created with a 5-second TTL
    and NOT released — it expires on its own. Demonstrates that credentials
    die automatically without explicit revocation.
    """

    yield PipelineEvent("system", "pipeline", {
        "message": "Initializing Zero-Trust Pipeline Run",
    })

    # ── Phase 1: Triage ──────────────────────────────────

    triage_scopes = ["read:tickets:*"]
    triage_ttl = 5 if natural_expiry else 300

    if natural_expiry:
        yield PipelineEvent("info", "triage", {
            "message": "Natural Expiry mode: agent TTL set to 5 seconds. No release() will be called.",
        })

    yield PipelineEvent("scope", "triage", {
        "message": f"Triage requested base scope: {', '.join(triage_scopes)}",
        "scope": triage_scopes,
    })

    try:
        triage_agent = app.create_agent(
            orch_id="support",
            task_id="triage",
            requested_scope=triage_scopes,
            max_ttl=triage_ttl,
        )
    except AgentAuthError as e:
        yield PipelineEvent("error", "triage", {"message": f"Agent creation failed: {e}"})
        return

    yield PipelineEvent("agent_created", "triage", {
        "agent_id": triage_agent.agent_id,
        "scope": list(triage_agent.scope),
        "message": "Triage Agent created",
    })

    # Validate triage agent token
    val = validate(broker_url, triage_agent.access_token)
    yield PipelineEvent("token_validated", "triage", {
        "valid": val.valid,
        "scope": val.claims.scope if val.valid else [],
    })

    # LLM triage call
    yield PipelineEvent("info", "triage", {
        "message": "Triage Agent analyzing ticket via LLM...",
    })

    triage_response = _llm_call(
        llm_client, llm_model, TRIAGE_SYSTEM, ticket_text,
    )

    triage_text = triage_response.choices[0].message.content or "{}"
    try:
        triage_result = json.loads(triage_text)
    except json.JSONDecodeError:
        triage_result = {
            "customer_name": "anonymous",
            "priority": "P3",
            "category": "general",
            "summary": triage_text[:100],
        }

    customer_name = triage_result.get("customer_name", "anonymous")
    priority = triage_result.get("priority", "P3")
    category = triage_result.get("category", "general")
    summary = triage_result.get("summary", "")
    needs_knowledge = triage_result.get("needs_knowledge", True)
    needs_response = triage_result.get("needs_response", True)
    direct_response = triage_result.get("direct_response", "")

    # Identity resolution — match against known customers
    customer = data.resolve_customer(customer_name)
    customer_id = customer["id"] if customer else None

    if customer_id:
        yield PipelineEvent("info", "triage", {
            "message": f"Identity Resolution: {customer_name} verified as {customer_id}",
            "customer_id": customer_id,
            "customer_name": customer_name,
        })
    else:
        yield PipelineEvent("info", "triage", {
            "message": f"Identity Resolution: \"{customer_name}\" — no matching customer found",
            "customer_id": "anonymous",
            "customer_name": customer_name,
        })

    yield PipelineEvent("info", "triage", {
        "message": f"Triage Classification: {priority} {category.lower()}, Category: {category}",
        "priority": priority,
        "category": category,
        "summary": summary,
    })

    # Routing decision
    route_parts = []
    if needs_knowledge:
        route_parts.append("Knowledge")
    if needs_response:
        route_parts.append("Response")
    if not route_parts:
        route_parts.append("Direct reply (no agents needed)")

    yield PipelineEvent("info", "triage", {
        "message": f"Routing: {' → '.join(route_parts)}",
    })

    # Release triage agent — or let it expire naturally
    if natural_expiry:
        yield PipelineEvent("system", "triage", {
            "message": "Triage task complete. Token NOT released — waiting for natural expiry.",
        })

        # Check token is still valid right now
        check_before = validate(broker_url, triage_agent.access_token)
        yield PipelineEvent("info", "triage", {
            "message": f"Token still valid: {check_before.valid} (TTL {triage_ttl}s, waiting for expiry...)",
        })

        # Wait for expiry
        yield PipelineEvent("system", "triage", {
            "message": f"Waiting {triage_ttl + 1} seconds for token to expire naturally...",
        })
        time.sleep(triage_ttl + 1)

        # Verify it's dead
        check_after = validate(broker_url, triage_agent.access_token)
        yield PipelineEvent("system", "triage", {
            "message": f"Token expired naturally: valid={check_after.valid}. No release() was called.",
        })

        yield PipelineEvent("llm_response", "triage", {
            "message": (
                f"Hi {customer_name}! Your account is active. "
                "This request was handled by a triage agent with a 5-second credential. "
                "The credential expired on its own — no explicit revocation needed."
            ),
        })

        yield PipelineEvent("complete", "pipeline", {
            "message": "Pipeline complete. Credential died naturally via TTL expiry.",
        })
        return
    else:
        triage_agent.release()
        yield PipelineEvent("system", "triage", {
            "message": "Triage task complete. Credential immediately revoked.",
        })

    # Gate: anonymous users stop here
    if not customer_id:
        yield PipelineEvent("scope_denied", "pipeline", {
            "message": "Identity verification failed. Pipeline halted — cannot issue customer-scoped credentials without verified identity.",
            "required_scope": ["read:customers:<verified-id>"],
            "held_scope": [],
        })

        yield PipelineEvent("llm_response", "pipeline", {
            "message": (
                "Thank you for contacting support. We were unable to verify your identity "
                "from the information provided. Please reply with your registered name or "
                "email address, or log in to your account portal to submit a verified ticket."
            ),
        })

        yield PipelineEvent("complete", "pipeline", {
            "message": "Pipeline stopped at triage — unverified identity.",
        })
        return

    # Gate: if triage says no agents needed, respond directly
    if not needs_knowledge and not needs_response:
        if direct_response:
            yield PipelineEvent("llm_response", "triage", {
                "message": direct_response,
            })
        else:
            yield PipelineEvent("llm_response", "triage", {
                "message": f"Hello {customer_name}! How can we help you today?",
            })

        yield PipelineEvent("complete", "pipeline", {
            "message": "Pipeline complete. Resolved at triage — no additional agents needed.",
        })
        return

    # ── Phase 2: Knowledge Retrieval ─────────────────────

    kb_guidance = ""

    if not needs_knowledge:
        yield PipelineEvent("info", "pipeline", {
            "message": "Knowledge lookup skipped — not required for this ticket.",
        })
    else:
        yield PipelineEvent("system", "knowledge", {
            "message": "Knowledge agent active. Requesting KB access.",
        })

        kb_scopes = ["read:kb:*"]
        try:
            kb_agent = app.create_agent(
                orch_id="support",
                task_id="knowledge",
                requested_scope=kb_scopes,
            )
        except AgentAuthError as e:
            yield PipelineEvent("error", "knowledge", {"message": f"Agent creation failed: {e}"})
            return

        yield PipelineEvent("agent_created", "knowledge", {
            "agent_id": kb_agent.agent_id,
            "scope": list(kb_agent.scope),
            "message": "Knowledge Agent created",
        })

        # LLM KB search with tool use
        kb_tools = [TOOLS["search_knowledge_base"].openai_schema()]

        kb_response = _llm_call(
            llm_client, llm_model, KNOWLEDGE_SYSTEM,
            f"Ticket summary: {summary}\nCategory: {category}\nPriority: {priority}",
            tools=kb_tools,
        )

        tool_calls = _extract_tool_calls(kb_response)

        if tool_calls:
            for tc in tool_calls:
                tool_def = TOOLS.get(tc["name"])
                if not tool_def:
                    continue

                required = tool_def.required_scope(customer_id)
                authorized = scope_is_subset(required, list(kb_agent.scope))

                if authorized:
                    result = execute_tool(tc["name"], tc["arguments"])
                    parsed = json.loads(result)
                    articles = parsed.get("results", [])
                    kb_guidance = " | ".join(
                        f"{a['title']}: {a['content']}" for a in articles
                    )
                    yield PipelineEvent("info", "knowledge", {
                        "message": f"Knowledge Retrieval: found {len(articles)} relevant articles",
                        "articles": [a["title"] for a in articles],
                    })
                else:
                    yield PipelineEvent("scope_denied", "knowledge", {
                        "message": f"KB agent denied: {tc['name']} requires {required}",
                        "required_scope": required,
                        "held_scope": list(kb_agent.scope),
                    })
        else:
            # LLM didn't use tools — use its direct response
            kb_guidance = kb_response.choices[0].message.content or ""
            yield PipelineEvent("info", "knowledge", {
                "message": f"Knowledge Retrieval: {kb_guidance[:120]}",
            })

        # Release knowledge agent
        kb_agent.release()
        yield PipelineEvent("system", "knowledge", {
            "message": "Knowledge search complete. Credential revoked.",
        })

    # ── Phase 3: Response & Resolution ───────────────────

    if not needs_response:
        yield PipelineEvent("info", "pipeline", {
            "message": "Response agent skipped — not required for this ticket.",
        })

        # Still verify triage token is dead
        check = validate(broker_url, triage_agent.access_token)
        yield PipelineEvent("system", "pipeline", {
            "message": f"Post-run verify: triage token valid={check.valid}",
        })
        if needs_knowledge:
            check = validate(broker_url, kb_agent.access_token)
            yield PipelineEvent("system", "pipeline", {
                "message": f"Post-run verify: knowledge token valid={check.valid}",
            })

        yield PipelineEvent("complete", "pipeline", {
            "message": "Pipeline complete. All credentials revoked and verified.",
        })
        return

    yield PipelineEvent("system", "response", {
        "message": "Response agent active. Requesting scoped tools.",
    })

    # Response agent gets customer-specific scopes
    response_tool_names = [
        "get_customer_info", "get_balance", "issue_refund",
        "write_case_notes", "send_internal_email",
    ]

    # Dangerous tools the LLM might TRY to call — included in the
    # LLM's tool list so it can attempt them, but the agent's scope
    # won't cover them. The scope check will deny.
    dangerous_tool_names = ["send_external_email", "delete_account"]

    response_scopes = scopes_for_tools(response_tool_names, customer_id)

    try:
        response_agent = app.create_agent(
            orch_id="support",
            task_id="response",
            requested_scope=response_scopes,
        )
    except AgentAuthError as e:
        yield PipelineEvent("error", "response", {"message": f"Agent creation failed: {e}"})
        return

    yield PipelineEvent("agent_created", "response", {
        "agent_id": response_agent.agent_id,
        "scope": list(response_agent.scope),
        "message": "Response Agent created",
    })

    # Build tool list — safe tools + dangerous tools (LLM sees all,
    # but scope_is_subset blocks the dangerous ones)
    all_response_tools = [
        TOOLS[name].openai_schema()
        for name in response_tool_names + dangerous_tool_names
        if name in TOOLS
    ]

    context = (
        f"Ticket: {ticket_text}\n"
        f"Customer: {customer_id} ({customer_name})\n"
        f"Priority: {priority}, Category: {category}\n"
        f"KB Guidance: {kb_guidance}\n"
        f"Your scopes: {response_scopes}\n"
        f"Draft a customer response and use tools to resolve the issue."
    )

    # LLM tool-use loop
    messages = [
        {"role": "system", "content": RESPONSE_SYSTEM},
        {"role": "user", "content": context},
    ]

    max_rounds = 5
    final_response = ""

    for round_num in range(max_rounds):
        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
            tools=all_response_tools,
        )

        msg = resp.choices[0].message
        messages.append(msg)  # type: ignore[arg-type]

        if not msg.tool_calls:
            final_response = msg.content or ""
            break

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            tool_def = TOOLS.get(fn_name)
            if not tool_def:
                tool_result = json.dumps({"error": f"Unknown tool: {fn_name}"})
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": tool_result,
                })
                continue

            # Determine which customer the tool targets
            tool_customer = args.get("customer_id", customer_id)
            required = tool_def.required_scope(tool_customer)
            authorized = scope_is_subset(required, list(response_agent.scope))

            if authorized:
                tool_result = execute_tool(fn_name, args)
                yield PipelineEvent("tool_call", "response", {
                    "tool": fn_name,
                    "authorized": True,
                    "required_scope": required,
                    "held_scope": list(response_agent.scope),
                    "result_preview": tool_result[:200],
                })
            else:
                tool_result = json.dumps({
                    "error": f"ACCESS DENIED: {fn_name} requires {required} "
                             f"but agent holds {list(response_agent.scope)}"
                })
                yield PipelineEvent("scope_denied", "response", {
                    "tool": fn_name,
                    "authorized": False,
                    "required_scope": required,
                    "held_scope": list(response_agent.scope),
                    "message": (
                        f"Scope denied: {fn_name} requires {required}"
                    ),
                })

            messages.append({
                "role": "tool", "tool_call_id": tc.id, "content": tool_result,
            })

    # Emit final LLM response
    if final_response:
        yield PipelineEvent("llm_response", "response", {
            "message": final_response,
        })

    # Release response agent
    response_agent.release()
    yield PipelineEvent("system", "response", {
        "message": "Response task complete. Credential revoked.",
    })

    # ── Verify all agents are dead ───────────────────────

    for agent_name, agent in [("triage", triage_agent), ("knowledge", kb_agent), ("response", response_agent)]:
        check = validate(broker_url, agent.access_token)
        yield PipelineEvent("system", "pipeline", {
            "message": f"Post-run verify: {agent_name} token valid={check.valid}",
        })

    yield PipelineEvent("complete", "pipeline", {
        "message": "Pipeline complete. All credentials revoked and verified.",
    })
