"""Local SRC_POST registration timestamp rename; journal, inverse DDL and mapping CAS."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path

import gold_docid_width_100 as guard

ROOT = guard.ROOT
HERE = guard.HERE
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261104-gold-src-post-rgsn-astm'
OLD, NEW = 'RGSN_AITM', 'RGSN_ASTM'
TARGET = 'mapping_local_rgsn_astm_current.json'
connect = guard.connect
existing = guard.existing
guard.OUT = OUT
guard.KEYS = ('SRC_POST',)
save = guard.save
event = guard.event


def snapshot(db, mapping):
    result = existing.snapshot(db, mapping)
    with db.cursor() as cursor:
        cursor.execute('SELECT DOC_POST_HASH_VALU,RGSN_AITM FROM ' + mapping.table('SRC_POST') +
                       ' ORDER BY DOC_POST_HASH_VALU')
        result['source_registration_times'] = [[key, value.isoformat()] for key, value in cursor]
    return result


def plan():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'plan.json').exists():
        raise RuntimeError('Existing plan; preserve and inspect')
    source, sha = connect.active_mapping()
    original = connect.read(source)
    target = deepcopy(original)
    column = target['tables']['SRC_POST']['columns'][OLD]
    assert column['name'] == OLD and column['type'] == 'TIMESTAMP(6) WITH TIME ZONE'
    column['name'] = NEW
    target['revision'] = '20261104-local-rgsn-astm-r1'
    assert original['owner'] == 'A8_GR12_CM1208'
    save('before-active-mapping.json', connect.read(HERE / 'ACTIVE_MAPPING.json'))
    save('before-mapping.json', original)
    save('target-mapping.json', target)
    old = connect.load_mapping(source)
    connect.load_mapping(OUT / 'target-mapping.json')
    with existing.writer() as db:
        old.preflight(db)
        save('concurrency-plan.json', guard.quiescent(db, old))
        save('plan-before.json', snapshot(db, old))
        with db.cursor() as cursor:
            cursor.execute("SELECT DBMS_METADATA.GET_DDL('TABLE',:name) FROM DUAL", name=old.tables['SRC_POST']['name'])
            (OUT / 'before-ddl.sql').write_text(cursor.fetchone()[0])
    forward = 'ALTER TABLE ' + old.physical_table('SRC_POST') + ' RENAME COLUMN ' + OLD + ' TO ' + NEW
    reverse = 'ALTER TABLE ' + old.physical_table('SRC_POST') + ' RENAME COLUMN ' + NEW + ' TO ' + OLD
    save('plan.json', {'old_mapping_file': str(source.relative_to(ROOT)), 'old_mapping_sha256': sha,
                      'pointer_sha256': connect.sha(HERE / 'ACTIVE_MAPPING.json'),
                      'target_mapping_sha256': connect.sha(OUT / 'target-mapping.json'),
                      'forward': forward, 'reverse': reverse,
                      'user_request': 'LGL_SRC_POST에서 RGSN_AITM을 RGSN_ASTM으로 바꿔야해'})
    (OUT / 'apply.sql').write_text(forward + ';\n')
    (OUT / 'rollback.sql').write_text(reverse + ';\n')
    print(json.dumps({'status': 'PLAN_READY', 'forward': forward}))


def rollback(p, error):
    failures = []
    try:
        old = connect.load_mapping(ROOT / p['old_mapping_file'])
        with existing.writer() as db, db.cursor() as cursor:
            cursor.execute('ALTER SESSION SET DDL_LOCK_TIMEOUT=5')
            cursor.execute('SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME=:t AND COLUMN_NAME IN (:a,:b)',
                           t=old.tables['SRC_POST']['name'], a=OLD, b=NEW)
            names = {r[0] for r in cursor}
            # Inspect dictionary state even if the ALTER acknowledgement was lost.
            if names == {NEW}:
                event(status='REVERSING', sql=p['reverse'])
                cursor.execute(p['reverse'])
                event(status='REVERSED', sql=p['reverse'])
            elif names != {OLD}:
                raise RuntimeError('Unexpected actual column state')
            old.preflight(db)
            assert snapshot(db, old) == connect.read(OUT / 'before.json')
        pointer = connect.read(HERE / 'ACTIVE_MAPPING.json')
        previous = connect.read(OUT / 'before-active-mapping.json')
        if pointer != previous:
            assert pointer['mapping_file'] == TARGET and pointer['sha256'] == p['target_mapping_sha256']
            guard.save_file(HERE / 'ACTIVE_MAPPING.json', previous)
    except Exception as exc:
        failures.append(str(exc))
    save('failed.json', {'error': str(error), 'rollback_verified': not failures, 'rollback_errors': failures})
    if failures:
        raise RuntimeError('Rollback incomplete; inspect failed.json') from error


def apply():
    if (OUT / 'ddl-events.jsonl').exists() or (OUT / 'completed.json').exists():
        raise RuntimeError('Existing DDL attempt; inspect instead of retrying')
    p = connect.read(OUT / 'plan.json')
    assert connect.sha(HERE / 'ACTIVE_MAPPING.json') == p['pointer_sha256']
    assert connect.sha(ROOT / p['old_mapping_file']) == p['old_mapping_sha256']
    assert connect.sha(OUT / 'target-mapping.json') == p['target_mapping_sha256']
    old = connect.load_mapping(ROOT / p['old_mapping_file'])
    new = connect.load_mapping(OUT / 'target-mapping.json')
    try:
        with existing.writer() as db:
            old.preflight(db)
            save('concurrency-apply.json', guard.quiescent(db, old))
            before = snapshot(db, old)
            save('before.json', before)
            assert before == connect.read(OUT / 'plan-before.json'), 'Concurrent DB change'
            with db.cursor() as cursor:
                cursor.execute('ALTER SESSION SET DDL_LOCK_TIMEOUT=5')
                guard.quiescent(db, old)
                event(status='STARTED', sql=p['forward'])
                cursor.execute(p['forward'])
                event(status='APPLIED', sql=p['forward'])
            new.preflight(db)
            after = snapshot(db, new)
            save('after.json', after)
            assert before == after, 'Unexpected data/object/type/constraint/index/publication/timestamp change'
            save('database-verified.json', {'status': 'PASS', 'renamed_columns': 1, 'tables': 13, 'columns': 60,
                                          'normalized_snapshots_identical': True,
                                          'target_mapping_sha256': p['target_mapping_sha256']})
            assert connect.sha(HERE / 'ACTIVE_MAPPING.json') == p['pointer_sha256']
            guard.save_file(HERE / TARGET, connect.read(OUT / 'target-mapping.json'))
            guard.save_file(HERE / 'ACTIVE_MAPPING.json', {
                'schema_version': 'gold-active-physical-map-v1', 'mapping_file': TARGET,
                'sha256': p['target_mapping_sha256'],
                'migration_receipt': str((OUT / 'database-verified.json').relative_to(ROOT))})
            assert connect.active_mapping() == (HERE / TARGET, p['target_mapping_sha256'])
    except BaseException as exc:
        if (OUT / 'ddl-events.jsonl').exists():
            event(status='FAILED', error=str(exc), error_type=type(exc).__name__)
            rollback(p, exc)
        else:
            save('pre-ddl-failed.json', {'error': str(exc), 'ddl': 0})
        raise
    result = {'status': 'RENAMED_AND_MAPPING_ACTIVATED', 'column': NEW, 'table': new.tables['SRC_POST']['name'],
              'active_mapping': TARGET, 'sha256': p['target_mapping_sha256'], 'data_modified': False,
              'finished_utc': datetime.now(timezone.utc).isoformat()}
    save('completed.json', result)
    print(json.dumps(result))


def verify():
    if (OUT / 'consumer-verification.json').exists():
        raise RuntimeError('Preserve existing consumer result')
    with connect.open_store(seconds=120, max_calls=100) as (store, request, transport):
        mapping = store.gold_ports.mapping
        assert mapping.column('SRC_POST', OLD) == NEW
        for key in ('DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRCH_ROW', 'ONTL_ANC', 'VCTR_ITEM'):
            assert mapping.tables[key]['columns']['DOC_ID']['type'] == 'VARCHAR2(100 BYTE)'
        store.selection.require_latest()
        did = sorted(request.sources.allowed)[0]
        document = request.sources.document(did)
        block = request.sources.blocks(did, limit=1)['rows'][0]
        anchor = {'document_id': did, 'version': document['source_artifact_sha256'], 'unit_id': block['unit_id']}
        source = store.gold_ports.source_reader(anchor)
        assert block['text'] in source
        baseline = connect.read(ROOT / '09_ARTIFACTS/AUDITS/20261104-gold-docid100-local/consumers-after.json')
        hashes = {k: hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                  for k, v in [('document', document), ('block', block), ('source', source)]}
        assert all(value == baseline['content_sha256'][key] for key, value in hashes.items())
        result = {'status': 'PASS', 'mapping': store.gold_ports.preflight, 'sql_calls': request.sql.calls,
                  'physical_timestamp_column': NEW, 'docid100_six_columns_preserved': True,
                  'document_block_source_identical_to_previous_verified_state': True,
                  'content_sha256': hashes, 'model_calls': 0, 'data_writes': 0}
    save('consumer-verification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'apply', 'verify'])
    args = parser.parse_args()
    lock_path = Path.home() / '.local/state/8-agent/gold-r12-1208/schema-migration.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        {'plan': plan, 'apply': apply, 'verify': verify}[args.action]()
