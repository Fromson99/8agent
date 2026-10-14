"""Exact emailed TXT: failed R8 -> onsite-shaped mock generation -> R10 replay."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import re
import types
import uuid
import zipfile
import zlib

from lawrag.core.legal_coordinate import find_coordinates
from lawrag.pipeline.term_generation import build_generation

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_oneclick_20261007_r10'
R8 = OUT.with_name('cm_shortcut_oneclick_20261007_r8')
NAME = 'GENOS_CM_ONECLICK_20261007_R10'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module():
    # Historical deliveries must be checked against their own sealed installer.
    text = (OUT/(NAME+'_RUN.txt')).read_text()
    packed = re.search(r"raw=zlib.decompress\(base64.b64decode\('([^']+)'\)\)", text)[1]
    bundle = json.loads(zlib.decompress(base64.b64decode(packed)))
    value = types.ModuleType('oneclick_r10')
    exec(compile(base64.b64decode(bundle['code']), 'sealed_r10.py', 'exec'), value.__dict__)
    return value


def test_all_sealed_recipe_engine_pins_and_source_scope():
    spec = json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    one = module()
    package = json.loads(one.blob(spec, spec['package_sha256']))
    assert package['source_binding_policy'] == 'target-selected-document-article-v1'
    assert 'built_against' not in package and len(package['cases']) == 51
    assert len(spec['r8_upgrades']) == len(spec['recipes']) == 216
    for recipe in spec['recipes'].values():
        after = spec['inventories'][recipe['after']]
        pipeline = json.loads(one.blob(spec, after['00_SYSTEM/PIPELINE.json']))
        for engine in pipeline['engines'].values():
            raw = one.blob(spec, after[engine['manifest']]); value = json.loads(raw)
            assert sha(raw) == engine['sha256']
            assert all(after[path] == pin for path, pin in value['files'].items())
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as archive:
        assert archive.testzip() is None
        assert all(Path(n).suffix.lower() not in {'.js', '.jsx', '.mjs', '.cjs'} for n in archive.namelist())
        assert archive.read(NAME+'_RUN.txt') == (OUT/(NAME+'_RUN.txt')).read_bytes()


def test_exact_txt_failed_r8_upgrade_field_names_new_hashes_and_replay(tmp_path, term_glossary):
    prefix = tmp_path; (prefix/'.genos-offline-validation').write_text('offline fixture')
    root = prefix/'DEV'; root.mkdir(); transfer = root/'TRANSFER'; transfer.mkdir()
    spec = json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    tests = json.loads(gzip.decompress((R8/'TEST_BASES.json.gz').read_bytes()))
    basis = next(b for b in tests['bases'] if 'SYSTEM_LOGGING' in b['label'] and '/nfs-list-r1' in b['label'])
    payload = {p: base64.b64decode(tests['blobs'][pin]) for p, pin in basis['files'].items()}
    for name, raw in payload.items():
        path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    package = json.loads((OUT/'CM51_SOURCE_PACKAGE.json').read_bytes())
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
            meta = {'document_title': Path(filename).stem, 'file_name': filename,
                    'relative_path': 'external/financial_team/krx/'+name+'/'+filename,
                    'folder_names': ['external', 'financial_team', 'krx', name], 'document_role': 'body'}
            db.execute('INSERT INTO document VALUES(?,?,?,?)', (did, display, fingerprint,
                       json.dumps({'document_metadata': meta}, ensure_ascii=False)))
            for i, key in enumerate(sorted(coordinates)):
                surface = key.split(':', 1)[1]; coordinate = find_coordinates(surface)[0].coordinate
                unit = {'id': str(i), 'family': 'kr_article', 'surface': surface, 'title': '모의 조문',
                        'span': [i, i+1], 'coordinate_key': key, 'coordinate_scope': 'body',
                        'legal_coordinate': coordinate.as_dict()}
                text = surface+' 모의 현장 구조화 본문. 실제 법령 내용을 나타내지 않는다. 영업일에 처리한다.'
                db.execute('INSERT INTO source_unit VALUES(?,?,?,?)', (did, str(i), None, json.dumps(unit, ensure_ascii=False)))
                db.execute('INSERT INTO source_block VALUES(?,?,?,?,?,?)', (did, str(i), str(i), text, fingerprint, '{}'))
    built = prefix/'built'
    build_generation(source, term_glossary, built, serving=True, fulltext_granularity='unit')
    generation = prefix/Path(spec['paths']['generation']).relative_to('/')
    generation.mkdir(parents=True)
    for path in (built/'generation').rglob('*'):
        target = generation/path.relative_to(built/'generation')
        if path.is_dir():
            target.mkdir(exist_ok=True)
        else:
            os.link(path, target)
    before = {p.relative_to(generation).as_posix(): sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    runtime = prefix/Path(spec['paths']['runtime']).relative_to('/')
    case = runtime/'case-memory'; case.mkdir(parents=True); database = case/'cases-v4.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE keep_fixture(value TEXT)'); db.execute("INSERT INTO keep_fixture VALUES('preserve')")
    remote = prefix/'remote.git'; subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
    git('init', '-q'); git('add', '-f', '--', *payload)
    git('-c', 'user.name=Offline fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'known field fixture')
    git('remote', 'add', 'origin', str(remote))
    env = {**os.environ, 'PATH': str(ROOT/'.venv/bin')+':'+os.environ['PATH'], 'GENOS_AUTO_WARMUP': '0',
           'AD_WORKER_ENABLED': '0', 'GENOS_SYSTEM_LOG_DIR': str(prefix/'logs'), 'GENOS_LOG_SPOOL_DIR': str(prefix/'spool')}
    for key in list(env):
        if key.startswith('CM_') or key in ('GENOS_GENERATION', 'GENOS_RUNTIME_DIR', 'GENOS_STATE_DIR', 'GENOS_DEV_ROOT', 'GENOS_DEV', 'GENOS_PYTHON_DIR'):
            env.pop(key)
    oldrun = transfer/'GENOS_CM_ONECLICK_20261007_R8_RUN.txt'; oldrun.write_bytes((R8/oldrun.name).read_bytes())
    def execute(run):
        result = subprocess.run(['bash', str(run), '--validation-prefix', str(prefix)], cwd=prefix,
                                env=env, capture_output=True, text=True, timeout=180)
        log = OUT/('RUN-'+uuid.uuid4().hex+'.log.gz')
        log.write_bytes(gzip.compress((result.stdout+result.stderr).encode(), mtime=0))
        return result
    failed = execute(oldrun)
    assert failed.returncode == 1
    status = json.loads((transfer/'cm-oneclick-r8/STATUS.json').read_bytes())
    assert status['state'] == 'FAILED'
    assert 'source document version missing or ambiguous' in (transfer/'cm-oneclick-r8/package-check.log').read_text()
    old_status = (transfer/'cm-oneclick-r8/STATUS.json').read_bytes()
    with zipfile.ZipFile(OUT/(NAME+'.zip')) as archive:
        archive.extractall(transfer)
    run = transfer/(NAME+'_RUN.txt')
    for replay in range(2):
        result = execute(run)
        assert result.returncode == 0, result.stdout+result.stderr
        status = json.loads((transfer/'cm-oneclick-r10/STATUS.json').read_bytes())
        assert status['state'] == 'READY_FOR_REVISION_DEPLOYMENT' and status['model_calls'] == 0
        assert status['code_serving_revision'] is None and status['workflow_verified'] is False
        checked = json.loads((transfer/'cm-oneclick-r10/DATA_CHECKED.json').read_bytes())
        assert checked['cases'] == 51 and checked['source_entries'] == 98
        assert len(checked['resolved_documents']) == 21
        assert all(d['document_name'].startswith('external > financial_team > ') for d in checked['resolved_documents'])
        receipt = json.loads((transfer/'cm-oneclick-r10/CM51_REGISTERED.json').read_bytes())
        assert len(receipt['records']) == 51 and receipt['source_binding_policy'] == 'target-selected-document-article-v1'
        assert receipt.get('already_imported', False) == bool(replay)
        with sqlite3.connect(database) as db:
            assert db.execute('SELECT value FROM keep_fixture').fetchone()[0] == 'preserve'
            assert db.execute('SELECT count(*) FROM sw_knowledge').fetchone()[0] == 51
        assert (transfer/'cm-oneclick-r8/STATUS.json').read_bytes() == old_status
        assert git('rev-parse', 'HEAD') == subprocess.run(['git', '--git-dir', str(remote), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    assert before == {p.relative_to(generation).as_posix(): sha(p.read_bytes()) for p in generation.rglob('*') if p.is_file()}
    lib = module().library(spec); changed = root/'02_BACKEND/lawrag/pipeline/shortcut_package.py'
    changed.write_bytes(changed.read_bytes()+b'\n# unknown later field change\n')
    try:
        module().verify_output(root, spec, lib, json.loads((root/'00_SYSTEM/GENOS_SERVING_PATHS.json').read_bytes()))
    except ValueError:
        pass
    else:
        raise AssertionError('later unknown code change accepted')
    record = {'cases': 51, 'entries': 98, 'documents': 21, 'exact_TXT_runs': 2,
              'failed_R8_reproduced': True, 'R8_upgrade': True, 'field_display_names': True,
              'different_input_and_structure_hashes': True, 'same_checkout_commit_gate_local_remote_push': True,
              'replay_no_duplicate': True, 'existing_state_and_failure_history_preserved': True,
              'source_generation_unchanged': True, 'unknown_code_change_rejected': True,
              'model_calls': 0, 'GENOS_field_verified': False, 'real_remote_push': False,
              'RUN_sha256': sha(run.read_bytes()), 'working_source_sha256': sha((ROOT/'06_TOOLS/COMMANDS/genos_cm_oneclick.py').read_bytes())}
    (OUT/'END_TO_END_VERIFIED.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
