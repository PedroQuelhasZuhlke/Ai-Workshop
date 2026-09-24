"""Unit tests for `pcbpick.sourcing.suppliers.live_base`'s pure mapping helpers."""

from pcbpick.contracts.enums import ComplianceTag
from pcbpick.sourcing.suppliers.live_base import map_rohs_compliance


def test_positive_rohs_strings_map_to_rohs() -> None:
    for raw in ("RoHS Compliant", "Compliant", "yes", "Y", "true"):
        assert map_rohs_compliance(raw) == [ComplianceTag.ROHS], raw
    assert map_rohs_compliance(True) == [ComplianceTag.ROHS]


def test_negative_rohs_strings_never_map_to_rohs() -> None:
    negatives = (
        "Non-Compliant",
        "Non-RoHS Compliant",
        "Not Compliant",
        "Not RoHS Compliant",
        "non compliant",
        # Concatenated forms with no separator between the negation and "compliant":
        "NonCompliant",
        "noncompliant",
        "NotRohsCompliant",
        "notrohscompliant",
    )
    for raw in negatives:
        assert map_rohs_compliance(raw) == [], raw
    assert map_rohs_compliance(False) == []
    assert map_rohs_compliance(None) == []


def test_unrecognized_rohs_string_is_not_compliant() -> None:
    assert map_rohs_compliance("Unknown") == []
    assert map_rohs_compliance("") == []
