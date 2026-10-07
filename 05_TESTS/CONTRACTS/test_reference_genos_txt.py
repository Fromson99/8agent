"""Execute the exact one-file GENOS handoff in an isolated Git checkout."""
import ast
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.contracts import sha
from test_document_release import source


ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT / '08_DEPLOYMENT/GENOS/patches/GENOS_REFERENCE_MAIN_AUTO_20260929_R1.txt'


def test_exact_txt_apply_reapply_internal_run_and_rollback(tmp_path, term_glossary):
    checkout = tmp_path / 'actual-checkout'; checkout.mkdir()
    ignore = shutil.ignore_patterns('__pycache__', 'research', '*.pyc')
    for name in ('02_BACKEND/lawrag', '02_BACKEND/semantic_runtime', '02_BACKEND/ENGINES', '00_SYSTEM'):
        shutil.copytree(ROOT / name, checkout / name, ignore=ignore)
    (checkout / '06_TOOLS/COMMANDS').mkdir(parents=True)
    for name in ('06_TOOLS/pipeline.py', '06_TOOLS/COMMANDS/composed_build.py'):
        shutil.copy2(ROOT / name, checkout / name)
    for name in ('01_DATA', '03_FRONTEND', '04_EXPERIMENTS', '05_TESTS', '07_DOCS', '08_DEPLOYMENT', '09_ARTIFACTS', '90_RUNTIME', '99_ARCHIVE'):
        (checkout / name).mkdir(exist_ok=True)
    new_files = ['02_BACKEND/lawrag/pipeline/reference_resolution.py',
                 '02_BACKEND/semantic_runtime/reference_resolution_repository.py',
                 '02_BACKEND/semantic_runtime/reference_resolution_protocol.py',
                 '00_SYSTEM/SCHEMAS/reference-resolution-v1.schema.json']
    for name in new_files:
        (checkout / name).unlink()
    # Simulate the existing GENOS entrypoint before the new reference route.
    pipeline = checkout / '06_TOOLS/pipeline.py'
    text = pipeline.read_text(); lines = text.splitlines(keepends=True)
    for node in reversed(ast.parse(text).body):
        if isinstance(node, ast.If) and "['reference-resolution']" in ast.get_source_segment(text, node):
            del lines[node.lineno - 1:node.end_lineno]
    pipeline.write_text(''.join(lines))
    document = checkout / '02_BACKEND/lawrag/pipeline/document_release.py'
    document.write_text(document.read_text() + '\n# ONSITE_CUSTOM_MARKER_PRESERVED\n')
    before = {str(p.relative_to(checkout)): sha(p) for p in checkout.rglob('*') if p.is_file()}
    subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
    subprocess.run(['git', '-C', str(checkout), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(checkout), '-c', 'user.name=contract', '-c', 'user.email=contract@example.invalid',
                    'commit', '-qm', 'isolated existing checkout'], check=True)
    entrance = tmp_path / 'DEV'; entrance.symlink_to(checkout, target_is_directory=True)
    env = {**os.environ, 'DEPLOY_ROOT': str(entrance), 'GENOS_PYTHON': str(ROOT / '.venv/bin/python')}
    for key in list(env):
        if key.startswith('GENOS_') and key != 'GENOS_PYTHON': env.pop(key)
    def execute(*args):
        value = subprocess.run(['bash', str(TXT), *args], cwd=checkout, env=env,
                               capture_output=True, text=True, timeout=90)
        assert value.returncode == 0, value.stdout + value.stderr
        return value.stdout
    first = execute()
    assert 'EMBEDDED_CODE_HASH_PASS' in first and 'CODE_APPLIED' in first
    assert 'ONSITE_CUSTOM_MARKER_PRESERVED' in document.read_text()
    assert all((checkout / name).is_file() for name in new_files)
    assert 'CODE_ALREADY_APPLIED' in execute()
    receipt = next((checkout / '90_RUNTIME/HANDOFF/reference-main-20260929-r1').glob('*/receipt.json'))
    value = json.loads(receipt.read_text())
    assert value['code_root'] == str(checkout) and value['status'] == 'APPLIED_AND_IMPORT_VERIFIED'
    for name, row in value['files'].items(): assert sha(checkout / name) == row['after_sha256']
    # No GENOS access: patch all physical model I/O in child processes to scripted responses.
    hooks = tmp_path / 'mock-runtime'; hooks.mkdir()
    (hooks / 'sitecustomize.py').write_text('''import json,os,errno
from semantic_runtime import genos
from semantic_runtime.legal_agent.transport import GenosTransport
genos.request_json=lambda *args,**kwargs: {'data':[{'id':'synthetic-contract'}]}
async def fake(self,method,path,body,seconds,**kwargs):
    if method=='GET': return {'body_json':{'data':[{'id':'synthetic-contract'}]}}
    cases=json.loads(body['messages'][1]['content'])['view']['cases']
    rows=[{'case_id':c['case_id'],'selected_candidate_ids':[c['candidates'][0]['id']],
           'evidence_ids':['E1'],'abstain_reason':None,'explanation':'synthetic'} for c in cases]
    return {'status_code':200,'body_json':{'model':'synthetic-contract',
            'choices':[{'message':{'content':json.dumps({'cases':rows})}}],'usage':{'prompt_tokens':1,'completion_tokens':1}}}
GenosTransport._request=fake
def cross_mount(*args,**kwargs): raise OSError(errno.EXDEV,'synthetic separate NFS mount')
os.link=cross_mount
''')
    env.update(PYTHONPATH=str(hooks)+os.pathsep+str(checkout/'02_BACKEND'),
               GENOS_LLM_URL='http://127.0.0.1:1/v1', GENOS_LLM_MODEL='synthetic-contract')
    raw = source(tmp_path / 'synthetic.sqlite', [
        ('internal', '내규', ['관련 규정 제1조에 따른다.']),
        ('a', '가상규정A', ['첫 번째 후보']), ('b', '가상규정B', ['두 번째 후보'])])
    build_generation(raw, term_glossary, tmp_path / 'parent', serving=True)
    generation = tmp_path / 'parent/generation'
    parent_hash = sha(generation / 'navigation/navigation.sqlite')
    result = execute('run', str(generation))
    assert 'CANDIDATE_VERIFIED' in result and 'INTERNAL_MODEL_BOUND model=synthetic-contract' in result
    assert sha(generation / 'navigation/navigation.sqlite') == parent_hash
    work = next((checkout / '90_RUNTIME/REFERENCE').iterdir())
    with sqlite3.connect(work / 'review/review.sqlite') as db:
        assert db.execute("SELECT count(*) FROM case_record WHERE state='APPROVED'").fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM model_attempt').fetchone()[0] == 1
    assert not (checkout / '01_DATA/generations/CURRENT.json').exists()
    execute('run', str(generation))
    with sqlite3.connect(work / 'review/review.sqlite') as db:
        assert db.execute('SELECT count(*) FROM model_attempt').fetchone()[0] == 1
    execute('rollback', str(receipt))
    for name, expected in before.items(): assert sha(checkout / name) == expected
    assert all(not (checkout / name).exists() for name in new_files)
