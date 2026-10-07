"""Bind completed evidence without replaying product calls or changing frozen code."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0624-required-unit-delegation-read'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    manifest = json.loads((ADR / '실험/manifest.json').read_text())
    mismatches = []
    checked = 0
    for name, expected in manifest['design']['frozen_inputs'].items():
        checked += 1
        if sha(ROOT / name) != expected:
            mismatches.append({'path': name, 'kind': 'frozen_input_drift'})
    for candidate in manifest['design']['code_isolation']['candidates']:
        path = ROOT / candidate['manifest_path']
        data = json.loads(path.read_text())
        if sha(path) != candidate['manifest_sha256']:
            mismatches.append({'path': candidate['manifest_path'], 'kind': 'candidate_manifest_drift'})
        revision = next(r for r in data['revisions'] if r['revision_id'] == candidate['revision_id'])
        if revision['revision_sha256'] != candidate['revision_sha256']:
            mismatches.append({'path': candidate['manifest_path'], 'kind': 'revision_drift'})
        for item in revision['files']:
            checked += 1
            if sha(ROOT / item['frozen_path']) != item['snapshot_sha256']:
                mismatches.append({'path': item['frozen_path'], 'kind': 'frozen_code_drift'})
    binding = json.loads((ADR / 'artifacts/design/source-binding.json').read_text())
    generation = ROOT / binding['generation']
    index = json.loads((ROOT / manifest['design']['index_reuse']['manifest']).read_text())
    original_store_unchanged = sha(generation / 'store.sqlite') == index['source_store_sha256']
    if not original_store_unchanged:
        mismatches.append({'path': str(generation / 'store.sqlite'), 'kind': 'source_store_drift'})
    active = '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    main_unchanged = sha(ROOT / active) == manifest['design']['frozen_inputs'][active]
    receipt = {
        'schema_version': 'unit-fulltext-preservation-receipt-v1',
        'adr_id': manifest['adr_id'], 'created_at': datetime.now(timezone.utc).isoformat(),
        'frozen_files_checked': checked, 'mismatches': mismatches,
        'main_unchanged': main_unchanged, 'original_store_unchanged': original_store_unchanged,
        'genos_deployed': False, 'product_calls_replayed': False,
    }
    (ADR / 'artifacts/preservation-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    files = set()
    roots = [ADR, ROOT / '06_TOOLS/EXPERIMENTS/adr_0624']
    roots += [(ROOT / c['manifest_path']).parent for c in manifest['design']['code_isolation']['candidates']]
    for directory in roots:
        for path in directory.rglob('*'):
            # The scoped graph has directory links to ancestor ADRs. Inventory only
            # this run's evidence, including its generated scoped graph files.
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT):
                continue
            if not path.is_file() or '__pycache__' in path.parts or path == ADR / 'artifacts/manifest.json':
                continue
            files.add(path)
    files.add(ROOT / '05_TESTS/CONTRACTS/test_unit_fulltext_adaptive_read.py')
    files.add(ROOT / '05_TESTS/CONTRACTS/test_batch_reference_navigation.py')
    files.add(ROOT / '05_TESTS/CONTRACTS/test_compact_reference_menu_repair.py')
    files.add(ROOT / '05_TESTS/CONTRACTS/test_required_unit_delegation_read.py')
    rows = []
    for path in sorted(files):
        raw = path.name.startswith(('model-input-', 'model-output-')) or 'provider' in path.parts or path.name.startswith('질문-')
        rows.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path),
                     'bytes': path.stat().st_size,
                     'description': 'Frozen code, raw source/model record, measured result, diagnostic receipt or research metadata',
                     'contains_raw_prompts_and_outputs': raw})
    inventory = {'schema_version': 'adr-artifacts-v1', 'adr_id': manifest['adr_id'], 'files': rows}
    (ADR / 'artifacts/manifest.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'files': len(rows), **receipt}, ensure_ascii=False))
    if mismatches or not main_unchanged:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
