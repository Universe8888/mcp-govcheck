"""Tests for the canonical control catalog."""

import pytest

from mcp_govcheck import controls
from mcp_govcheck.types import Control


def test_catalog_is_nonempty_and_well_formed():
    assert controls.CATALOG
    for ref, ctrl in controls.CATALOG.items():
        assert isinstance(ctrl, Control)
        assert ctrl.ref == ref  # key matches the control's own ref
        assert ctrl.framework in {"ISO27001", "SOC2"}
        assert ctrl.title  # no empty titles


def test_refs_are_unique():
    refs = list(controls.CATALOG)
    assert len(refs) == len(set(refs))


def test_get_control_known():
    c = controls.get_control("ISO27001:A.8.2")
    assert c.framework == "ISO27001"
    assert c.title == "Privileged access rights"


def test_get_control_unknown_raises_with_helpful_message():
    with pytest.raises(KeyError) as exc:
        controls.get_control("ISO27001:A.99.99")
    assert "Unknown control ref" in str(exc.value)


def test_is_known():
    assert controls.is_known("SOC2:CC6.3")
    assert not controls.is_known("SOC2:NOPE")


def test_validate_refs_returns_only_unknown():
    bad = controls.validate_refs(["ISO27001:A.8.2", "SOC2:CC6.1", "MADE:UP"])
    assert bad == ["MADE:UP"]


def test_validate_refs_all_valid_is_empty():
    assert controls.validate_refs(["ISO27001:A.8.2", "SOC2:CC6.1"]) == []
