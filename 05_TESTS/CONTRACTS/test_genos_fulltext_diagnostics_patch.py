"""Exercise the delivered TXT, constrained hash repair and report preservation."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'08_DEPLOYMENT/GENOS/patches'
PATCH=BASE/'fulltext_diagnostics_20260928_r1'
PRE=ROOT/'90_RUNTIME/diagnostics/fulltext-20260928-r1-preimage'
TXT=BASE/'GENOS_FULLTEXT_DIAGNOSTICS_20260928_R1_APPLY.txt'
REPORT='02_BACKEND/semantic_runtime/request_report.py'
WORKFLOW='02_BACKEND/semantic_runtime/legal_agent/workflow_relations_tools.py'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def commit(root):
    subprocess.run(['git','-C',str(root),'add','00_SYSTEM','02_BACKEND','other.py'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                    '-c','core.hooksPath=/dev/null','commit','-qm','fixture code'],check=True)


@pytest.fixture
def installed(tmp_path,monkeypatch):
    root=tmp_path/'DEV';root.mkdir();package=tmp_path/'patch';shutil.copytree(PATCH,package)
    spec=json.loads((package/'PATCH_MANIFEST.json').read_bytes())
    for name in spec['files']:
        dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((PRE/name).read_bytes())
    (root/'other.py').write_text('OTHER_UNCHANGED = True\n')
    files={name:sha((root/name).read_bytes()) for name in [*spec['files'],'other.py']}
    # Simulate a new shipped report with older (also shipped) selected engine pins.
    old=(BASE/'latency_20260928_r2/payload'/REPORT).read_bytes();files[REPORT]=sha(old)
    engines={}
    for index in range(2):
        name=f'02_BACKEND/ENGINES/fixture{index}.json';dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps({'files':files},indent=2)+'\n')
        engines[str(index)]={'manifest':name,'sha256':sha(dest.read_bytes())}
    schema=root/'00_SYSTEM/schema.json';schema.parent.mkdir();schema.write_text('{}\n')
    (root/'00_SYSTEM/PIPELINE.json').write_text(json.dumps({'engines':engines,
        'contracts':{'fixture':{'schema_path':'00_SYSTEM/schema.json','schema_sha256':sha(schema.read_bytes())}},
        'profiles':{'untouched':731}},indent=2)+'\n')
    subprocess.run(['git','init','-q',str(root)],check=True);commit(root)
    implementation=module('fulltext_apply_fixture',package/'apply.py');monkeypatch.setattr(implementation,'PATCH',package)
    monkeypatch.setattr(sys,'argv',['apply.py','--deploy-root',str(root)])
    return root,package,implementation


def snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.parts and 'TRANSFER' not in p.parts}


def repin(root):
    config=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
    for engine in config['engines'].values():
        path=root/engine['manifest'];manifest=json.loads(path.read_bytes())
        manifest['files'][REPORT]=sha((root/REPORT).read_bytes());path.write_text(json.dumps(manifest)+'\n')
        engine['sha256']=sha(path.read_bytes())
    (root/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(config)+'\n')


def test_final_standalone_txt_repairs_all_pins_reapplies_commits_and_rolls_back(installed,tmp_path):
    root,package,implementation=installed;before=snapshot(root)
    env={**os.environ,'DEPLOY_ROOT':str(root),'PYTHON_BIN':sys.executable,'TMPDIR':str(tmp_path),'MODE':'apply'}
    def execute():return subprocess.run(['bash',str(TXT)],env=env,capture_output=True,text=True)
    first=execute();assert first.returncode==0,first.stdout+first.stderr
    assert first.stdout.count('KNOWN_REPORT_PIN_REPAIR')==2 and 'BACKUP_READY' in first.stdout
    config=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes());assert config['profiles']=={'untouched':731}
    for engine in config['engines'].values():
        path=root/engine['manifest'];assert sha(path.read_bytes())==engine['sha256']
        assert json.loads(path.read_bytes())['files'][REPORT]==sha((root/REPORT).read_bytes())
    assert b'_FULLTEXT_DIAGNOSTIC_FIELD_NAMES' in (root/REPORT).read_bytes()
    second=execute();assert second.returncode==0 and 'ALREADY_APPLIED' in second.stdout
    state=root/'TRANSFER/fulltext-diagnostics-20260928-r1';backups=list(state.glob('backup-*'));assert len(backups)==1
    env['MODE']='code-only';dirty=execute();assert dirty.returncode!=0 and 'uncommitted' in dirty.stdout
    commit(root);clean=execute();assert clean.returncode==0 and 'CODE_CHECK PASS' in clean.stdout,clean.stdout+clean.stderr
    env.update(MODE='rollback',ROLLBACK_FROM=str(backups[0]));restored=execute()
    assert restored.returncode==0 and 'ROLLED_BACK' in restored.stdout
    assert snapshot(root)==before
    logs=list(tmp_path.glob('genos-fulltext-diagnostics-r1-*.log'));assert len(logs)==5
    assert sum('FINISHED status=0' in p.read_text() for p in logs)==4


@pytest.mark.parametrize('style',['comments','pinned_extension'])
def test_report_preserves_approved_comments_or_valid_pinned_onsite_features(installed,style):
    root,package,implementation=installed
    marker='# 현장 수정 보존\r\n'.encode();raw=marker+(root/REPORT).read_bytes().replace(b'\n',b'\r\n')
    if style=='pinned_extension':raw+=b'\r\nONSITE_REPORT_FEATURE = 731\r\n'
    (root/REPORT).write_bytes(raw)
    if style=='pinned_extension':repin(root)
    implementation.main();after=(root/REPORT).read_bytes()
    assert after.startswith(marker)
    if style=='pinned_extension':assert b'ONSITE_REPORT_FEATURE = 731' in after
    ast.parse(after,feature_version=(3,11))


@pytest.mark.parametrize('kind',['unknown_report','unrelated_code','manifest','schema','asset','unsupported_search'])
def test_unrecognized_integrity_problems_fail_before_target_writes(installed,kind):
    root,package,implementation=installed
    target={'unknown_report':root/REPORT,'unrelated_code':root/'other.py',
            'manifest':root/'02_BACKEND/ENGINES/fixture0.json','schema':root/'00_SYSTEM/schema.json',
            'asset':package/'REPORT_CATALOG.json','unsupported_search':root/'02_BACKEND/semantic_runtime/fulltext.py'}[kind]
    with target.open('ab') as stream:stream.write(b'\nUNKNOWN_BEHAVIOR = 731\n' if kind=='unknown_report' else b'\n# changed\n')
    before=snapshot(root)
    with pytest.raises(ValueError):implementation.main()
    assert snapshot(root)==before


def test_apply_failure_restores_original_code_and_mismatched_pins(installed,monkeypatch):
    root,package,implementation=installed;before=snapshot(root);original=implementation.atomic;failed=False
    def fail_once(path,data):
        nonlocal failed
        if path==root/REPORT and not failed:failed=True;raise OSError('simulated write failure')
        original(path,data)
    monkeypatch.setattr(implementation,'atomic',fail_once)
    with pytest.raises(OSError):implementation.main()
    assert snapshot(root)==before


def test_rollback_rejects_later_edits(installed):
    root,package,implementation=installed;implementation.main()
    with (root/REPORT).open('ab') as stream:stream.write(b'\n# later onsite edit\n')
    before=snapshot(root);backup=next((root/'TRANSFER/fulltext-diagnostics-20260928-r1').glob('backup-*'))
    with pytest.raises(ValueError,match='rollback refused'):implementation.rollback(root,backup)
    assert snapshot(root)==before


@pytest.mark.parametrize('version',['latency_20260928_r1','latency_20260928_r2','relation_wait_20260928_r1',
                                    'team_request_logs_20260928_r1','thinking_log_20260928_r2'])
def test_old_report_transform_preserves_other_functions_and_is_idempotent(version):
    fields=module('report_fields_fixture',PATCH/'report_fields.py');raw=(BASE/version/'payload'/REPORT).read_bytes()
    old=ast.parse(raw);after=fields.transform(raw);new=ast.parse(after)
    for node in old.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name not in {'_LiveLog','format_readable_report'}:
            assert ast.dump(node,include_attributes=False)==ast.dump(next(n for n in new.body if getattr(n,'name',None)==node.name),include_attributes=False)
    assert fields.transform(after)==after


def test_r2_search_variant_preserves_non_search_behavior(installed):
    root,package,implementation=installed;spec=json.loads((package/'PATCH_MANIFEST.json').read_bytes())
    (root/WORKFLOW).write_bytes((BASE/'latency_20260928_r2/payload'/WORKFLOW).read_bytes())
    config=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
    for entry in config['engines'].values():
        path=root/entry['manifest'];manifest=json.loads(path.read_bytes());manifest['files'][WORKFLOW]=sha((root/WORKFLOW).read_bytes())
        path.write_text(json.dumps(manifest)+'\n');entry['sha256']=sha(path.read_bytes())
    (root/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(config)+'\n')
    before=ast.parse((root/WORKFLOW).read_bytes());implementation.main();after=ast.parse((root/WORKFLOW).read_bytes())
    def methods(tree):return {n.name:ast.dump(n,include_attributes=False) for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='RelationsTools' for n in c.body if isinstance(n,ast.FunctionDef) and n.name!='search'}
    assert methods(before)==methods(after)
    assert sha((root/WORKFLOW).read_bytes())==spec['files'][WORKFLOW]['variants'][0]['new_sha256']


def test_new_diagnostics_reach_live_and_summary_without_arbitrary_text(tmp_path):
    from semantic_runtime import observability as obs
    from semantic_runtime.request_report import live_log,format_readable_report,capture_events
    logger=obs.get_logger('fulltext-report-fields')
    with capture_events('req-fulltext') as events,live_log(tmp_path,'req-fulltext') as (path,handler):
        with obs.context(request_id='req-fulltext'):
            obs.event(logger,'fulltext.sql.timings',sql_fetch_ms=83000.5,sql_fetch_cpu_ms=124,
                      active_searches_peak=3,thread_non_cpu_ms=82800.5,search_id='b'*32,
                      sql_status='completed',cache_size=-2000,source_json_decode_ms='private source',
                      scheduler_wait_ms=float('inf'))
        assert handler.writer.drain(2);text=path.read_text()
    summary=format_readable_report({'service_events':events})
    for output in (text,summary):
        assert 'sql_fetch_ms=83000.5' in output and 'sql_fetch_cpu_ms=124' in output
        assert 'active_searches_peak=3' in output and 'thread_non_cpu_ms=82800.5' in output
        assert 'cache_size=-2000' in output and 'sql_status=completed' in output
        assert 'private source' not in output and 'scheduler_wait_ms=inf' not in output
