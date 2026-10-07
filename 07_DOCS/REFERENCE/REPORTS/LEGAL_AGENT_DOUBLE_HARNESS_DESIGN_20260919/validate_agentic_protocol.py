"""Validate the proposed control shape only; not a runtime or quality test."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

base = Path(__file__).resolve().parent
schema = json.loads((base / "AGENTIC_CONTROL.schema.json").read_text())
examples = json.loads((base / "agentic-control-examples.json").read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)
checks = []
for expected, name in ((True, "valid"), (False, "invalid")):
    for number, value in enumerate(examples[name], 1):
        accepted = not list(validator.iter_errors(value))
        checks.append({"case": f"{name}_{number}", "passed": accepted == expected})
print(json.dumps({"scope": "synthetic JSON shape only", "checks": checks}, indent=2))
assert all(check["passed"] for check in checks)
