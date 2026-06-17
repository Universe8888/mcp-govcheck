"""Canonical governance-control catalog.

Single source of truth for every control id used in rubrics and evidence.
Rubric checks reference controls by `ref` (e.g. "ISO27001:A.8.2"); this module
is the ONLY place those ids and their titles are defined. Never inline a
control id or title elsewhere — import and resolve it here.

Scope (v1): the ISO 27001:2022 Annex A and SOC 2 Common Criteria controls that
are relevant to governing an autonomous agent's tool surface (access control,
least privilege, change/approval, logging). This is deliberately a curated
subset, not the full standards.
"""

from __future__ import annotations

from .types import Control

# --- ISO 27001:2022 Annex A (curated subset) -------------------------------
_ISO27001 = [
    Control("ISO27001:A.5.15", "ISO27001", "Access control"),
    Control("ISO27001:A.5.18", "ISO27001", "Access rights"),
    Control("ISO27001:A.8.2", "ISO27001", "Privileged access rights"),
    Control("ISO27001:A.8.3", "ISO27001", "Information access restriction"),
    Control("ISO27001:A.8.15", "ISO27001", "Logging"),
    Control("ISO27001:A.8.16", "ISO27001", "Monitoring activities"),
    Control("ISO27001:A.8.32", "ISO27001", "Change management"),
]

# --- SOC 2 Common Criteria (curated subset) --------------------------------
_SOC2 = [
    Control("SOC2:CC6.1", "SOC2", "Logical access security controls"),
    Control("SOC2:CC6.3", "SOC2", "Least-privilege access management"),
    Control("SOC2:CC7.2", "SOC2", "Monitoring of security events"),
    Control("SOC2:CC8.1", "SOC2", "Change management authorization"),
]

CATALOG: dict[str, Control] = {c.ref: c for c in (*_ISO27001, *_SOC2)}


def get_control(ref: str) -> Control:
    """Resolve a control id to its `Control`. Raises KeyError if unknown."""
    try:
        return CATALOG[ref]
    except KeyError as exc:
        raise KeyError(
            f"Unknown control ref {ref!r}. Known refs: {sorted(CATALOG)}"
        ) from exc


def is_known(ref: str) -> bool:
    return ref in CATALOG


def validate_refs(refs: list[str]) -> list[str]:
    """Return the subset of `refs` that are NOT in the catalog (empty == all valid)."""
    return [r for r in refs if r not in CATALOG]
