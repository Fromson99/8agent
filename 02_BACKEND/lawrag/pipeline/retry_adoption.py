"""Verify explicit failure-retry adoption without rewriting historical status."""
import json
from semantic_runtime.contracts import digest, sha
from . import genos_stages, genos_status


def reconcile(data, parent_dir, selection, report):
    rows = {r['document_id']: r for r in report['documents'] if r['selection'] == 'SELECTED'}
    expected = set(rows)
    passed = {did for did, r in rows.items() if r['phases']['structure']['state'] == 'PASSED'}
    if expected != set(selection.get('expected_document_ids', [])):
        raise ValueError('Structure selection expected inputs and ledger disagree')
    if set(selection['documents']) == passed and not selection.get('failure_retry'):
        return passed, []
    inventories = {}
    for path in parent_dir.glob('inventory-*.json'):
        files = json.loads(genos_stages.plain_path(path).read_text()).get('files', [])
        mapping = {r['document_id']: r for r in files}
        if set(mapping) == expected:
            inventories[digest(mapping)] = mapping
    if len(inventories) != 1:
        raise ValueError('Retry adoption requires unambiguous original inventory')
    inventory = next(iter(inventories.values()))
    current, evidence, seen = selection, [], set()
    while current.get('failure_retry'):
        binding = current['failure_retry']
        child = binding['run_id']
        genos_status.validate_run_id(child)
        if child in seen or child == parent_dir.name:
            raise ValueError('Retry adoption chain cycle')
        seen.add(child)
        backup = genos_stages.plain_path(parent_dir / ('structure-selection-before-retry-' + child + '.json'))
        # Legacy merge recorded an absolute path; resolve the configured root once.
        if genos_stages.plain_path(binding['previous_selection']).resolve() != backup.resolve():
            raise ValueError('Retry adoption backup path mismatch')
        if sha(backup) != binding['previous_sha256']:
            raise ValueError('Retry adoption backup hash mismatch')
        previous = json.loads(backup.read_text())
        if any(current.get(k) != previous.get(k) for k in
               ('schema_version', 'inputs_sha256', 'expected_document_ids', 'input_inventory_valid')):
            raise ValueError('Retry adoption changed parent input binding')
        child_dir = genos_stages.plain_path(data / 'LOGS' / child)
        from .structure_selection import run_lock
        with run_lock(child_dir):
            child_path = genos_stages.plain_path(child_dir / 'structure-selection.json')
            retry = json.loads(child_path.read_text())
            status = genos_status.read_report(child_dir)
            if (not status['recorded'] or status['attempt']['stage'] not in ('structure', 'all')
                    or status['attempt']['status'] not in ('COMPLETED', 'FAILED', 'COMPLETED_WITH_FAILURES')
                    or status['attempt'].get('error') or retry.get('schema_version') != 'structure-selection-v1'):
                raise ValueError('Retry adoption child is not a finished structure run')
            child_passed = {r['document_id'] for r in status['documents']
                            if r['selection'] == 'SELECTED' and r['phases']['structure']['state'] == 'PASSED'}
            if child_passed != set(retry['documents']):
                raise ValueError('Retry adoption child selection and ledger disagree')
            combined = {**previous['documents'], **retry['documents']}
            if current['documents'] != combined:
                raise ValueError('Retry adoption union differs from recorded merge')
            for did, entry in retry['documents'].items():
                if did not in rows or rows[did]['phases']['structure']['state'] != 'FAILED':
                    raise ValueError('Retry adoption was not an original failure')
                # The release consumer verifies key syntax, receipt hash, structure and DB identity.
                from .document_release import verified_structures
                verified_structures(data, {'schema_version': 'structure-selection-v1',
                    'completed': True, 'expected_document_ids': [did], 'documents': {did: entry}})
                folder = genos_stages.plain_path(data / 'STRUCTURE' / entry['key'])
                receipt = json.loads((folder / 'structure-receipt.json').read_text())
                if receipt['input_row'] != inventory[did]:
                    raise ValueError('Retry adoption original input identity mismatch')
            evidence.append({'run_id': child, 'backup_sha256': sha(backup),
                'child_selection_sha256': sha(child_path), 'child_status_sha256': digest(status),
                'adopted_document_ids': sorted(child_passed)})
        current = previous
    if set(current['documents']) != passed:
        raise ValueError('Structure selection and latest status ledger disagree without verified retry lineage')
    return set(selection['documents']), evidence
