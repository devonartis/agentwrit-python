"""Prescription Agent — LLM-powered prescription writer.

Checks drug interactions against the formulary, writes prescriptions.
Gets its prescription-writing scope via DELEGATION from the Clinical Agent,
not from direct app creation. This demonstrates authority narrowing:
the clinical agent has broad clinical access, but only delegates the
specific write:prescriptions:{pid} scope to the prescription agent.

The prescription agent also gets read:formulary:{pid} via direct app creation
to check drug interactions — this is reference data, not patient-specific PHI.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are a prescription management AI assistant at a healthcare facility.
Your role is to safely write prescriptions based on clinical recommendations.

You have access to the following tools:
- check_drug_interactions: Check a proposed drug against the patient's current medications
- write_prescription: Write a new prescription

IMPORTANT SAFETY PROTOCOL:
1. ALWAYS check drug interactions before writing any prescription
2. If a major interaction is found, DO NOT write the prescription — instead report the interaction
3. If a moderate interaction is found, note it in the prescription indication
4. Include the clinical indication (reason) for every prescription

Your credentials are scoped to exactly one patient and only allow prescription operations.
You cannot read medical records or billing data.
"""

TOOL_NAMES: list[str] = [
    "check_drug_interactions",
    "write_prescription",
]
