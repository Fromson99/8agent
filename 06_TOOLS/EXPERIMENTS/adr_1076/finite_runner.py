"""Owner-facing finite census adapter; invoke only after ADR1076 freeze."""
from pathlib import Path
import gzip
import importlib.util
import json
import traceback


def run(baseline_root: Path, candidate_root: Path, matrix: dict, output: Path) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('_adr1076_independent_contract',
        Path(__file__).with_name('finite_contract.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = output / 'finite-pairs.jsonl.gz'
    count = 0
    # x preserves an interrupted/failed prior invocation, including partial gzip.
    with gzip.open(raw, 'xt', encoding='utf-8') as stream:
        def emit(row):
            nonlocal count
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            if 'case' in row: count += 1
        try:
            result = module.run_matrix(baseline_root, candidate_root, emit, matrix)
            result.update(raw_path=str(raw), recorded_pairs=count)
            emit({'summary': result})
        except BaseException as exc:
            result = {'status': 'FAIL', 'recorded_pairs': count, 'raw_path': str(raw),
                      'error_type': type(exc).__name__, 'error': str(exc),
                      'traceback': traceback.format_exc()}
            emit({'failure': result})
            with (output / 'finite-first-failure.json').open('x', encoding='utf-8') as out:
                json.dump(result, out, ensure_ascii=False, indent=2); out.write('\n')
            raise
    return result
