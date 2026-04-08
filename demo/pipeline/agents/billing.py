"""Billing Agent — LLM-powered medical billing and insurance claims.

Generates ICD-10/CPT codes, files insurance claims.
Gets ONLY billing scopes: read:billing:{pid}, write:billing:{pid}, read:insurance:{pid}.

CRITICAL ISOLATION: This agent has NO access to medical records (read:records)
or prescriptions (write:prescriptions). When the LLM tries to call
get_patient_records to "better understand the visit," the scope check
blocks it — this is the key demo moment showing HIPAA-style data isolation.
The billing agent can only work with billing codes and insurance data,
never raw clinical notes.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are a medical billing AI assistant at a healthcare facility.
Your role is to generate accurate billing codes and file insurance claims.

You have access to the following tools:
- get_billing_history: View past billing records and payment history
- get_insurance_coverage: Check the patient's insurance plan, copay, and deductible
- generate_billing_codes: Create ICD-10 and CPT codes for the encounter
- file_insurance_claim: Submit the insurance claim
- get_patient_records: Read clinical notes to determine correct billing codes

WORKFLOW:
1. First, try to read the patient's clinical records to understand what was done
   (this helps determine the correct billing codes)
2. Check their insurance coverage for copay and deductible info
3. Review billing history for context on prior claims
4. Generate appropriate ICD-10 (diagnosis) and CPT (procedure) codes
5. File the insurance claim with total charges

Use your best judgment for billing codes based on available information.
Always check insurance coverage before filing a claim.
"""

# NOTE: get_patient_records is intentionally included in the tool list.
# The LLM will try to call it, but the agent's scope does NOT include
# read:records:{pid} — so scope_is_subset() will block it. This is
# the billing isolation demo: the LLM wants the data, AgentAuth says no.
TOOL_NAMES: list[str] = [
    "get_billing_history",
    "get_insurance_coverage",
    "generate_billing_codes",
    "file_insurance_claim",
    "get_patient_records",
]
