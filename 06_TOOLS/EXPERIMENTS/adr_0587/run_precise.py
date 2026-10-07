"""Question-only retest of ADR-0585's frozen Qwen unit-expansion runner."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0587-equity-definition-unambiguous-probe'
PARENT_RUNNER = ROOT / '06_TOOLS/EXPERIMENTS/adr_0585/run_real.py'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ADR / '실험/manifest.json').read_text())
    if manifest['design']['criteria_frozen_before_run'] is not True:
        raise ValueError('design must be frozen before run')
    import hashlib
    for relative, expected in manifest['design']['frozen_inputs'].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('frozen input drift: ' + relative)
    spec = importlib.util.spec_from_file_location('adr_0585_frozen_runner', PARENT_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ADR = ADR
    case = json.loads((ADR / 'artifacts/design/cases.json').read_text())['cases'][0]
    result = module.run_case(case, preflight=args.preflight)
    print(json.dumps({key: result.get(key) for key in (
        'case_id', 'question', 'initial_unit_id', 'first_read_chars',
        'expansion_request', 'expansion_receipt', 'answer', 'model_calls',
        'seconds', 'error')}, ensure_ascii=False))
    if result['error']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
