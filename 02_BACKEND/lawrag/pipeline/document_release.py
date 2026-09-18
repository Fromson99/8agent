"""Join selected document builds, review existing and new definitions, and prepare a serving DRAFT.

No implicit base discovery or activation. GENOS pointer changes require explicit
confirmation and compare-and-swap; completed generations are never rewritten.
"""
import argparse
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid

from semantic_runtime.contracts import sha, digest, write
from semantic_runtime.storage import Store, TABLES
from . import glossary_linking, glossary_review, glossary_document_update
from . import genos_stages
from .term_generation import build_generation
from .term_serving_bundle import verify_assets


def merge_sources(sources, output, *, exclude=()):
    sources = [genos_stages.plain_path(p).resolve() for p in sources]
    output = Path(output)
    identity = {'sources': [{'path': str(p), 'sha256': sha(p)} for p in sources],
                'exclude_document_ids': sorted(set(exclude)), 'compiler_sha256': sha(__file__)}
    if output.exists():
        receipt = json.loads((output / 'selection.json').read_text())
        if receipt['identity'] != identity or receipt['store_sha256'] != sha(output / 'store.sqlite'):
            raise ValueError('Integrated source selection changed; use a new run ID')
        return output / 'store.sqlite'
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.' + output.name, dir=output.parent))
    try:
        seen, excluded = {}, set()
        with closing(sqlite3.connect(temp / 'store.sqlite')) as db:
            db.executescript('''
              CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);
              CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT,PRIMARY KEY(document_id,unit_id));
              CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,PRIMARY KEY(document_id,block_id));
            ''')
            for path in sources:
                with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
                    for doc in source.execute('SELECT * FROM document ORDER BY document_id'):
                        did = doc[0]
                        if did in exclude:
                            excluded.add(did); continue
                        rows = {'document': [doc]}
                        for table, order in [('source_unit', 'unit_id'), ('source_block', 'block_id')]:
                            rows[table] = source.execute(f'SELECT * FROM {table} WHERE document_id=? ORDER BY {order}', (did,)).fetchall()
                        fingerprint = digest(rows)
                        if did in seen:
                            if seen[did] != fingerprint:
                                raise ValueError('Conflicting document version ID: ' + did)
                            continue
                        seen[did] = fingerprint
                        for table in TABLES:
                            if rows[table]:
                                db.executemany(f'INSERT INTO {table} VALUES (' + ','.join('?' * len(rows[table][0])) + ')', rows[table])
            if set(exclude) != excluded:
                raise ValueError('Excluded document is not in the explicit selection')
            if not seen:
                raise ValueError('Empty integrated source selection')
            db.commit()
        for item in identity['sources']:
            if sha(item['path']) != item['sha256']:
                raise ValueError('Source changed during integration')
        write(temp / 'selection.json', {'identity': identity, 'document_ids': sorted(seen),
                                       'document_hashes': seen, 'store_sha256': sha(temp / 'store.sqlite')})
        os.rename(temp, output)
        return output / 'store.sqlite'
    except BaseException:
        shutil.rmtree(temp)
        raise


def selected_sources(data, run_id, bases):
    path = data / 'LOGS' / run_id / 'structure-selection.json'
    selection = json.loads(path.read_text())
    if selection.get('schema_version') != 'structure-selection-v1' or not selection['documents']:
        raise ValueError('Completed structure selection is required')
    if (selection.get('completed') is not True or selection.get('input_inventory_valid', True) is not True
            or set(selection.get('expected_document_ids', [])) != set(selection['documents'])):
        raise ValueError('Structure selection is incomplete; rerun structure before release')
    paths, pins = [], {str(path): sha(path)}
    for base in bases:
        base = genos_stages.plain_path(base).resolve()
        with closing(Store(base)):
            pass
        pins[str(base / 'manifest.json')] = sha(base / 'manifest.json')
        paths.append(base / 'store.sqlite')
    for did, value in sorted(selection['documents'].items()):
        if not re.fullmatch(r'[0-9a-f]{64}', value['key']):
            raise ValueError('Invalid structure selection key')
        folder = data / 'STRUCTURE' / value['key']
        receipt = folder / 'structure-receipt.json'
        if sha(receipt) != value['receipt_sha256']:
            raise ValueError('Selected structure receipt changed')
        genos_stages.verify_structure(folder)
        with closing(sqlite3.connect((folder / 'source.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
            if {r[0] for r in db.execute('SELECT document_id FROM document')} != {did}:
                raise ValueError('Structure selection document mismatch')
        paths.append(folder / 'source.sqlite')
        pins[str(receipt)] = sha(receipt)
    return paths, pins


def build(data, run_id, glossary, *, bases=(), exclude=(), max_jobs=100, retry_failed=False,
          prepare_only=False, provider=None):
    data = genos_stages.plain_path(data).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', run_id):
        raise ValueError('Invalid run ID')
    sources, pins = selected_sources(data, run_id, bases)
    destination = data / 'TERM_RELEASES' / run_id
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from . import glossary_assembly
        identity = {'pins': pins, 'glossary_sha256': glossary_assembly.inspect(glossary)['dictionary_sha256'],
                    'exclude': sorted(set(exclude)), 'compiler_sha256': sha(__file__)}
        plan = destination / 'plan.json'
        if plan.exists() and json.loads(plan.read_text()) != identity:
            raise ValueError('Release inputs changed; use a new run ID')
        if not plan.exists():
            write(plan, identity)
        source = merge_sources(sources, destination / 'sources', exclude=exclude)
        glossary_document_update.augment(glossary, source, destination / 'glossary-draft')
        state, reviewed = destination / 'review', destination / 'glossary-reviewed'
        if not state.exists():
            glossary_review.prepare(destination / 'glossary-draft', state)
        if prepare_only:
            return {'completed': False, 'status': 'PREPARED', 'review': glossary_review.inspect(state), 'path': str(destination)}
        review = glossary_review.complete(destination / 'glossary-draft', state, reviewed,
                                         max_jobs=max_jobs, retry_failed=retry_failed, provider=provider)
        if not review['completed']:
            return {'completed': False, 'status': 'REVIEW_PENDING', 'review': review, 'path': str(destination)}
        selection_path = destination / 'sources/selection.json'
        selection = json.loads(selection_path.read_text())
        scope = {'document_version_ids': selection['document_ids'], 'source_selection_sha256': sha(selection_path)}
        result = build_generation(source, reviewed, destination / 'serving', serving=True, scope=scope)
        generation = destination / 'serving/generation'
        validation = verify_assets(generation)
        for path, expected in pins.items():
            if sha(path) != expected:
                raise ValueError('Release input changed during preparation')
        receipt = {'schema_version': 'document-release-v1', 'completed': True, 'activated': False,
                   'quality_certified': False, 'generation': 'serving/generation', 'review_status': review['review_status'],
                   'review_completion_sha256': sha(state / 'completion.json'),
                   'plan_sha256': sha(plan), 'reviewed_report_sha256': sha(reviewed / 'report.json'),
                   'source_selection_sha256': sha(selection_path), 'source_store_sha256': sha(source),
                   'result_sha256': sha(destination / 'serving/result.json'),
                   'manifest_sha256': validation['manifest_sha256'], 'counts': result['counts']}
        target = destination / 'release.json'
        if target.exists() and json.loads(target.read_text()) != receipt:
            raise ValueError('Completed release receipt changed')
        if not target.exists():
            write(target, receipt)
        return {**receipt, 'path': str(destination), 'generation_path': str(generation)}


def verify_glossary(path):
    from . import glossary_assembly
    path = Path(path).resolve()
    report = glossary_assembly.inspect(path)
    review = report.get('llm_review', {})
    state = Path(review.get('state', ''))
    receipt_path = state / 'completion.json'
    if not receipt_path.is_file():
        raise ValueError('Explicit glossary needs a completed review receipt')
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('completed') is not True or receipt['dictionary_sha256'] != report['dictionary_sha256']
            or receipt['state_sha256'] != sha(state / 'review.sqlite')
            or review.get('state_sha256') != receipt['state_sha256']
            or (state / receipt['output_relative_to_state']).resolve() != path):
        raise ValueError('Completed glossary receipt mismatch')
    glossary_linking.binding(path)
    return {'verified': True, 'dictionary_sha256': report['dictionary_sha256'],
            'review_status': receipt['review_status']}


def verify_release(path):
    path = genos_stages.plain_path(path).resolve()
    receipt = json.loads((path / 'release.json').read_text())
    if receipt.get('schema_version') != 'document-release-v1' or not receipt.get('completed'):
        raise ValueError('Incomplete document release')
    for file, field in [('plan.json', 'plan_sha256'), ('serving/result.json', 'result_sha256'),
                        ('review/completion.json', 'review_completion_sha256'),
                        ('glossary-reviewed/report.json', 'reviewed_report_sha256'),
                        ('sources/selection.json', 'source_selection_sha256'), ('sources/store.sqlite', 'source_store_sha256')]:
        if sha(path / file) != receipt[field]:
            raise ValueError('Release receipt binding mismatch: ' + file)
    review = json.loads((path / 'review/completion.json').read_text())
    if sha(path / 'review/review.sqlite') != review['state_sha256']:
        raise ValueError('Review audit state changed')
    if sha(path / 'glossary-reviewed/dictionary.sqlite') != review['dictionary_sha256']:
        raise ValueError('Reviewed glossary changed')
    generation = (path / receipt['generation']).resolve()
    generation.relative_to(path)
    if verify_assets(generation)['manifest_sha256'] != receipt['manifest_sha256']:
        raise ValueError('Release generation mismatch')
    return generation, receipt


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pointer-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def change_pointer(root, *, release=None, rollback=None, expected_current, confirm=False):
    if not confirm:
        raise ValueError('Activation/rollback requires --confirm-main')
    if bool(release) == bool(rollback):
        raise ValueError('Select exactly one release or rollback receipt')
    root = genos_stages.plain_path(root).resolve()
    pointer = root / 'generations/CURRENT.json'
    pointer.parent.mkdir(parents=True, exist_ok=True)
    with (pointer.parent / '.activation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        actual = sha(pointer) if pointer.exists() else 'absent'
        if actual != expected_current:
            raise ValueError('CURRENT changed; inspect the new selection before activation')
        before = json.loads(pointer.read_text()) if pointer.exists() else None
        if release:
            generation, receipt = verify_release(release)
            generation.relative_to(root)
            manifest = json.loads((generation / 'manifest.json').read_text())
            after = {'schema_version': 'genos-current-generation-v1', 'generation_id': manifest['generation_id'],
                     'path': str(generation), 'manifest_sha256': receipt['manifest_sha256']}
        else:
            history = genos_stages.plain_path(rollback).resolve()
            history.relative_to(pointer.parent / 'receipts')
            event = json.loads(history.read_text())
            if before != event['after']:
                raise ValueError('Rollback receipt does not describe CURRENT')
            after = event['before']
            if after is not None:
                previous = genos_stages.plain_path(after['path']).resolve()
                previous.relative_to(root)
                if sha(previous / 'manifest.json') != after['manifest_sha256']:
                    raise ValueError('Rollback target changed')
                with closing(Store(previous)):
                    pass
        history = pointer.parent / 'receipts' / (uuid.uuid4().hex + '.json')
        event = {'schema_version': 'document-release-activation-v1', 'before': before, 'after': after,
                 'previous_pointer_sha256': actual, 'action': 'APPLY' if release else 'ROLLBACK',
                 'quality_certified': False, 'release': str(release) if release else None}
        _atomic(history, event)
        if after is None:
            pointer.unlink(missing_ok=True)
        else:
            _atomic(pointer, after)
        return {'activated': release is not None, 'action': event['action'], 'receipt': str(history),
                'current_sha256': sha(pointer) if pointer.exists() else 'absent', 'restart_required': True}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'build', 'verify', 'verify-glossary', 'activate', 'rollback'])
    p.add_argument('--run-id'); p.add_argument('--glossary-dir', type=Path)
    p.add_argument('--base-generation', action='append', type=Path, default=[])
    p.add_argument('--exclude-document', action='append', default=[])
    p.add_argument('--max-review-jobs', type=int, default=100)
    p.add_argument('--retry-review-failed', action='store_true')
    p.add_argument('--release', type=Path); p.add_argument('--receipt', type=Path)
    p.add_argument('--active-data-root', type=Path)
    p.add_argument('--expected-current'); p.add_argument('--confirm-main', action='store_true')
    a = p.parse_args(argv)
    if a.action in {'prepare', 'build'}:
        if not a.run_id:
            p.error('--run-id is required')
        from lawrag.platform.paths import repository_root
        root = repository_root(); data = genos_stages.offline_data_root(root)
        glossary = a.glossary_dir or glossary_review.configured_paths()['glossary']
        result = build(data, a.run_id, glossary, bases=a.base_generation, exclude=a.exclude_document,
                       max_jobs=a.max_review_jobs, retry_failed=a.retry_review_failed, prepare_only=a.action == 'prepare')
    elif a.action == 'verify-glossary':
        if not a.glossary_dir: p.error('--glossary-dir is required')
        result = verify_glossary(a.glossary_dir)
    elif a.action == 'verify':
        if not a.release: p.error('--release is required')
        generation, receipt = verify_release(a.release)
        result = {'verified': True, 'generation': str(generation), 'review_status': receipt['review_status']}
    else:
        if not a.active_data_root or not a.expected_current: p.error('--active-data-root and --expected-current are required')
        result = change_pointer(a.active_data_root, release=a.release if a.action == 'activate' else None,
                                rollback=a.receipt if a.action == 'rollback' else None,
                                expected_current=a.expected_current, confirm=a.confirm_main)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if a.action == 'build' and not result['completed'] else 0
