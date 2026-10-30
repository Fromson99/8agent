"""Apply a pre-recorded, name-only local Gold schema change with inverse DDL.

Oracle DDL commits independently. Each step is journalled; a failed run reverses
only its own completed steps. Data types, row values and object IDs are retained.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CONNECTOR = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261030-gold-physical-rename'
sys.dont_write_bytecode = True


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)


def event(**value):
    with (OUT / 'ddl-events.jsonl').open('a') as f:
        f.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **value}, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())


def snapshot(connection, mapping):
    result = {'row_counts': {}, 'objects': [], 'constraints': [], 'grants': [], 'publications': {}}
    with connection.cursor() as c:
        for key in mapping.tables:
            c.execute('SELECT COUNT(*) FROM ' + mapping.physical_table(key))
            result['row_counts'][key] = int(c.fetchone()[0])
        c.execute('SELECT OBJECT_NAME,OBJECT_TYPE,STATUS,OBJECT_ID,DATA_OBJECT_ID FROM USER_OBJECTS ORDER BY OBJECT_TYPE,OBJECT_NAME')
        result['objects'] = [list(row) for row in c]
        c.execute('SELECT TABLE_NAME,CONSTRAINT_NAME,CONSTRAINT_TYPE,STATUS,VALIDATED FROM USER_CONSTRAINTS ORDER BY TABLE_NAME,CONSTRAINT_NAME')
        result['constraints'] = [list(row) for row in c]
        c.execute('SELECT TABLE_NAME,GRANTEE,PRIVILEGE FROM USER_TAB_PRIVS_MADE ORDER BY TABLE_NAME,GRANTEE,PRIVILEGE')
        result['grants'] = [list(row) for row in c]
        for key, ident, payload in [('SRC_POST', 'DOC_POST_HASH_VALU', 'DOC_POST_IFMN_CTNT'),
                                    ('SRCH_POST', 'RFRN_POST_HASH_VALU', 'RFRN_POST_IFMN_CTNT'),
                                    ('VCTR_POST', 'VCTR_POST_ID', 'VCTR_POST_IFMN_CTNT')]:
            c.execute('SELECT ' + ident + ',' + payload + ' FROM ' + mapping.table(key) + ' ORDER BY ' + ident)
            rows = c.fetchmany(33)
            if len(rows) > 32:
                raise RuntimeError('Unexpected publication count')
            result['publications'][key] = [[a, hashlib.sha256(b.encode()).hexdigest()] for a, b in rows]
    return result


def main():
    if sys.argv[1:] != ['--apply']:
        raise SystemExit('Usage: gold_physical_rename.py --apply (explicit name-change task only)')
    spec = importlib.util.spec_from_file_location('gold_name_mapping', CONNECTOR / 'physical_mapping.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    old_file = CONNECTOR / 'mapping_r12_local.json'
    target_file = OUT / 'target-mapping.json'
    old = module.GoldMapping.load(old_file)
    new = module.GoldMapping.load(target_file)
    if old.owner != new.owner or old.owner != 'A8_GR12_CM1208':
        raise RuntimeError('Unexpected target owner')
    if (OUT / 'completed.json').exists() or (OUT / 'ddl-events.jsonl').exists():
        raise RuntimeError('Existing attempt: inspect its journal before any new apply')
    steps = []
    for key, before in old.tables.items():
        after = new.tables[key]
        if before['name'] != after['name']:
            raise RuntimeError('No alternate table names supplied for this task; table renames are not planned')
        if before['primary_key'] != after['primary_key'] or before['indexes'] != after['indexes']:
            raise RuntimeError('Name-only migration cannot alter keys/indexes')
        for logical, column in before['columns'].items():
            target = after['columns'][logical]
            if any(column[field] != target[field] for field in ('type', 'required', 'default')):
                raise RuntimeError('Name-only migration cannot change type/width/nullability/default')
            if column['name'] != target['name']:
                table = old.physical_table(key)
                steps.append({'forward': 'ALTER TABLE ' + table + ' RENAME COLUMN ' + column['name'] + ' TO ' + target['name'],
                              'reverse': 'ALTER TABLE ' + table + ' RENAME COLUMN ' + target['name'] + ' TO ' + column['name']})
    if len(steps) != 16:
        raise RuntimeError('Unexpected change count')
    save(OUT / 'plan.json', {'owner': old.owner, 'old_mapping_sha256': sha(old_file),
                           'target_mapping_sha256': sha(target_file), 'steps': steps})
    (OUT / 'apply.sql').write_text(';\n'.join(s['forward'] for s in steps) + ';\n')
    (OUT / 'rollback.sql').write_text(';\n'.join(s['reverse'] for s in reversed(steps)) + ';\n')
    import oracledb
    oracledb.defaults.fetch_lobs = False
    credentials = Path.home() / '.local/state/8-agent/gold-r12-1208/connection.json'
    if credentials.stat().st_mode & 0o077:
        raise RuntimeError('Private credentials permissions required')
    credentials_value = read(credentials)
    if credentials_value['dsn'].split(':')[0] not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('This migration is local only')
    completed = []
    with oracledb.connect(**credentials_value) as connection:
        connection.call_timeout = 60000
        with connection.cursor() as c:
            c.execute("SELECT SYS_CONTEXT('USERENV','SESSION_USER'),SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM DUAL")
            if c.fetchone() != (old.owner, old.owner):
                raise RuntimeError('Connected schema differs')
            c.execute('ALTER SESSION SET DDL_LOCK_TIMEOUT=5')
        old.preflight(connection)
        before = snapshot(connection, old)
        save(OUT / 'before.json', before)
        ddl = []
        with connection.cursor() as c:
            for table in old.tables.values():
                c.execute("SELECT DBMS_METADATA.GET_DDL('TABLE',:name) FROM DUAL", name=table['name'])
                ddl.append(c.fetchone()[0])
        (OUT / 'before-ddl.sql').write_text('\n'.join(ddl))
        try:
            for number, step in enumerate(steps, 1):
                event(status='STARTED', number=number, sql=step['forward'])
                with connection.cursor() as c:
                    c.execute(step['forward'])
                completed.append(step)
                event(status='APPLIED', number=number, sql=step['forward'])
            new.preflight(connection)
            after = snapshot(connection, new)
            save(OUT / 'after.json', after)
            if after != before:
                raise RuntimeError('Rows/object identities/constraints/grants/publication bytes changed')
            save(OUT / 'database-verified.json', {'column_renames': len(completed), 'table_renames': 0,
                 'registered_table_names_already_match': 13, 'name_only': True,
                 'before_after_snapshot_equal': True, 'target_mapping_sha256': sha(target_file)})
        except BaseException as exc:
            event(status='FAILURE', error_type=type(exc).__name__, error=str(exc))
            rollback_errors = []
            for step in reversed(completed):
                try:
                    with connection.cursor() as c:
                        c.execute(step['reverse'])
                    event(status='REVERSED', sql=step['reverse'])
                except Exception as err:
                    rollback_errors.append({'sql': step['reverse'], 'error_type': type(err).__name__, 'error': str(err)})
            save(OUT / 'failed.json', {'completed_before_error': len(completed), 'rollback_errors': rollback_errors})
            raise
    # Activate only after the new schema and unchanged data have been verified.
    selected_file = CONNECTOR / 'mapping_local_current.json'
    save(selected_file, read(target_file))
    save(CONNECTOR / 'ACTIVE_MAPPING.json', {'schema_version': 'gold-active-physical-map-v1',
         'mapping_file': selected_file.name, 'sha256': sha(selected_file),
         'migration_receipt': str((OUT / 'database-verified.json').relative_to(ROOT))})
    save(OUT / 'completed.json', {'status': 'RENAMED_AND_MAPPING_ACTIVATED', 'column_renames': 16,
         'table_renames': 0, 'registered_tables_verified': 13, 'data_values_modified': False,
         'active_mapping_sha256': sha(selected_file), 'finished_utc': datetime.now(timezone.utc).isoformat()})
    print(json.dumps(read(OUT / 'completed.json')))


if __name__ == '__main__':
    main()
