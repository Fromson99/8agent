"""R11 delivery: exact field command order, preserved budget and strict drift checks."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import types
import zipfile
import zlib

import pytest

from lawrag.core.legal_coordinate import find_coordinates
from lawrag.pipeline.term_generation import build_generation

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r11'
R8 = OUT.with_name('cm_shortcut_oneclick_20261007_r8')
R10 = OUT.with_name('cm_shortcut_oneclick_20261007_r10')
BUDGET = OUT.with_name('investigation_budget_20261007_r1')
NAME = 'GENOS_CM_ONECLICK_20261007_R11'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def sealed_module():
    text = (OUT/(NAME+'_RUN.txt')).read_text()
    packed = re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)", text)[1]
    bundle = json.loads(zlib.decompress(base64.b64decode(packed)))
    value = types.ModuleType('sealed_r11')
    exec(compile(base64.b64decode(bundle['code']), 'sealed_r11.py', 'exec'), value.__dict__)
    return value, bundle['spec']


def field_fixture(prefix, glossary, spec, *, plain_body_title=None):
    (prefix/'.genos-offline-validation').write_text('offline fixture')
    root = prefix/'DEV'; root.mkdir(); transfer = root/'TRANSFER'; transfer.mkdir()
    tests = json.loads(gzip.decompress((R8/'TEST_BASES.json.gz').read_bytes()))
    basis = next(b for b in tests['bases'] if 'SYSTEM_LOGGING' in b['label'] and '/nfs-list-r1' in b['label'])
    payload = {p: base64.b64decode(tests['blobs'][pin]) for p, pin in basis['files'].items()}
    for name, raw in payload.items():
        path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    package = json.loads((R10/'CM51_SOURCE_PACKAGE.json').read_bytes())
    references = {}
    for case in package['cases']:
        for entry in case['entries']:
            references.setdefault(entry['document_name'], set()).add(entry['coordinate_key'])
    source = prefix/'MOCK_SOURCE.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('CREATE TABLE document(document_id TEXT PRIMARY KEY,name TEXT,source_artifact_sha256 TEXT,json TEXT);'
                        'CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);'
                        'CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT);')
        for name, coordinates in sorted(references.items()):
            fingerprint = sha(('MOCK onsite input '+name).encode()); did = fingerprint[:16]
            filename = name+'_전문.hwpx'
            display = 'external > financial_team > krx > '+name+' > '+Path(filename).stem
            metadata = {'document_title': Path(filename).stem, 'file_name': filename,
                'relative_path': 'external/financial_team/krx/'+name+'/'+filename,
                'folder_names': ['external', 'financial_team', 'krx', name], 'document_role': 'body'}
            if name==plain_body_title:
                display=name+' 본문'
                metadata={'document_title':display,'file_name':display+'.xml','document_role':'body'}
            db.execute('INSERT INTO document VALUES(?,?,?,?)', (did, display, fingerprint,
                json.dumps({'document_metadata': metadata}, ensure_ascii=False)))
            for i, key in enumerate(sorted(coordinates)):
                surface = key.split(':', 1)[1]; coordinate = find_coordinates(surface)[0].coordinate
                unit = {'id': str(i), 'family': 'kr_article', 'surface': surface, 'title': '모의 조문',
                    'span': [i, i+1], 'coordinate_key': key, 'coordinate_scope': 'body',
                    'legal_coordinate': coordinate.as_dict()}
                text = surface+' 모의 현장 본문. 실제 법령 내용을 나타내지 않는다. 영업일에 처리한다.'
                db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', (did, str(i), None, json.dumps(unit, ensure_ascii=False)))
                db.execute('INSERT INTO source_block VALUES(?,?,?,?,?,?)', (did, str(i), str(i), text, fingerprint, '{}'))
    build_generation(source, glossary, prefix/'built', serving=True, fulltext_granularity='unit')
    generation = prefix/Path(spec['paths']['generation']).relative_to('/')
    generation.mkdir(parents=True)
    for path in (prefix/'built/generation').rglob('*'):
        target = generation/path.relative_to(prefix/'built/generation')
        if path.is_dir():target.mkdir(exist_ok=True)
        else:os.link(path, target)
    runtime = prefix/Path(spec['paths']['runtime']).relative_to('/')
    case = runtime/'case-memory';case.mkdir(parents=True);database = case/'cases-v4.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE keep_fixture(value TEXT)');db.execute("INSERT INTO keep_fixture VALUES('preserve')")
    remote = prefix/'remote.git';subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
    git('init', '-q');git('add', '-f', '--', *payload)
    git('-c', 'user.name=Offline fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'known field fixture')
    git('remote', 'add', 'origin', str(remote))
    env = {**os.environ, 'PATH': str(ROOT/'.venv/bin')+':'+os.environ['PATH'],
        'GENOS_AUTO_WARMUP': '0', 'AD_WORKER_ENABLED': '0',
        'GENOS_SYSTEM_LOG_DIR': str(prefix/'logs'), 'GENOS_LOG_SPOOL_DIR': str(prefix/'spool'),
        'GENOS_BUDGET_LOG_ROOT': str(prefix/'budget-logs'), 'GENOS_DEV_ROOT': str(root)}
    for key in list(env):
        if key.startswith('CM_') or key in ('GENOS_GENERATION', 'GENOS_RUNTIME_DIR', 'GENOS_STATE_DIR',
            'GENOS_DEV', 'GENOS_PYTHON_DIR', 'GENOS_LLM_URL', 'GENOS_LLM_SERVING_ID', 'GENOS_LLM_KEY'):
            env.pop(key)
    return root,transfer,generation,database,remote,git,env


def test_sealed_recipes_budget_variants_and_zip_integrity(tmp_path):
    module,spec = sealed_module()
    text=(OUT/(NAME+'_RUN.txt')).read_text()
    packed=re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)",text)[1]
    installer=base64.b64decode(json.loads(zlib.decompress(base64.b64decode(packed)))['code'])
    assert sha(installer) == json.loads((OUT/'HANDOFF.json').read_bytes())['oneclick_source_sha256']
    old = json.loads(gzip.decompress((R10/'PATCH_SPEC.json.gz').read_bytes()))
    assert spec['recipes'] == old['recipes'] and spec['package_sha256'] == old['package_sha256']
    assert len(spec['r8_upgrades']) == len(spec['r10_upgrades']) == 216
    budget,policy = module.budget_library(spec)
    for recipe in spec['recipes'].values():
        after = spec['inventories'][recipe['after']]
        payload = {path: module.blob(spec,pin) for path,pin in after.items() if path=='service.py'}
        transformed = budget.transform(payload['service.py'],policy)
        assert module.without_budget(transformed,spec) == payload['service.py']
        pipeline = json.loads(module.blob(spec,after['00_SYSTEM/PIPELINE.json']))
        for engine in pipeline['engines'].values():
            raw = module.blob(spec,after[engine['manifest']]);assert sha(raw)==engine['sha256']
            value=json.loads(raw);assert all(after[path]==pin for path,pin in value['files'].items())
            assert 'service.py' not in value['files']
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as archive:
        assert archive.testzip() is None
        assert archive.read(NAME+'_RUN.txt') == (OUT/(NAME+'_RUN.txt')).read_bytes()
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in archive.namelist())
    subprocess.run([str(ROOT/'.venv/bin/python'), '-m', 'zipfile', '-e', str(OUT/(NAME+'.zip')), str(tmp_path)], check=True)
    subprocess.run(['sha256sum','-c',NAME+'_SHA256SUMS.txt'], cwd=tmp_path, check=True)
    subprocess.run(['bash','-n',str(tmp_path/(NAME+'_RUN.txt'))], check=True)


@pytest.mark.parametrize('basis',['r8-budget','r10-budget','plain'])
def test_exact_field_sequence_recovery_preservation_and_replay(tmp_path,term_glossary,basis):
    module,spec = sealed_module()
    root,transfer,generation,database,remote,git,env = field_fixture(tmp_path,term_glossary,spec)
    before_generation = {p.relative_to(generation).as_posix():sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    main_pointer = (ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()
    history = {};transcript=[]
    def run(script,*args,success=True):
        result = subprocess.run(['bash',str(script),*map(str,args)], cwd=tmp_path, env=env,
            capture_output=True,text=True,timeout=180)
        transcript.append(script.name+' '+str(args)+'\n'+result.stdout+result.stderr)
        if (result.returncode==0)!=success:
            (OUT/('FAIL-'+basis+'.log.gz')).write_bytes(gzip.compress('\n'.join(transcript).encode(),mtime=0))
        assert (result.returncode==0)==success,transcript[-1]
        return result
    if basis!='plain':
        oldrun=transfer/'GENOS_CM_ONECLICK_20261007_R8_RUN.txt';oldrun.write_bytes((R8/oldrun.name).read_bytes())
        run(oldrun,'--validation-prefix',tmp_path,success=False)
        assert 'source document version missing or ambiguous' in (transfer/'cm-oneclick-r8/package-check.log').read_text()
        r10run=transfer/'GENOS_CM_ONECLICK_20261007_R10_RUN.txt';r10run.write_bytes((R10/r10run.name).read_bytes())
        if basis=='r10-budget':run(r10run,'--validation-prefix',tmp_path)
        budget_run=BUDGET/'GENOS_INVESTIGATION_BUDGET_20261007_R1_RUN.txt'
        run(budget_run,'check');run(budget_run,'apply');run(budget_run,'verify')
        budget_service=(root/'service.py').read_bytes()
        assert sha(budget_service)=='2cfb9c6e36c0a80ffd8ce1409060d4666c074479be699028ebe28272827d86af'
        manifest_before_r10=(root/'CODE_MANIFEST.json').read_bytes()
        if basis=='r8-budget':
            run(r10run,'--validation-prefix',tmp_path,success=False)
            assert 'R8 code differs from the verified upgrade inventory' in transcript[-1]
            assert (root/'CODE_MANIFEST.json').read_bytes()==manifest_before_r10
        for folder in ('cm-oneclick-r8','cm-oneclick-r10'):
            for p in (transfer/folder).rglob('*'):
                if p.is_file():history[p]=sha(p.read_bytes())
        for p in (tmp_path/'budget-logs').rglob('*'):
            if p.is_file():history[p]=sha(p.read_bytes())
        budget_meta=json.loads((root/'CODE_MANIFEST.json').read_bytes())['investigation_budget_settings']
        # Self-consistent but unapproved extra edits are rejected before writing.
        saved=(root/'service.py').read_bytes();saved_manifest=(root/'CODE_MANIFEST.json').read_bytes()
        drift=saved+b'\n# unapproved field change\n';(root/'service.py').write_bytes(drift)
        edited=json.loads(saved_manifest)
        for row in edited['files']:
            if row['path']=='service.py':row.update(sha256=sha(drift),bytes=len(drift))
        for row in edited.get('required_files',[]):
            if isinstance(row,dict) and row['path']=='service.py':row['sha256']=sha(drift)
        (root/'CODE_MANIFEST.json').write_bytes(module.encoded(edited))
        with pytest.raises(ValueError):module.prepare(root,spec,module.library(spec),json.loads((root/module.CONFIG).read_bytes()))
        assert (root/'service.py').read_bytes()==drift
        (root/'service.py').write_bytes(saved);(root/'CODE_MANIFEST.json').write_bytes(saved_manifest)
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as archive:archive.extractall(transfer)
    for replay in range(2):
        result=run(transfer/(NAME+'_RUN.txt'),'--validation-prefix',tmp_path)
        status=json.loads((transfer/'cm-oneclick-r11/STATUS.json').read_bytes())
        assert status['state']=='READY_FOR_REVISION_DEPLOYMENT' and status['model_calls']==0
        assert status['code_serving_revision'] is None and status['workflow_verified'] is False
        assert Path(status['sys_executable']).resolve()==(ROOT/'.venv/bin/python').resolve()
        manifest=json.loads((root/'CODE_MANIFEST.json').read_bytes())
        if basis!='plain':
            assert (root/'service.py').read_bytes()==budget_service
            assert manifest['investigation_budget_settings']==budget_meta
            assert manifest['cm_oneclick']['preserved_investigation_budget']==budget_meta
            budget,policy=module.budget_library(spec);budget.local_verification(budget_service,policy)
        else:assert 'investigation_budget_settings' not in manifest
        checked=json.loads((transfer/'cm-oneclick-r11/DATA_CHECKED.json').read_bytes())
        assert checked['cases']==51 and checked['source_entries']==98 and len(checked['resolved_documents'])==21
        receipt=json.loads((transfer/'cm-oneclick-r11/CM51_REGISTERED.json').read_bytes())
        assert len(receipt['records'])==51
        assert receipt.get('already_imported',False)==bool(replay or basis=='r10-budget')
        with sqlite3.connect(database) as db:
            assert db.execute('SELECT value FROM keep_fixture').fetchone()[0]=='preserve'
            assert db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0]==51
        assert git('rev-parse','HEAD')==subprocess.run(['git','--git-dir',str(remote),'rev-parse','HEAD'],
            check=True,capture_output=True,text=True).stdout.strip()
        logfile=Path(re.search(r'^EXIT=0 LOG=(.+)$',result.stdout,re.M)[1])
        assert json.loads(Path(str(logfile)+'.EXIT_STATUS.json').read_bytes())['exit_code']==0
        assert all(p.exists() and sha(p.read_bytes())==pin for p,pin in history.items())
    assert before_generation=={p.relative_to(generation).as_posix():sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    assert (ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()==main_pointer
    (OUT/('RUN-'+basis+'.log.gz')).write_bytes(gzip.compress('\n'.join(transcript).encode(),mtime=0))
    (OUT/('VERIFIED-'+basis+'.json')).write_bytes(module.encoded({'basis':basis,'runs':2,'cases':51,'entries':98,
        'documents':21,'budget_preserved':basis!='plain','old_failure_and_budget_backups_preserved':True,
        'same_checkout_commit_generation_gate_local_remote_push':True,'replay_no_duplicates':True,
        'unknown_self_consistent_code_rejected':basis!='plain','generation_unchanged':True,
        'local_main_pointer_unchanged':True,'model_calls':0,'GENOS_field_verified':False,
        'RUN_sha256':sha((OUT/(NAME+'_RUN.txt')).read_bytes())}))
