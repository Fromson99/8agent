"""Freeze verified successful structures for an explicitly scoped follow-up run.

This changes the follow-up's scope, never the original run's completion state.
No RAW discovery, parsing, model calls, or active pointer changes occur here.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile

from semantic_runtime.contracts import digest, sha, write
from . import genos_stages, genos_status


@contextmanager
def run_lock(directory):
    path = genos_stages.plain_path(Path(directory) / 'run.lock')
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Structure run is busy; wait for it to finish') from exc
        yield


def verify_origin(directory, selection):
    """Validate the immutable local snapshots; the parent may later be retried."""
    directory = Path(directory)
    expected = selection.get('origin_sha256')
    origin_path = genos_stages.plain_path(directory / 'selection-origin.json')
    if not expected:
        if origin_path.exists():
            raise ValueError('Structure selection lost its origin binding')
        return {}
    if sha(origin_path) != expected:
        raise ValueError('Structure selection origin changed')
    origin = json.loads(origin_path.read_text())
    if origin.get('schema_version') != 'structure-selection-origin-v1':
        raise ValueError('Unsupported structure selection origin')
    pins = {str(origin_path): expected}
    for name, field in [('parent-selection.json', 'parent_selection_sha256'),
                        ('parent-status.json', 'parent_status_sha256')]:
        path = genos_stages.plain_path(directory / name)
        if sha(path) != origin[field]:
            raise ValueError('Structure selection snapshot changed: ' + name)
        pins[str(path)] = origin[field]
    parent = json.loads((directory / 'parent-selection.json').read_text())
    if (selection['documents'] != parent['documents'] or
            sorted(selection['documents']) != origin['selected_document_ids']):
        raise ValueError('Structure selection differs from verified parent successes')
    return pins


def select_completed(data, parent_run, run_id, *, allow_incomplete=False, reason=''):
    """Select all and only PASSED structures, preserving excluded rows and errors."""
    for value in (parent_run, run_id):
        genos_status.validate_run_id(value)
    if parent_run == run_id:
        raise ValueError('Use a new run ID; the original structure run is immutable here')
    data = genos_stages.plain_path(data).resolve()
    parent_dir = genos_stages.plain_path(data / 'LOGS' / parent_run)
    destination = genos_stages.plain_path(data / 'LOGS' / run_id)
    if not parent_dir.is_dir():
        raise ValueError('Structure run does not exist: ' + parent_run)
    with run_lock(parent_dir):
        path = genos_stages.plain_path(parent_dir / 'structure-selection.json')
        selection_bytes = path.read_bytes()
        selection = json.loads(selection_bytes)
        report = genos_status.read_report(parent_dir)
        if (not report['recorded'] or report['attempt']['stage'] not in {'structure', 'all'} or
                report['attempt']['status'] not in {'COMPLETED', 'FAILED', 'COMPLETED_WITH_FAILURES'}):
            raise ValueError('A finished structure run and its document ledger are required')
        if report['attempt'].get('error'):
            raise ValueError('Run-level error must be resolved before selecting successes')
        if selection.get('schema_version') != 'structure-selection-v1' or not selection.get('documents'):
            raise ValueError('No completed structures to select')
        selected = [row for row in report['documents'] if row['selection'] == 'SELECTED']
        expected = {row['document_id'] for row in selected}
        from .retry_adoption import reconcile
        successes, retry_evidence = reconcile(data, parent_dir, selection, report)
        if (expected != set(selection.get('expected_document_ids', [])) or
                successes != set(selection['documents'])):
            raise ValueError('Structure selection and latest status ledger disagree')
        omitted = [row for row in report['documents'] if row['selection'] == 'INPUT_FAILED' or
                   (row['selection'] == 'SELECTED' and row['document_id'] not in successes)]
        if any(row['phases']['structure']['state'] != 'FAILED' for row in selected
               if row['document_id'] not in successes):
            raise ValueError('Unfinished documents must finish before selecting successes')
        if bool(omitted) != (selection.get('completed') is not True or
                             selection.get('input_inventory_valid', True) is not True):
            raise ValueError('Structure completion flags and ledger disagree')
        if omitted and (not allow_incomplete or not reason.strip()):
            raise ValueError('Excluded failures require --allow-incomplete and --reason')
        origin = {
            'schema_version': 'structure-selection-origin-v1', 'parent_run_id': parent_run,
            'parent_attempt_id': report['attempt']['id'], 'parent_selection_sha256': sha(path),
            'selected_document_ids': sorted(successes), 'parent_selected_count': len(expected),
            'verified_retry_adoptions': retry_evidence,
            'omitted_count': len(omitted), 'omitted_documents': omitted,
            'coverage': 'PARTIAL' if omitted else 'COMPLETE',
            'reason': genos_status.safe(reason.strip()), 'allow_incomplete': allow_incomplete,
            'activated': False,
        }
        # Validate every receipt and source DB through the same release consumer.
        # Only the copied subset has completed=true; the parent's flags stay intact.
        temp = Path(tempfile.mkdtemp(prefix='.selection-', dir=destination.parent))
        try:
            os.chmod(temp, 0o700)
            (temp / 'parent-selection.json').write_bytes(selection_bytes)
            write(temp / 'parent-status.json', report)
            origin['parent_status_sha256'] = sha(temp / 'parent-status.json')
            write(temp / 'selection-origin.json', origin)
            subset = {
                'schema_version': 'structure-selection-v1', 'inputs_sha256': digest(origin),
                'completed': True, 'input_inventory_valid': True,
                'expected_document_ids': sorted(successes), 'documents': selection['documents'],
                'origin_sha256': sha(temp / 'selection-origin.json'),
            }
            write(temp / 'structure-selection.json', subset)
            from .document_release import verified_structures
            verified_structures(data, subset)
            if path.read_bytes() != selection_bytes:
                raise ValueError('Parent selection changed during snapshot')
            if destination.exists():
                # A repeated identical selection is read-only; never replace another run.
                for name in ('structure-selection.json', 'selection-origin.json',
                             'parent-selection.json', 'parent-status.json'):
                    existing = genos_stages.plain_path(destination / name)
                    if not existing.is_file() or sha(existing) != sha(temp / name):
                        raise ValueError('Destination run exists with different inputs; use a new run ID')
            else:
                os.rename(temp, destination)
            return {'completed': True, 'stage': 'select', 'run_id': run_id,
                    'selected': len(successes), 'omitted': len(omitted), 'coverage': origin['coverage'],
                    'path': str(destination), 'activated': False}
        finally:
            if temp.exists():
                shutil.rmtree(temp)
