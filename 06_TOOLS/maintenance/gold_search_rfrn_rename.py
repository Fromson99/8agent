"""Rename the two local Gold search data columns, preserving row contents and aliases."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path

import gold_docid_width_100 as guard

ROOT, HERE = guard.ROOT, guard.HERE
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261104-gold-search-rfrn'
RENAMES = {'SRCH_DATA_HASH_VALU': 'RFRN_DATA_HASH_VALU', 'SRCH_DATA_CTNT': 'RFRN_DATA_CTNT'}
TARGET = 'mapping_local_rfrn_current.json'
connect, existing = guard.connect, guard.existing
guard.OUT, guard.KEYS = OUT, ('SRCH_ROW',)
save, event = guard.save, guard.event


def snapshot(db, mapping):
    value = existing.snapshot(db, mapping)
    with db.cursor() as cursor:
        cursor.execute('SELECT RFRN_POST_HASH_VALU,RFRN_DTA_TYPE_VALU,RFRN_DTA_ID,SRCH_DATA_HASH_VALU,SRCH_DATA_CTNT FROM ' +
                       mapping.table('SRCH_ROW') + ' ORDER BY RFRN_POST_HASH_VALU,RFRN_DTA_TYPE_VALU,RFRN_DTA_ID FETCH FIRST 8 ROWS ONLY')
        value['search_content_samples'] = [[*row[:4], hashlib.sha256(row[4].encode()).hexdigest()] for row in cursor]
    return value


def plan():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'plan.json').exists():
        raise RuntimeError('Existing plan; inspect without overwriting')
    source, sha = connect.active_mapping()
    original = connect.read(source)
    target = deepcopy(original)
    for logical, name in RENAMES.items():
        assert target['tables']['SRCH_ROW']['columns'][logical]['name'] == logical
        target['tables']['SRCH_ROW']['columns'][logical]['name'] = name
    target['revision'] = '20261104-local-rfrn-data-r1'
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
            cursor.execute("SELECT DBMS_METADATA.GET_DDL('TABLE',:name) FROM DUAL", name=old.tables['SRCH_ROW']['name'])
            (OUT / 'before-ddl.sql').write_text(cursor.fetchone()[0])
    table = old.physical_table('SRCH_ROW')
    steps = [{'old': old_name, 'new': new_name,
              'forward': 'ALTER TABLE ' + table + ' RENAME COLUMN ' + old_name + ' TO ' + new_name,
              'reverse': 'ALTER TABLE ' + table + ' RENAME COLUMN ' + new_name + ' TO ' + old_name}
             for old_name, new_name in RENAMES.items()]
    save('plan.json', {'old_mapping_file': str(source.relative_to(ROOT)), 'old_mapping_sha256': sha,
                      'pointer_sha256': connect.sha(HERE / 'ACTIVE_MAPPING.json'),
                      'target_mapping_sha256': connect.sha(OUT / 'target-mapping.json'), 'steps': steps,
                      'user_request': '조회자료해시값 조회자료 내용 이게 SRCH가 아니라 RFRN이거야 이거 다바꿔줘'})
    (OUT / 'apply.sql').write_text(';\n'.join(s['forward'] for s in steps) + ';\n')
    (OUT / 'rollback.sql').write_text(';\n'.join(s['reverse'] for s in reversed(steps)) + ';\n')
    print(json.dumps({'status': 'PLAN_READY', 'columns': 2, 'steps': steps}))


def rollback(p, error):
    failures = []
    old = connect.load_mapping(ROOT / p['old_mapping_file'])
    try:
        with existing.writer() as db, db.cursor() as cursor:
            cursor.execute('ALTER SESSION SET DDL_LOCK_TIMEOUT=5')
            for step in reversed(p['steps']):
                cursor.execute('SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME=:t AND COLUMN_NAME IN (:a,:b)',
                               t=old.tables['SRCH_ROW']['name'], a=step['old'], b=step['new'])
                names = {r[0] for r in cursor}
                if names == {step['new']}:
                    event(status='REVERSING', sql=step['reverse'])
                    cursor.execute(step['reverse'])
                    event(status='REVERSED', sql=step['reverse'])
                elif names != {step['old']}:
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
                for step in p['steps']:
                    guard.quiescent(db, old)
                    event(status='STARTED', sql=step['forward'])
                    cursor.execute(step['forward'])
                    event(status='APPLIED', sql=step['forward'])
            new.preflight(db)
            after = snapshot(db, new)
            save('after.json', after)
            assert before == after, 'Unexpected data/object/type/constraint/index/publication/content change'
            save('database-verified.json', {'status': 'PASS', 'renamed_columns': 2, 'tables': 13, 'columns': 60,
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
    result = {'status': 'RENAMED_AND_MAPPING_ACTIVATED', 'renames': RENAMES,
              'table': new.tables['SRCH_ROW']['name'], 'active_mapping': TARGET,
              'sha256': p['target_mapping_sha256'], 'data_modified': False,
              'finished_utc': datetime.now(timezone.utc).isoformat()}
    save('completed.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'apply'])
    args = parser.parse_args()
    with (Path.home() / '.local/state/8-agent/gold-r12-1208/schema-migration.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        {'plan': plan, 'apply': apply}[args.action]()
