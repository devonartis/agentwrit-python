"""Patient data loader — reads mock patients from patients.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent
_patients_cache: list[dict[str, Any]] | None = None
_formulary_cache: dict[str, Any] | None = None


def _load_patients() -> list[dict[str, Any]]:
    global _patients_cache
    if _patients_cache is None:
        with open(_DATA_DIR / "patients.json") as f:
            _patients_cache = json.load(f)
    return _patients_cache


def _load_formulary() -> dict[str, Any]:
    global _formulary_cache
    if _formulary_cache is None:
        with open(_DATA_DIR / "formulary.json") as f:
            _formulary_cache = json.load(f)
    return _formulary_cache


def list_patients() -> list[dict[str, str]]:
    """Return a summary list: [{patient_id, name, dob}, ...]."""
    return [
        {"patient_id": p["patient_id"], "name": p["name"], "dob": p["dob"]}
        for p in _load_patients()
    ]


def get_patient(patient_id: str) -> dict[str, Any] | None:
    """Return full patient record by ID, or None."""
    for p in _load_patients():
        if p["patient_id"] == patient_id:
            return p
    return None


def get_medical_records(patient_id: str) -> list[dict[str, Any]]:
    patient = get_patient(patient_id)
    if not patient:
        return []
    return patient.get("medical_records", [])


def get_lab_results(patient_id: str) -> list[dict[str, Any]]:
    patient = get_patient(patient_id)
    if not patient:
        return []
    return patient.get("labs", [])


def get_prescriptions(patient_id: str) -> list[dict[str, Any]]:
    patient = get_patient(patient_id)
    if not patient:
        return []
    return patient.get("prescriptions", [])


def get_billing_history(patient_id: str) -> list[dict[str, Any]]:
    patient = get_patient(patient_id)
    if not patient:
        return []
    return patient.get("billing", [])


def get_insurance_info(patient_id: str) -> dict[str, Any] | None:
    patient = get_patient(patient_id)
    if not patient:
        return None
    return patient.get("insurance")


def get_demographics(patient_id: str) -> dict[str, Any] | None:
    patient = get_patient(patient_id)
    if not patient:
        return None
    return patient.get("demographics")


def get_formulary() -> dict[str, Any]:
    return _load_formulary()


def check_drug_interactions(
    new_drug: str, current_drugs: list[str]
) -> list[dict[str, Any]]:
    """Check a new drug against current medications for interactions."""
    formulary = _load_formulary()
    interactions: list[dict[str, Any]] = []
    for drug_entry in formulary.get("drugs", []):
        if drug_entry["name"].lower() == new_drug.lower():
            for interaction in drug_entry.get("interactions", []):
                if any(
                    interaction["drug"].lower() in d.lower()
                    or d.lower() in interaction["drug"].lower()
                    for d in current_drugs
                ):
                    interactions.append({
                        "new_drug": new_drug,
                        "existing_drug": interaction["drug"],
                        "severity": interaction["severity"],
                        "note": interaction["note"],
                    })
    return interactions
