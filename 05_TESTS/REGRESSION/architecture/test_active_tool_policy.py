import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REMOVED = ("01_DATA/corpus", "01_DATA/structure", "01_DATA/frames", "01_DATA/rag")


def test_active_tool_policy_is_deny_by_default() -> None:
    policy = json.loads((ROOT / "06_TOOLS/ACTIVE_TOOLS.json").read_text("utf-8"))
    assert policy["schema_version"] == "active-tools-v1"
    assert policy["policy"] == "deny-by-default"
    assert len(policy["tools"]) == len(set(policy["tools"]))
    assert "dataset_sync.py" not in policy["tools"]
    assert "data_ship.sh" not in policy["tools"]
    for name in policy["tools"]:
        tool = ROOT / "06_TOOLS/COMMANDS" / name
        assert tool.is_file()
        assert not any(value in tool.read_text("utf-8") for value in REMOVED)
