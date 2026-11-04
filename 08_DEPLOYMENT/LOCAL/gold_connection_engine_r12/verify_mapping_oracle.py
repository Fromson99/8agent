"""Explicit local Oracle mapping contracts using disposable, bounded schemas.

No external model, real corpus writes, deployment, or performance comparison.
Runs only against the existing labelled loopback test container.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import sys
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261030-gold-column-mapping'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(mapping_path=None, output_root=None):
    import connect
    runtime, binding = connect.load_runtime()
    legacy = HERE.parent / 'gold_connection_r12'
    sys.path.append(str(legacy))
    old_test = module('legacy_gold_contracts', legacy / 'run.py')
    example_data = module('legacy_gold_example', legacy / 'example_data.py')
    from physical_mapping import GoldMapping
    from gold_connection import open_gold_request
    from semantic_runtime.ontology_work.repository import ddl as ontology_ddl
    from semantic_runtime.ontology_work.workflow import Workflow
    from semantic_runtime.ontology_work.store import LocalFolderStore
    from semantic_runtime.legal_agent import ontology_scenarios
    from semantic_runtime.legal_agent.ontology_compiler import content_hash
    from semantic_runtime.legal_agent.errors import ContractError
    from semantic_runtime.contracts import digest
    import oracledb
    oracledb.defaults.fetch_lobs = False

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = (Path(output_root) if output_root else OUT) / ('oracle-' + stamp)
    out.mkdir(parents=True)
    result = {'started': stamp, 'models': 0, 'real_corpus_writes': 0, 'created_schemas': [],
              'dropped_schemas': [], 'checks': [], 'status': 'RUNNING'}
    active_before = connect.sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
    admin = None
    try:
        before = runtime.guard()
        info = json.loads(subprocess.check_output(['docker', 'inspect', old_test.CONTAINER]))[0]
        assert info['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
        assert info['State']['Running']
        endpoint = info['HostConfig']['PortBindings']['1521/tcp']
        assert len(endpoint) == 1 and endpoint[0]['HostIp'] == '127.0.0.1'
        dsn = '127.0.0.1:' + endpoint[0]['HostPort'] + '/FREEPDB1'
        password = dict(s.split('=', 1) for s in info['Config']['Env'])['ORACLE_PASSWORD']
        admin = oracledb.connect(dsn=dsn, user='system', password=password)
        admin.call_timeout = 15000
        result['oracle_version'] = admin.version
        gold, agent = 'A8_MAP_G_' + secrets.token_hex(4).upper(), 'A8_MAP_A_' + secrets.token_hex(4).upper()
        key = secrets.token_hex(24)
        with admin.cursor() as cursor:
            for name in (gold, agent):
                cursor.execute('CREATE USER ' + name + ' IDENTIFIED BY "' + key + '" DEFAULT TABLESPACE USERS QUOTA 64M ON USERS')
                result['created_schemas'].append(name)
                cursor.execute('GRANT CREATE SESSION,CREATE TABLE TO ' + name)

        def connection():
            conn = oracledb.connect(dsn=dsn, user=gold, password=key)
            conn.call_timeout = 15000
            return conn

        data = json.loads(Path(mapping_path or HERE / 'mapping_r14_photos.json').read_text())
        # Exercise actual reordered physical columns: logical contracts must survive.
        for table in data['tables'].values():
            table['columns'] = dict(reversed(list(table['columns'].items())))
        mapped = GoldMapping(data, owner=gold)
        (out / 'ddl.sql').write_text(';\n'.join(mapped.ddl()) + ';\n')
        with connection() as conn:
            with conn.cursor() as cursor:
                for statement in mapped.ddl():
                    cursor.execute(statement)
            result['preflight'] = mapped.preflight(conn)
            example = example_data.make_example()
            example_data.load_example(conn, mapped, example)
            legacy_result = old_test.verify(conn, mapped, example)
            result['legacy_contracts'] = legacy_result
            # Mismatching the old mapping must fail before a data query.
            try:
                GoldMapping.load(HERE / 'mapping_r12_local.json', owner=gold).preflight(conn)
            except ValueError:
                result['checks'].append('old_mapping_rejected_on_new_columns')
            else:
                raise AssertionError('old mapping accepted')
            request, transport = open_gold_request(conn, mapped, document_ids=['public'])
            result['checks'].append('new_physical_order_existing_source_fulltext_vector_contracts')

            with admin.cursor() as cursor:
                for statement in ontology_ddl(agent, 'oracle')[:2]:
                    cursor.execute(statement)
                for table in ('LGL_ONT_WORK_A', 'LGL_ONT_EVT_A'):
                    cursor.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ' + agent + '.' + table + ' TO ' + gold)
            repo = mapped.ontology_repository(connection, agent_owner=agent, read_only=False)
            test = module('ontology_workflow_fixture', ROOT / '06_TOOLS/EXPERIMENTS/adr_1160/test_workflow.py')
            work, proposal = test.fixture()
            text = '\n'.join(request.sources.source('public', bid)['text'] for bid in ('1', '2'))
            original = work['originals'][0]
            original.update(text=text, anchor={'document_id': 'public', 'version': digest('public'), 'unit_id': 'article-1',
                            'label': '합성 원문', 'content_sha256': content_hash(text)})
            first, second = text.split('\n')
            proposal = {'components': [
                            {'id': 'C', 'text': first, 'requires': [], 'basis': [{'source': 'S1', 'quote': first}]},
                            {'id': 'R', 'text': second, 'requires': ['C'], 'basis': [{'source': 'S1', 'quote': second}]}],
                        'paths': [{'id': 'NORMAL', 'title': '합성 승인 기록', 'business_use': '매핑 계약 검사',
                                   'conditions': ['C'], 'calculations': [], 'outcomes': ['R'], 'notes': []}], 'unused_components': {}}
            workflow = Workflow(repo, LocalFolderStore(out / 'synthetic-work'), actor='synthetic-reviewer',
                                source_reader=lambda a: text if a == original['anchor'] else None)
            row = workflow.save(work, proposal, bundle_id='cb-map-contract')
            assert not repo.lookup(original['anchor'], {'public'})
            workflow.review(row['bundle_id'], row['revision'], row['work_hash'], True, '합성 자료의 매핑 계약 검사')
            # Inject a failure at the last Agent event to prove Gold+Agent rollback.
            event = repo.event
            def fail_event(c, bid, rev, action, *args, **kwargs):
                if action == 'PUBLISHED':
                    raise RuntimeError('synthetic rollback injection')
                return event(c, bid, rev, action, *args, **kwargs)
            repo.event = fail_event
            try:
                test.publish(workflow, row)
            except RuntimeError as exc:
                assert str(exc) == 'synthetic rollback injection'
            else:
                raise AssertionError('rollback did not execute')
            repo.event = event
            assert not repo.lookup(original['anchor'], {'public'})
            result['checks'].append('gold_and_agent_atomic_rollback')
            publication = test.publish(workflow, row)
            found = repo.lookup(original['anchor'], {'public'})
            assert len(found) == 1 and found[0]['publication_id'] == publication['publication_id']
            assert not repo.lookup(original['anchor'], set())
            assert not repo.lookup({**original['anchor'], 'version': 'other-version'}, {'public'})
            catalog = ontology_scenarios.bind_current(found[0]['context']['scenario_package'], [dict(original, evidence_refs=['E1'])])
            assert first in catalog['paths'][0]['body'] and second in catalog['paths'][0]['body'] and catalog['runtime_compilation'] is False
            result['checks'].append('ontology_approval_publish_anchor_acl_hash_and_current_original')
            # Route the same lookup through the request's metered SQL interface.
            request_repo = mapped.request_ontology_repository(request)
            before_calls = request.sql.calls
            assert request_repo.lookup(original['anchor'], {'public'}) == found
            assert request.sql.calls == before_calls + 2
            result['checks'].append('ontology_request_budget_and_sql_port')
            repo.activate(row['bundle_id'], None, 1, 'synthetic-reviewer')
            assert not request_repo.lookup(original['anchor'], {'public'})
            assert test.publish(workflow, row)['reused']
            try:
                repo.activate(row['bundle_id'], publication['publication_id'], 1, 'synthetic-reviewer')
            except ContractError:
                pass
            else:
                raise AssertionError('stale ontology activation accepted')
            repo.activate(row['bundle_id'], publication['publication_id'], 2, 'synthetic-reviewer')
            assert request_repo.lookup(original['anchor'], {'public'})
            result['checks'].append('ontology_withdraw_reconcile_and_stale_cas')
            result['ontology_read_sql'] = len(transport.statements)
        after = runtime.guard()
        result['swap_growth_bytes'] = max(0, before['SwapFree'] - after['SwapFree'])
        assert result['swap_growth_bytes'] <= 128 * 1024**2
        result['status'] = 'PASS_LOCAL_ORACLE_MAPPING_CONTRACTS'
    except BaseException as exc:
        result['status'] = 'FAILED'
        result['error_type'] = type(exc).__name__
        result['error'] = str(exc)
        (out / 'failure.txt').write_text(traceback.format_exc())
    finally:
        if admin:
            for name in reversed(result['created_schemas']):
                try:
                    with admin.cursor() as cursor:
                        cursor.execute('DROP USER ' + name + ' CASCADE')
                    result['dropped_schemas'].append(name)
                except Exception as exc:
                    result.setdefault('cleanup_errors', []).append(type(exc).__name__)
            admin.close()
        result['active_main_unchanged'] = active_before == connect.sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
        result['cleaned'] = set(result['created_schemas']) == set(result['dropped_schemas'])
        if not result['active_main_unchanged'] or not result['cleaned']:
            result['status'] = 'INCOMPLETE'
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'result': str(out / 'result.json'),
                      'checks': len(result['checks']), 'cleaned': result['cleaned']}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS_LOCAL_ORACLE_MAPPING_CONTRACTS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
