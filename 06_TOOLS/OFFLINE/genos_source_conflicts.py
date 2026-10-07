"""Read-only diagnosis of explicit release source collisions; never select a winner."""
import argparse
from collections import defaultdict
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

from semantic_runtime.contracts import digest, sha


def connect(path):
    db = sqlite3.connect(Path(path).resolve(strict=True).as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    return db


def scan(paths, *, emit=print):
    """Compare the same rows/order as merge_sources, retaining only hashes/counts."""
    paths = list(dict.fromkeys(Path(p).resolve(strict=True) for p in paths))
    pins, documents = {}, defaultdict(list)
    started = time.monotonic()
    for number, path in enumerate(paths, 1):
        pins[str(path)] = sha(path)
        with closing(connect(path)) as db:
            for did, name, artifact in db.execute(
                    'SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY document_id'):
                documents[did].append({'path': str(path), 'name': name,
                                       'source_artifact_sha256': artifact})
        if number == 1 or number % 100 == 0 or number == len(paths):
            emit(f'INPUT {number}/{len(paths)} remaining={len(paths)-number} elapsed={time.monotonic()-started:.1f}s', flush=True)
    duplicates = [(did, rows) for did, rows in sorted(documents.items()) if len(rows) > 1]
    conflicts, identical = [], 0
    for number, (did, entries) in enumerate(duplicates, 1):
        versions = []
        for entry in entries:
            with closing(connect(entry['path'])) as db:
                rows = {'document': db.execute('SELECT * FROM document WHERE document_id=?', (did,)).fetchall()}
                for table, order in [('source_unit', 'unit_id'), ('source_block', 'block_id')]:
                    rows[table] = db.execute(f'SELECT * FROM {table} WHERE document_id=? ORDER BY {order}', (did,)).fetchall()
                versions.append({**entry, 'row_sha256': digest(rows),
                                 'table_sha256': {t: digest(r) for t, r in rows.items()},
                                 'row_counts': {t: len(r) for t, r in rows.items()}})
        if len({v['row_sha256'] for v in versions}) == 1:
            identical += 1
        else:
            raw_hashes = {v['source_artifact_sha256'] for v in versions}
            classification = ('SAME_RAW_DIFFERENT_ROWS' if len(raw_hashes) == 1 and next(iter(raw_hashes))
                              else 'DIFFERENT_OR_MISSING_RAW_HASH')
            conflicts.append({'document_id': did, 'classification': classification, 'versions': versions})
        if number == 1 or number % 25 == 0 or number == len(duplicates):
            emit(f'COMPARE {number}/{len(duplicates)} remaining={len(duplicates)-number} conflicts={len(conflicts)}', flush=True)
    for path, expected in pins.items():
        if sha(path) != expected:
            raise ValueError('Source changed during diagnosis: ' + path)
    return {'schema_version': 'genos-source-conflicts-v1', 'input_pins': pins,
            'source_count': len(paths), 'unique_documents': len(documents),
            'duplicate_ids': len(duplicates), 'identical_duplicates': identical,
            'conflict_count': len(conflicts), 'conflicts': conflicts,
            'mutated_sources': False, 'selected_winner': False, 'model_calls': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--base-generation', action='append', default=[], type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--show', type=int, default=12)
    args = parser.parse_args(argv)
    if args.show < 1:
        parser.error('--show must be positive')
    from lawrag.pipeline.document_release import selected_sources
    data = args.data_root.resolve(strict=True)
    print('VERIFY explicit selected sources; no build, LLM, index or activation', flush=True)
    paths, input_pins = selected_sources(data, args.run_id, args.base_generation)
    plan_path = data / 'TERM_RELEASES' / args.run_id / 'plan.json'
    if plan_path.is_file():
        plan = json.loads(plan_path.read_text())
        if plan['pins'] != input_pins:
            raise ValueError('Diagnostic inputs differ from the failed release plan')
    report = scan(paths)
    for path, expected in input_pins.items():
        if sha(path) != expected:
            raise ValueError('Selection pin changed during diagnosis: ' + path)
    report.update(run_id=args.run_id, selection_pins=input_pins,
                  release_plan_sha256=sha(plan_path) if plan_path.is_file() else None,
                  base_generations=[str(p.resolve()) for p in args.base_generation])
    # Exclusive creation: never replace an earlier diagnostic or release artifact.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f"SUMMARY sources={report['source_count']} documents={report['unique_documents']} "
          f"conflicts={report['conflict_count']} identical={report['identical_duplicates']}", flush=True)
    base_paths = {str(p.resolve() / 'store.sqlite') for p in args.base_generation}
    for number, conflict in enumerate(report['conflicts'][:args.show], 1):
        print(f"\nCONFLICT {number}/{report['conflict_count']} ID={conflict['document_id']} {conflict['classification']}")
        for version in conflict['versions']:
            role = 'BASE' if version['path'] in base_paths else 'SELECTED'
            print(f"  {role} NAME={version['name']}\n  PATH={version['path']}\n"
                  f"  RAW_SHA={version['source_artifact_sha256']}\n  COUNTS={version['row_counts']}\n"
                  f"  ROW_SHA={version['row_sha256']}\n  TABLE_SHA={version['table_sha256']}")
    print(f"\nSAVED={args.output.resolve()} shown={min(args.show, report['conflict_count'])} "
          f"not_shown={max(0,report['conflict_count']-args.show)}", flush=True)
    print('SAME_RAW_DIFFERENT_ROWS means same recorded raw hash, not proof either structure is correct.')
    print('No winner selected. RAW, code, release plans and CURRENT are unchanged.', flush=True)
    return 2 if report['conflict_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
