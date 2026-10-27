"""Collect and evaluate completed cells sequentially, without product replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from common import ROOT, ART, read, save, sha
from run_case import load_frozen, process_lock, cell_directory, require
from run_matrix import finished


def run_script(name, arguments, log):
    require(not log.exists(), 'existing evaluation log; inspect partial work before continuing')
    with log.open('x', encoding='utf-8') as stream:
        result = subprocess.run([str(ROOT / '.venv/bin/python'), '-B',
            str(Path(__file__).with_name(name)), *arguments], cwd=ROOT,
            stdout=stream, stderr=subprocess.STDOUT)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-only', action='store_true')
    args = parser.parse_args()
    frozen, _, cases, *_ = load_frozen()
    freeze_hash = sha(ART / 'design-freeze.json')
    for name, expected in frozen['evaluation_scripts'].items():
        require(sha(ROOT / name) == expected, 'evaluation script drift')
    complete = all(finished(row, freeze_hash) for row in frozen['execution_order'])
    require(complete, 'all product cells must finish before offline evaluation')
    if args.inspect_only:
        print(json.dumps({'product_cells': 111, 'evaluation_cases': len(cases), 'live_model_calls': 0}))
        return 0
    stop_path = ART / 'evaluation-stop.json'
    require(not stop_path.exists(), 'offline evaluation has a sticky stop')
    receipt_path = ART / 'evaluation-case-receipts.json'
    receipts = read(receipt_path) if receipt_path.exists() else {'design_freeze_sha256': freeze_hash,
        'metrics': {}, 'judge': {}}
    require(receipts['design_freeze_sha256'] == freeze_hash, 'evaluation receipts use another freeze')
    # Share the product guard lock: no evaluator can overlap a product process.
    with process_lock('.matrix-runner.lock'), process_lock('.matrix-case.lock'):
        for row in frozen['execution_order']:
            directory = cell_directory(row)
            output = directory / 'metrics.json'
            if not output.exists():
                code = run_script('collect_metrics.py', ['--case', row['case_id'], '--arm', row['arm'],
                    '--out', str(directory)], directory / 'metrics.log')
                if code:
                    save(stop_path, {'kind': 'METRICS_FAILURE', 'cell': row, 'exit_code': code})
                    return 2
                outputs = [directory / name for name in ('metrics.json', 'evidence-audit.json',
                    'judge-source-packets.json', 'ontology-audit.json', 'retrieval-ledger-case.json')]
                receipts['metrics'][str(row['ordinal'])] = {str(p.relative_to(ROOT)): sha(p) for p in outputs}
                save(receipt_path, receipts)
            expected = receipts['metrics'].get(str(row['ordinal']))
            require(expected is not None, 'metrics lack completion receipt; inspect partial work')
            require(all(sha(ROOT / p) == h for p, h in expected.items()), 'completed metric output changed')
            metrics = read(output)
            integrity = metrics['source_integrity']
            if integrity['mismatch_count'] or integrity['failures']:
                save(stop_path, {'kind': 'SOURCE_OR_RECORD_INTEGRITY_FAILURE', 'cell': row,
                    'metrics_path': str(output.relative_to(ROOT))})
                return 2
        evaluation = ART / 'evaluation'
        evaluation.mkdir(exist_ok=True)
        for case_id in cases:
            output = evaluation / case_id / 'result.json'
            if output.exists():
                require(read(output)['status'] != 'PROVIDER_STOP', 'previous judge provider stop')
                expected = receipts['judge'].get(case_id)
                require(expected is not None, 'judge lacks completion receipt; inspect partial work')
                require(all(sha(ROOT / p) == h for p, h in expected.items()), 'completed judge output changed')
                for item in read(output.parent / 'plan.json')['input_files']:
                    require(sha(ROOT / item['path']) == item['sha256'], 'judge input changed after evaluation')
                continue
            code = run_script('judge.py', ['--case', case_id, '--execute'], evaluation / (case_id + '.log'))
            if code or not output.exists():
                save(stop_path, {'kind': 'JUDGE_STOP', 'case_id': case_id, 'exit_code': code})
                return 2
            outputs = [output, output.parent / 'plan.json', output.parent / 'relevance-judgments.json']
            receipts['judge'][case_id] = {str(p.relative_to(ROOT)): sha(p) for p in outputs}
            save(receipt_path, receipts)
            status = read(output)['status']
            print(json.dumps({'case_id': case_id, 'status': status}, ensure_ascii=False), flush=True)
        save(ART / 'evaluation-progress.json', {'completed_cases': 37, 'total_cases': 37,
            'all_attempts_finished': True, 'design_freeze_sha256': freeze_hash,
            'semantic_unknowns_preserved': True})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
