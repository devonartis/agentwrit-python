"""Support tools with scope-gated execution.

Each tool maps to a required AgentAuth scope parameterized by customer_id.
The LLM decides which tools to use. The pipeline checks scope_is_subset()
before every execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from demo2 import data


@dataclass(frozen=True)
class ToolDefinition:
    """A tool the LLM can call, with its scope requirement template."""

    name: str
    description: str
    scope_template: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def required_scope(self, customer_id: str) -> list[str]:
        if "{customer_id}" in self.scope_template:
            return [self.scope_template.format(customer_id=customer_id)]
        return [self.scope_template]

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


TOOLS: dict[str, ToolDefinition] = {}


def _register(tool: ToolDefinition) -> ToolDefinition:
    TOOLS[tool.name] = tool
    return tool


# ── Triage Tools ─────────────────────────────────────────

read_ticket = _register(ToolDefinition(
    name="read_ticket",
    description="Read the full support ticket content.",
    scope_template="read:tickets:*",
    parameters={
        "type": "object",
        "properties": {
            "ticket_text": {
                "type": "string",
                "description": "The ticket content to analyze",
            },
        },
        "required": ["ticket_text"],
    },
))

# ── Customer Tools ───────────────────────────────────────

get_customer_info = _register(ToolDefinition(
    name="get_customer_info",
    description="Retrieve a customer's profile including plan, status, and contact info.",
    scope_template="read:customers:{customer_id}",
    parameters={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "The customer ID"},
        },
        "required": ["customer_id"],
    },
))

get_balance = _register(ToolDefinition(
    name="get_balance",
    description="Get a customer's current account balance and last payment date.",
    scope_template="read:billing:{customer_id}",
    parameters={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "The customer ID"},
        },
        "required": ["customer_id"],
    },
))

issue_refund = _register(ToolDefinition(
    name="issue_refund",
    description="Issue a refund to a customer's account.",
    scope_template="write:billing:{customer_id}",
    parameters={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "The customer ID"},
            "amount": {"type": "number", "description": "Refund amount in dollars"},
            "reason": {"type": "string", "description": "Reason for refund"},
        },
        "required": ["customer_id", "amount", "reason"],
    },
))

# ── Knowledge Base Tools ─────────────────────────────────

search_knowledge_base = _register(ToolDefinition(
    name="search_knowledge_base",
    description="Search the internal knowledge base for policies, procedures, and guidance.",
    scope_template="read:kb:*",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "category": {
                "type": "string",
                "description": "Optional category filter",
                "enum": ["billing", "account", "access", "security"],
            },
        },
        "required": ["query"],
    },
))

# ── Response Tools ───────────────────────────────────────

write_case_notes = _register(ToolDefinition(
    name="write_case_notes",
    description="Write internal case notes for the support ticket.",
    scope_template="write:notes:{customer_id}",
    parameters={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "The customer ID"},
            "notes": {"type": "string", "description": "Case notes to save"},
        },
        "required": ["customer_id", "notes"],
    },
))

send_internal_email = _register(ToolDefinition(
    name="send_internal_email",
    description="Send an email to an internal company address (@company.com only).",
    scope_template="write:email:internal",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body"},
        },
        "required": ["to", "subject", "body"],
    },
))

send_external_email = _register(ToolDefinition(
    name="send_external_email",
    description="Send an email to any external address.",
    scope_template="write:email:external",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body"},
        },
        "required": ["to", "subject", "body"],
    },
))

delete_account = _register(ToolDefinition(
    name="delete_account",
    description="Permanently delete a customer's account and all associated data. IRREVERSIBLE.",
    scope_template="delete:account:{customer_id}",
    parameters={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "The customer ID"},
            "confirmation": {"type": "string", "description": "Must be 'CONFIRM_DELETE'"},
        },
        "required": ["customer_id", "confirmation"],
    },
))


# ── Tool Execution ───────────────────────────────────────

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool. Scope checking is NOT done here — caller must check first."""
    cid = arguments.get("customer_id", "")

    if tool_name == "read_ticket":
        return json.dumps({"status": "read", "content": arguments.get("ticket_text", "")})

    elif tool_name == "get_customer_info":
        customer = data.get_customer(cid)
        if not customer:
            return json.dumps({"error": f"Customer {cid} not found"})
        return json.dumps(customer, indent=2)

    elif tool_name == "get_balance":
        customer = data.get_customer(cid)
        if not customer:
            return json.dumps({"error": f"Customer {cid} not found"})
        return json.dumps({
            "customer_id": cid,
            "balance": customer["balance"],
            "last_payment": customer["last_payment"],
            "plan": customer["plan"],
        })

    elif tool_name == "issue_refund":
        return json.dumps({
            "status": "refund_issued",
            "customer_id": cid,
            "amount": arguments.get("amount", 0),
            "reason": arguments.get("reason", ""),
            "new_balance": 0.00,
            "timestamp": "2026-04-09T10:00:00Z",
        })

    elif tool_name == "search_knowledge_base":
        results = data.search_kb(
            arguments.get("query", ""),
            arguments.get("category"),
        )
        return json.dumps({"results": results, "count": len(results)}, indent=2)

    elif tool_name == "write_case_notes":
        return json.dumps({
            "status": "saved",
            "customer_id": cid,
            "notes_preview": arguments.get("notes", "")[:100],
            "timestamp": "2026-04-09T10:05:00Z",
        })

    elif tool_name == "send_internal_email":
        return json.dumps({
            "status": "sent",
            "to": arguments.get("to", ""),
            "subject": arguments.get("subject", ""),
            "timestamp": "2026-04-09T10:06:00Z",
        })

    elif tool_name == "send_external_email":
        return json.dumps({
            "status": "sent",
            "to": arguments.get("to", ""),
            "subject": arguments.get("subject", ""),
            "timestamp": "2026-04-09T10:06:00Z",
        })

    elif tool_name == "delete_account":
        if arguments.get("confirmation") != "CONFIRM_DELETE":
            return json.dumps({"error": "Deletion requires confirmation='CONFIRM_DELETE'"})
        return json.dumps({
            "status": "account_deleted",
            "customer_id": cid,
            "timestamp": "2026-04-09T10:07:00Z",
            "data_purge_eta": "72 hours",
        })

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def scopes_for_tools(tool_names: list[str], customer_id: str) -> list[str]:
    """Compute the exact scopes needed for a set of tools + customer."""
    scopes: list[str] = []
    seen: set[str] = set()
    for name in tool_names:
        tool = TOOLS.get(name)
        if tool:
            for s in tool.required_scope(customer_id):
                if s not in seen:
                    scopes.append(s)
                    seen.add(s)
    return scopes
