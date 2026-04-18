"""Healthcare tools with scope-gated execution.

Each tool is an OpenAI function definition that an LLM agent can call.
Every tool maps to a required AgentWrit scope parameterized by patient_id.
Before execution, the pipeline checks scope_is_subset() — the agent must
hold the exact scope for the specific patient and action.

The LLM decides which tools to use. The tools decide which scopes are
required. The agent only gets the scopes matching its authorized tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from demo.data import patients


@dataclass(frozen=True)
class ToolResult:
    """Outcome of a tool execution attempt."""

    tool_name: str
    authorized: bool
    required_scope: list[str]
    held_scope: list[str]
    output: str | None = None
    denial_reason: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    """A tool the LLM can call, with its scope requirement template."""

    name: str
    description: str
    scope_template: str  # e.g. "read:records:{patient_id}"
    parameters: dict[str, Any] = field(default_factory=dict)

    def required_scope(self, patient_id: str) -> list[str]:
        """Resolve the scope template with a concrete patient ID.

        Templates with literal '*' (like read:formulary:*) are reference
        data scopes and don't get patient-specific substitution.
        """
        if "{patient_id}" in self.scope_template:
            return [self.scope_template.format(patient_id=patient_id)]
        return [self.scope_template]

    def openai_schema(self) -> dict[str, Any]:
        """Return OpenAI function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── Tool Registry ──────────────────────────────────────────────

TOOLS: dict[str, ToolDefinition] = {}


def _register(tool: ToolDefinition) -> ToolDefinition:
    TOOLS[tool.name] = tool
    return tool


# ── Clinical Tools ─────────────────────────────────────────────

get_patient_records = _register(ToolDefinition(
    name="get_patient_records",
    description="Retrieve a patient's medical history including visit notes, diagnoses, and vitals. Returns the full clinical record.",
    scope_template="read:records:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID (e.g. P-1042)",
            },
        },
        "required": ["patient_id"],
    },
))

write_clinical_notes = _register(ToolDefinition(
    name="write_clinical_notes",
    description="Write clinical notes for the current encounter. Include assessment, plan, and any orders.",
    scope_template="write:records:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID",
            },
            "notes": {
                "type": "string",
                "description": "The clinical notes to record",
            },
            "diagnoses": {
                "type": "array",
                "items": {"type": "string"},
                "description": "ICD-10 diagnosis codes with descriptions",
            },
        },
        "required": ["patient_id", "notes"],
    },
))

get_lab_results = _register(ToolDefinition(
    name="get_lab_results",
    description="Retrieve a patient's lab test results including values, reference ranges, and flags.",
    scope_template="read:labs:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID",
            },
        },
        "required": ["patient_id"],
    },
))

# ── Prescription Tools ─────────────────────────────────────────

check_drug_interactions = _register(ToolDefinition(
    name="check_drug_interactions",
    description="Check a proposed medication against the patient's current prescriptions for drug interactions. Returns severity and clinical notes for any interactions found.",
    scope_template="read:formulary:*",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID to look up current meds",
            },
            "proposed_drug": {
                "type": "string",
                "description": "Name of the drug to check (e.g. Glipizide)",
            },
        },
        "required": ["patient_id", "proposed_drug"],
    },
))

write_prescription = _register(ToolDefinition(
    name="write_prescription",
    description="Write a new prescription for a patient. Requires the drug name, dose, frequency, and clinical indication.",
    scope_template="write:prescriptions:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID",
            },
            "drug": {
                "type": "string",
                "description": "Drug name (e.g. Lisinopril)",
            },
            "dose": {
                "type": "string",
                "description": "Dosage (e.g. 20mg)",
            },
            "frequency": {
                "type": "string",
                "description": "Dosing frequency (e.g. once daily)",
            },
            "indication": {
                "type": "string",
                "description": "Clinical reason for prescribing",
            },
        },
        "required": ["patient_id", "drug", "dose", "frequency"],
    },
))

# ── Billing Tools ──────────────────────────────────────────────

get_billing_history = _register(ToolDefinition(
    name="get_billing_history",
    description="Retrieve a patient's billing history including past charges, insurance payments, and outstanding balances.",
    scope_template="read:billing:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID",
            },
        },
        "required": ["patient_id"],
    },
))

get_insurance_coverage = _register(ToolDefinition(
    name="get_insurance_coverage",
    description="Retrieve a patient's insurance coverage details including provider, plan, copay, and deductible remaining.",
    scope_template="read:insurance:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID",
            },
        },
        "required": ["patient_id"],
    },
))

generate_billing_codes = _register(ToolDefinition(
    name="generate_billing_codes",
    description="Generate ICD-10 and CPT billing codes for an encounter based on diagnoses and procedures performed. Returns structured billing data ready for claim submission.",
    scope_template="write:billing:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID",
            },
            "diagnoses": {
                "type": "array",
                "items": {"type": "string"},
                "description": "ICD-10 codes from the encounter",
            },
            "procedures": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Procedures performed (e.g. 'Office visit, moderate complexity')",
            },
        },
        "required": ["patient_id", "diagnoses", "procedures"],
    },
))

file_insurance_claim = _register(ToolDefinition(
    name="file_insurance_claim",
    description="Submit an insurance claim for an encounter. Requires billing codes and total charges. Returns claim confirmation with estimated reimbursement.",
    scope_template="write:billing:{patient_id}",
    parameters={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "The patient ID",
            },
            "billing_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "CPT codes for the claim",
            },
            "total_charges": {
                "type": "number",
                "description": "Total charges in dollars",
            },
        },
        "required": ["patient_id", "billing_codes", "total_charges"],
    },
))


# ── Tool Execution Engine ──────────────────────────────────────

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool with the given arguments. Returns JSON string output.

    This performs the actual data lookup against mock patient data.
    Scope checking is NOT done here — the caller (pipeline runner)
    must check scope_is_subset() BEFORE calling this function.
    """
    pid = arguments.get("patient_id", "")

    if tool_name == "get_patient_records":
        records = patients.get_medical_records(pid)
        if not records:
            return json.dumps({"error": f"No records found for {pid}"})
        return json.dumps(records, indent=2)

    elif tool_name == "write_clinical_notes":
        return json.dumps({
            "status": "saved",
            "patient_id": pid,
            "timestamp": "2026-04-08T10:30:00Z",
            "notes_preview": arguments.get("notes", "")[:100] + "...",
            "diagnoses_recorded": arguments.get("diagnoses", []),
        })

    elif tool_name == "get_lab_results":
        labs = patients.get_lab_results(pid)
        if not labs:
            return json.dumps({"error": f"No lab results found for {pid}"})
        return json.dumps(labs, indent=2)

    elif tool_name == "check_drug_interactions":
        proposed = arguments.get("proposed_drug", "")
        current_rxs = patients.get_prescriptions(pid)
        current_drugs = [rx["drug"] for rx in current_rxs]
        interactions = patients.check_drug_interactions(proposed, current_drugs)
        return json.dumps({
            "proposed_drug": proposed,
            "current_medications": current_drugs,
            "interactions_found": len(interactions),
            "interactions": interactions,
        }, indent=2)

    elif tool_name == "write_prescription":
        return json.dumps({
            "status": "prescribed",
            "patient_id": pid,
            "drug": arguments.get("drug", ""),
            "dose": arguments.get("dose", ""),
            "frequency": arguments.get("frequency", ""),
            "indication": arguments.get("indication", ""),
            "prescriber": "MedAssist AI Clinical Agent",
            "timestamp": "2026-04-08T10:35:00Z",
            "refills": 3,
        })

    elif tool_name == "get_billing_history":
        billing = patients.get_billing_history(pid)
        if not billing:
            return json.dumps({"error": f"No billing history for {pid}"})
        return json.dumps(billing, indent=2)

    elif tool_name == "get_insurance_coverage":
        insurance = patients.get_insurance_info(pid)
        if not insurance:
            return json.dumps({"error": f"No insurance info for {pid}"})
        return json.dumps(insurance, indent=2)

    elif tool_name == "generate_billing_codes":
        return json.dumps({
            "status": "codes_generated",
            "patient_id": pid,
            "icd10_codes": arguments.get("diagnoses", []),
            "cpt_codes": arguments.get("procedures", []),
            "estimated_charges": 285.00,
            "timestamp": "2026-04-08T10:40:00Z",
        })

    elif tool_name == "file_insurance_claim":
        insurance = patients.get_insurance_info(pid)
        copay = insurance.get("copay", 0) if insurance else 0
        total = arguments.get("total_charges", 0)
        return json.dumps({
            "status": "claim_submitted",
            "patient_id": pid,
            "claim_id": f"CLM-{pid}-20260408",
            "billing_codes": arguments.get("billing_codes", []),
            "total_charges": total,
            "estimated_insurance_payment": total - copay,
            "estimated_patient_responsibility": copay,
            "timestamp": "2026-04-08T10:45:00Z",
        })

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def get_tools_for_role(role: str) -> list[ToolDefinition]:
    """Return the tool definitions available to a given agent role."""
    role_tools: dict[str, list[str]] = {
        "clinical": [
            "get_patient_records",
            "write_clinical_notes",
            "get_lab_results",
        ],
        "prescription": [
            "check_drug_interactions",
            "write_prescription",
        ],
        "billing": [
            "get_billing_history",
            "get_insurance_coverage",
            "generate_billing_codes",
            "file_insurance_claim",
            "get_patient_records",  # billing will TRY to call this — scope blocks it
        ],
    }
    return [TOOLS[name] for name in role_tools.get(role, []) if name in TOOLS]


def scopes_for_tools(tool_names: list[str], patient_id: str) -> list[str]:
    """Compute the exact scopes needed for a set of tools + patient.

    This is how agents get granular scopes: the tool set determines
    the scope set, parameterized by the specific patient ID.
    """
    scopes: list[str] = []
    seen: set[str] = set()
    for name in tool_names:
        tool = TOOLS.get(name)
        if tool:
            for s in tool.required_scope(patient_id):
                if s not in seen:
                    scopes.append(s)
                    seen.add(s)
    return scopes
