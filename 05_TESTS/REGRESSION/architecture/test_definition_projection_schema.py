from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "00_SYSTEM/SCHEMAS/definition-projection-v1.schema.json"
EXAMPLE_PATH = ROOT / "01_DATA/CONTRACTS/definition-projection-v1.example.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_definition_projection_example_satisfies_machine_contract():
    _validator().validate(_example())


def test_ready_projection_requires_verified_completeness_receipt():
    value = _example()
    value["completeness"]["verification_receipt_sha256"] = None

    assert list(_validator().iter_errors(value))


def test_restricted_projection_cannot_be_exportable():
    value = _example()
    value["security"] = {
        "security_class": "restricted",
        "export_allowed": True,
    }

    assert list(_validator().iter_errors(value))


def test_non_exists_condition_requires_a_comparison_value():
    value = copy.deepcopy(_example())
    del value["decision_contract"]["necessary_conditions"][0]["value"]

    assert list(_validator().iter_errors(value))
