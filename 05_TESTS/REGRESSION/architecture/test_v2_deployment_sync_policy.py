import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REMOVED = ("01_DATA/corpus", "01_DATA/structure", "01_DATA/frames", "01_DATA/rag")


def test_deployment_sync_uses_sourceset_release_contract() -> None:
    config_root = ROOT / "08_DEPLOYMENT/CONFIG/dataset_sync"
    profile_path = config_root / "profiles.json"
    profile = json.loads(profile_path.read_text("utf-8"))

    assert profile["schema_version"] == "sourceset-release-sync-v2"
    assert profile["legacy_overlay_sync_allowed"] is False
    assert set(profile["targets"]) == {"local", "onsite", "genos"}
    assert not list(config_root.glob("*overlay*.json"))
    text = profile_path.read_text("utf-8")
    assert not any(value in text for value in REMOVED)


def test_v2_cutover_validator_reads_the_active_release() -> None:
    validator = ROOT / "06_TOOLS/MIGRATION/validate_v2_cutover.py"
    text = validator.read_text("utf-8")
    assert "active_runtime_paths" in text
    assert not any(value in text for value in REMOVED)
