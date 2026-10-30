#!/usr/bin/env python3
"""Bounded local Oracle example; uses the pre-existing labelled test container."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTAINER = 'a8-legal-mapped-20261023'
from gold_connection import GoldConfig, GoldError, GoldConflict, open_gold_request, VectorReader, change_vector_head


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n')


def resources():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0])*1024
    return {'at': datetime.now(timezone.utc).isoformat(), 'wsl_free_bytes': shutil.disk_usage(ROOT).free,
            'windows_c_free_bytes': shutil.disk_usage('/mnt/c').free, 'memory_available_bytes': memory['MemAvailable'],
            'swap_used_bytes': memory['SwapTotal']-memory['SwapFree']}


def guard(before, result):
    current = resources()
    result['resource_samples'].append(current)
    if (current['wsl_free_bytes'] < 10*1024**3 or current['windows_c_free_bytes'] < 20*1024**3 or
        current['memory_available_bytes'] < 4*1024**3 or
        current['swap_used_bytes']-before['swap_used_bytes'] > 128*1024**2 or
        before['windows_c_free_bytes']-current['windows_c_free_bytes'] > 256*1024**2):
        raise GoldError('LOCAL_RESOURCE_GUARD')


def scalar(connection, sql, **binds):
    with connection.cursor() as cursor:
        cursor.execute(sql, binds)
        return cursor.fetchone()[0]


def verify(connection, config, example):
    from semantic_runtime.oracle_dp_io import DPError, digest
    from semantic_runtime.oracle_query_fulltext import UnitIndex
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    def rejects(name, fn, error, message):
        try:
            fn()
        except error as exc:
            if message not in str(exc):
                raise
            checks.append(name)
        else:
            raise AssertionError(name+' did not reject')

    check('actual_13_tables', scalar(connection, 'SELECT COUNT(*) FROM USER_TABLES') == 13)
    check('actual_60_columns', scalar(connection, 'SELECT COUNT(*) FROM USER_TAB_COLUMNS') == 60)
    check('actual_13_primary_keys', scalar(connection, "SELECT COUNT(*) FROM USER_CONSTRAINTS WHERE CONSTRAINT_TYPE='P'") == 13)
    check('actual_11_ordinary_indexes', scalar(connection, "SELECT COUNT(*) FROM USER_INDEXES WHERE UNIQUENESS='NONUNIQUE' AND INDEX_TYPE='NORMAL'") == 11)
    check('no_foreign_or_extra_unique_constraints', scalar(connection, "SELECT COUNT(*) FROM USER_CONSTRAINTS WHERE CONSTRAINT_TYPE IN ('R','U')") == 0)
    check('no_function_indexes', scalar(connection, 'SELECT COUNT(*) FROM USER_IND_EXPRESSIONS') == 0)
    check('native_VECTOR_column', scalar(connection, "SELECT COUNT(*) FROM USER_TAB_COLUMNS WHERE DATA_TYPE='VECTOR'") == 1)
    request, transport = open_gold_request(connection, config, document_ids=['public'])
    check('existing_source_reader_name_type', request.sources.document('public')['name'] == '가상 예시 문서 public')
    block = request.sources.source('public', '1')
    check('existing_source_reader_hash_and_YN_roundtrip', json.loads(block['json'])['text'] == block['text'] == '이사회 승인 절차를 확인한다.')
    check('existing_original_numeric_order', [r['block_id'] for r in request.sources.blocks('public')['rows']] == ['1', '2'])
    rejects('source_ACL_denied', lambda: request.sources.source('private', '1'), DPError, 'QUERY_SCOPE')
    rejects('request_scope_cannot_widen', lambda: request.restrict(['public', 'private']), DPError, 'QUERY_SCOPE')
    with connection.cursor() as cursor:
        cursor.execute('UPDATE '+config.table('DOC_BLK')+" SET BODY_CTNT='변조 예시' WHERE DOC_ID='public' AND BODY_SLC_ID='1'")
    try:
        rejects('existing_source_integrity_detects_tampering', lambda: request.sources.source('public', '1'), DPError, 'QUERY_SOURCE_HASH')
    finally:
        connection.rollback()
    index = UnitIndex(request)
    laws = index.law_groups_page(index, ['이사회 승인'])
    check('existing_fulltext_SRCH_ROW_phrase_and_ACL', laws['items'] == [{'document_id': 'public', 'article_count': 1, 'unit_count': 2}])
    first = index.hit_page(index, ['이사회 승인'], 'public:article-1', limit=1)
    second = index.hit_page(index, ['이사회 승인'], 'public:article-1', limit=1, cursor=first['next_cursor'])
    check('existing_fulltext_pages_and_totals', first['total'] == second['total'] == 2 and
          first['items'][0]['key'] != second['items'][0]['key'] and second['next_cursor'] is None)
    rejects('fulltext_cursor_binding', lambda: index.hit_page(index, ['다른 검색어'], 'public:article-1',
            cursor=first['next_cursor']), DPError, 'QUERY_CURSOR')
    check('existing_fulltext_empty_result', index.law_groups_page(index, ['없는 검색어'])['items'] == [])
    reader = VectorReader(request, config)
    check('partial_vector_rows_not_active', reader.active() is None)
    rejects('partial_vector_publication_rejected', lambda: change_vector_head(connection, config, reader,
            digest('unfinished'), previous=None, revision=0), GoldError, 'UNSEALED')
    publication = example['vector']['pub']
    change_vector_head(connection, config, reader, publication, previous=None, revision=0)
    phash = example['vector']['envelope']['completion']['profile_sha256']
    vectors = reader.search([1., 0., 0., 0.], profile_sha256=phash)
    check('native_exact_vector_ACL_and_group_before_limit', len(vectors) == 1 and
          vectors[0]['DOC_ID'] == 'public' and vectors[0]['SRC_UNIT_ID'] == 'public:article-1' and abs(vectors[0]['DISTANCE']) < 1e-6)
    rejects('vector_scope_denied', lambda: reader.search([1., 0., 0., 0.], profile_sha256=phash, documents=['private']), GoldError, 'SCOPE')
    rejects('vector_profile_denied', lambda: reader.search([1., 0., 0., 0.], profile_sha256='x'*64), GoldError, 'PROFILE')
    rejects('vector_nonfinite_denied', lambda: reader.search([float('nan'), 0., 0., 0.], profile_sha256=phash), GoldError, 'PROFILE')
    rejects('head_stale_insert_denied', lambda: change_vector_head(connection, config, reader, publication,
            previous=None, revision=0), GoldConflict, 'CONFLICT')
    change_vector_head(connection, config, reader, None, previous=publication, revision=1)
    check('head_deactivate', reader.active() is None)
    change_vector_head(connection, config, reader, publication, previous=None, revision=2)
    rejects('head_ABA_stale_revision_denied', lambda: change_vector_head(connection, config, reader, None,
            previous=publication, revision=1), GoldConflict, 'CONFLICT')
    check('head_revision_monotonic', reader.active()['CHAN_NO'] == 3)
    count = scalar(connection, 'SELECT COUNT(*) FROM '+config.table('ONTL_ANC')+' a JOIN '+config.table('ONTL_HEAD')+
                   ' h ON h.ONTL_POST_ID=a.ONTL_POST_ID JOIN '+config.table('DOC_UNIT')+
                   ' u ON u.DOC_ID=a.DOC_ID AND u.STRC_UNIT_ID=a.STRC_UNIT_ID WHERE u.MNFST_HASH_VALU=:v AND a.DOC_ID=:d',
                   v=example['version'], d='public')
    check('ontology_example_anchor_join', count == 1)
    check('no_legacy_Silver_tables_in_executed_SQL', all('SIDDS.' not in q and 'SIDDA.' not in q for q in transport.statements))
    allocated = scalar(connection, 'SELECT NVL(SUM(BYTES),0) FROM USER_SEGMENTS')
    row_counts = {t['suffix']: scalar(connection, 'SELECT COUNT(*) FROM '+config.table(t['suffix'])) for t in config.model['tables']}
    return {'variant': config.variant, 'checks': checks, 'checks_passed': len(checks), 'allocated_segment_bytes': allocated,
            'row_counts': row_counts, 'rows': sum(row_counts.values()), 'read_SQL_calls': len(transport.statements),
            'source_example': block, 'fulltext_example': laws, 'vector_example': vectors,
            'bounded_scope': 'native SQL/data reader contracts; no full RAG, embedding model, production publisher or performance certification'}


def run_local(config_paths, result_dir, execution):
    import oracledb
    from example_data import make_example, load_example
    result_dir.mkdir(parents=True, exist_ok=False)
    before = resources()
    result = {'status': 'RUNNING', 'execution': execution, 'resource_samples': [before], 'cases': [], 'created_schemas': [], 'dropped_schemas': [],
              'new_model_calls': 0, 'copied_corpus_bytes': 0, 'downloaded_image_bytes': 0,
              'limits': {'schema_quota_bytes_each': 64*1024**2, 'minimum_windows_free_bytes': 20*1024**3,
                         'minimum_available_RAM_bytes': 4*1024**3, 'maximum_swap_increase_bytes': 128*1024**2}}
    admin = None
    started = False
    owned = []
    try:
        guard(before, result)
        info = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER]))[0]
        if info['Config'].get('Labels', {}).get('a8.task') != 'legal-mapped-20261023':
            raise GoldError('LOCAL_CONTAINER_IDENTITY')
        endpoints = info['HostConfig']['PortBindings']['1521/tcp']
        if len(endpoints) != 1 or endpoints[0]['HostIp'] != '127.0.0.1':
            raise GoldError('LOCAL_BINDING_ONLY')
        result['container_was_running'] = info['State']['Running']
        result['container_memory_limit_bytes'] = info['HostConfig']['Memory']
        if not 0 < info['HostConfig']['Memory'] <= 3*1024**3:
            raise GoldError('LOCAL_CONTAINER_MEMORY_LIMIT')
        if not info['State']['Running']:
            started = True
            subprocess.run(['docker', 'start', CONTAINER], check=True, capture_output=True, timeout=30)
        # Existing local test credentials stay in memory; never copied to result/config files.
        password = dict(x.split('=', 1) for x in info['Config']['Env'])['ORACLE_PASSWORD']
        dsn = '127.0.0.1:'+endpoints[0]['HostPort']+'/FREEPDB1'
        deadline = time.monotonic()+120
        while admin is None:
            guard(before, result)
            try:
                admin = oracledb.connect(dsn=dsn, user='system', password=password, tcp_connect_timeout=3)
            except oracledb.DatabaseError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(3)
        result['oracle_version'] = admin.version
        for path in config_paths:
            guard(before, result)
            user = 'A8_GR12_'+secrets.token_hex(5).upper()
            own_password = secrets.token_hex(24)
            with admin.cursor() as cursor:
                cursor.execute('CREATE USER '+user+' IDENTIFIED BY "'+own_password+'" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
                owned.append(user)
                result['created_schemas'].append(user)
                cursor.execute('GRANT CREATE SESSION,CREATE TABLE TO '+user)
            config = GoldConfig.load(path, ROOT, example_owner=user)
            # Replayable DDL uses the documented example owner, never credentials.
            template = GoldConfig.load(path, ROOT)
            (result_dir/('example_'+config.variant+'.sql')).write_text(';\n\n'.join(template.ddl())+';\n')
            with oracledb.connect(dsn=dsn, user=user, password=own_password) as connection:
                for sql in config.ddl():
                    with connection.cursor() as cursor:
                        cursor.execute(sql)
                example = make_example()
                save(result_dir/'synthetic_example.json', example)
                load_example(connection, config, example)
                case = verify(connection, config, example)
                result['cases'].append(case)
            guard(before, result)
            with admin.cursor() as cursor:
                cursor.execute('DROP USER '+user+' CASCADE')
            owned.remove(user)
            result['dropped_schemas'].append(user)
            print(config.variant+': '+str(case['checks_passed'])+' checks passed; '+str(case['rows'])+' rows', flush=True)
        result['status'] = 'PASS_LOCAL_DATA_CONNECTION'
    except BaseException as exc:
        result['status'] = 'FAILED'
        result['error_type'] = type(exc).__name__
        result['error'] = str(exc)
        (result_dir/'failure.txt').write_text(traceback.format_exc())
    finally:
        if admin is not None:
            for user in owned:
                try:
                    with admin.cursor() as cursor:
                        cursor.execute('DROP USER '+user+' CASCADE')
                    result['dropped_schemas'].append(user)
                except Exception as exc:
                    result.setdefault('cleanup_errors', []).append({'schema': user, 'type': type(exc).__name__})
            admin.close()
        if started:
            stop = subprocess.run(['docker', 'stop', '--time', '20', CONTAINER], capture_output=True, timeout=40)
            result['container_restored_stopped'] = stop.returncode == 0
        result['resource_samples'].append(resources())
        pinned = json.loads((HERE/'results/original_files_before.json').read_text())
        changed = [name for name, sha in pinned.items() if not (ROOT/name).is_file() or
                   hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != sha]
        result['original_files_checked'] = len(pinned)
        result['original_files_changed'] = changed
        result['temporary_schemas_removed'] = sorted(result['created_schemas']) == sorted(result['dropped_schemas'])
        selected_changed = [name for name, sha in execution['files'].items() if
                            hashlib.sha256((ROOT/execution['code_root']/name).read_bytes()).hexdigest() != sha]
        result['selected_runtime_files_changed'] = selected_changed
        result['working_tree_observation_note'] = 'Observed changes outside this new folder are recorded, not reverted; the run imports the immutable selected release.'
        active_changed = hashlib.sha256((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()).hexdigest() != execution['active_pointer_sha256']
        result['active_pointer_changed_during_run'] = active_changed
        if selected_changed or active_changed or not result['temporary_schemas_removed'] or result.get('container_restored_stopped') is False:
            result['status'] = 'INCOMPLETE_REVIEW_REQUIRED'
        save(result_dir/'result.json', result)
    print('RESULT='+str(result_dir/'result.json'), flush=True)
    print('STATUS='+result['status'], flush=True)
    return 0 if result['status'] == 'PASS_LOCAL_DATA_CONNECTION' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'verify-local'])
    parser.add_argument('--config', action='append', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'plan':
        for path in args.config:
            print(';\n\n'.join(GoldConfig.load(path, ROOT).ddl())+';')
        return 0
    selected = json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
    release = json.loads((ROOT/selected['manifest_path']).read_text())
    code_root = ROOT/release['code_root']
    for name, sha in release['files'].items():
        if hashlib.sha256((code_root/name).read_bytes()).hexdigest() != sha:
            raise GoldError('SELECTED_RUNTIME_HASH: '+name)
    execution = {'release_id': selected['release_id'], 'code_root': release['code_root'], 'files': release['files'],
                 'active_pointer_sha256': hashlib.sha256((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()).hexdigest(),
                 'new_connector_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}}
    backend = ROOT/release['code_root']/'02_BACKEND'
    sys.path.insert(0, str(backend))
    output = HERE/'results'/datetime.now().strftime('run-%Y%m%d-%H%M%S-%f')
    return run_local(args.config, output, execution)


if __name__ == '__main__':
    raise SystemExit(main())
