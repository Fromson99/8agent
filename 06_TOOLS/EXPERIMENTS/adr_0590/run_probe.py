"""Hash-checked entry point for the frozen ADR-0590 mechanical probe."""
import hashlib
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "04_EXPERIMENTS/ADR/ADR-0590-journal-chain-resume/artifacts/design/run_probe.py"
EXPECTED_SHA256 = "b718cdc29e10dec551759893f34aa44f685397e822beb1e27fa0200debaa2db2"
if hashlib.sha256(RUNNER.read_bytes()).hexdigest() != EXPECTED_SHA256:
    raise RuntimeError("frozen runner hash mismatch")
runpy.run_path(str(RUNNER), run_name="__main__")
