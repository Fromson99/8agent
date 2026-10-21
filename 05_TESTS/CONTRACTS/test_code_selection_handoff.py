"""Execute the exact mailed ZIP/TXT against a disposable committed checkout."""
import json
import importlib.util
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from semantic_runtime.contracts import sha, write

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'08_DEPLOYMENT/GENOS/handoffs/code_selection_20261021_r1'
NAME='GENOS_DEV_SEARCH_SELECTION_20261021_R1'


@pytest.mark.parametrize('configured',[False,True])
def test_final_zip_commands(tmp_path,term_glossary,monkeypatch,configured):
    from test_latest_internal_versions import docx
    from lawrag.pipeline import genos_corpus,genos_stages,document_release
    from lawrag.pipeline.term_generation import build_generation
    selected=ROOT/'08_DEPLOYMENT/RELEASES/multiturn-structured-scope-20261021-r1/code'
    monkeypatch.setenv('STRUCTURE_RECIPE_VLM','off')
    raw=tmp_path/'RAW'
    docx(raw/'internal/모의규정(20240101).docx','영업일은 은행이 영업하는 날을 말한다. 이전 내용')
    docx(raw/'internal/모의규정(20250101).docx','영업일은 은행이 영업하는 날을 말한다. 최신 내용')
    inventory,_=genos_corpus.collect(raw,only_internal=True,skip_invalid=True,emit=lambda _:None)
    stores=[]
    for row in inventory['files']:
        folder,_=genos_stages.structure(row,inventory,tmp_path,{'synthetic':'no-model'},30,lambda _:None)
        stores.append(folder/'source.sqlite')
    merged=document_release.merge_sources(stores,tmp_path/'merged')
    build_generation(merged,term_glossary,tmp_path/'nfs',serving=True,
        storage_profile='compact-v2',fulltext_granularity='unit',audit_profile='factorized-v1')
    g=tmp_path/'nfs/generation';runtime=tmp_path/'nfs/runtime';runtime.mkdir()
    before_data={str(p.relative_to(g)):sha(p) for p in g.rglob('*') if p.is_file()}
    checkout=tmp_path/'workspace';shutil.copytree(selected,checkout)
    # Preserve current independent fixes and use the same compiler as generation
    # construction. Revert only this patch in the synthetic pre-install checkout.
    module_spec=importlib.util.spec_from_file_location('handoff_runner',PACKAGE/'runner.py')
    runner=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(runner)
    registry,required=runner.pins(ROOT)
    for n in [*required,'00_SYSTEM/PIPELINE.json']:
        dest=checkout/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
    audit=ROOT/'09_ARTIFACTS/AUDITS/20261021-code-local-selection'
    old=json.loads((audit/'BEFORE.json').read_text())['files']
    for n in json.loads((PACKAGE/'PATCH_SPEC.json').read_text())['payload']:
        (checkout/n).write_bytes(gzip.decompress((audit/'before'/(n+'.gz')).read_bytes()))
    for entry in registry['engines'].values():
        p=checkout/entry['manifest'];v=json.loads(p.read_text())
        for n in json.loads((PACKAGE/'PATCH_SPEC.json').read_text())['payload']:
            if n in v['files']:v['files'][n]=old[n]
        p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');entry['sha256']=sha(p)
    (checkout/'00_SYSTEM/PIPELINE.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
    # The serving snapshot omits offline deployment gates; DEV retains these.
    for n in ['06_TOOLS/COMMANDS/genos_generation_e2e.py',
              '02_BACKEND/lawrag/pipeline/term_serving_bundle.py',
              '02_BACKEND/lawrag/pipeline/glossary_knowledge.py',
              '02_BACKEND/lawrag/pipeline/glossary_serving.py',
              '02_BACKEND/lawrag/pipeline/glossary_v1.py',
              '02_BACKEND/lawrag/pipeline/glossary_alignment.py',
              '02_BACKEND/lawrag/pipeline/collect_moleg_knowledge.py',
              '02_BACKEND/lawrag/sources/__init__.py',
              '02_BACKEND/lawrag/sources/moleg_knowledge.py']:
        dest=checkout/n;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copyfile(ROOT/n,dest)
    for source in (ROOT/'02_BACKEND/lawrag/sources').glob('*.py'):
        dest=checkout/'02_BACKEND/lawrag/sources'/source.name
        if not dest.exists():shutil.copyfile(source,dest)
    if configured:
        write(checkout/'00_SYSTEM/GENOS_SERVING_PATHS.json',dict(schema_version='genos-serving-paths-v1',
            selection='operator-fixed',generation=str(g),runtime=str(runtime),state=None,
            generation_manifest_sha256=sha(g/'manifest.json'),operator_note='preserve existing field setting'))
        from lawrag.pipeline.search_selection import plan
        write(g.parent/'SEARCH_SELECTION/generation.json',plan(g))
        write(checkout/'CODE_MANIFEST.json',dict(format='8agent-code/1',files=[
            dict(path='service.py',sha256=sha(checkout/'service.py'),bytes=(checkout/'service.py').stat().st_size)],
            operator_note='preserve existing inventory'))
        (checkout/'.gitignore').write_text('/CODE_MANIFEST.json\n/00_SYSTEM/SEARCH_SELECTION/\n')
    sidecar=g.parent/'SEARCH_SELECTION/generation.json'
    sidecar_before=sidecar.read_bytes() if configured else None
    alias=tmp_path/'DEV';alias.symlink_to(checkout,target_is_directory=True)
    git=lambda *a:subprocess.run(['git','-C',str(checkout),*a],check=True,capture_output=True,text=True)
    git('init','-q');git('config','user.email','test@example.invalid');git('config','user.name','Synthetic fixture')
    git('add','.');git('commit','-qm','fixture base')
    before_code={str(p.relative_to(checkout)):sha(p) for p in checkout.rglob('*') if p.is_file() and '.git' not in p.parts}
    transfer=tmp_path/'actual-upload';transfer.mkdir()
    archive=transfer/(NAME+'.zip');shutil.copyfile(PACKAGE/archive.name,archive)
    package=transfer/NAME
    subprocess.run([sys.executable,'-m','zipfile','-e','./'+archive.name,'./'+NAME],cwd=transfer,check=True)
    env=os.environ.copy();env['PATH']=str(ROOT/'.venv/bin')+os.pathsep+env['PATH']
    for k in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RUNTIME_DIR','GENOS_STATE_DIR'):
        env.pop(k,None)
    records=[]
    def run(action,ok=True):
        cmd=['bash','./'+NAME+'/RUN_DEV_SELECTION.txt',action,'--root',str(alias),'--generation',str(g),'--runtime',str(runtime)]
        result=subprocess.run(cmd,cwd=transfer,env=env,capture_output=True,text=True,timeout=180)
        records.append(dict(command=cmd,exit_code=result.returncode,expected_success=ok,output=result.stdout+result.stderr))
        (tmp_path/'COMMANDS.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
        assert (result.returncode==0)==ok, result.stdout+result.stderr
        return result
    run('check')
    assert before_code=={str(p.relative_to(checkout)):sha(p) for p in checkout.rglob('*') if p.is_file() and '.git' not in p.parts}
    file=package/'selection_worker.py';original=file.read_bytes();file.write_bytes(original+b'\n# tamper\n')
    run('check',False);file.write_bytes(original)
    manifest=g/'manifest.json';manifest_raw=manifest.read_bytes();manifest.write_bytes(manifest_raw+b' ')
    run('apply',False);manifest.write_bytes(manifest_raw)
    run('apply');run('apply');run('check')
    state=json.loads((package/'INSTALL_STATE.json').read_text())
    # Exact partial-write recovery, after an interrupted apply.
    name='02_BACKEND/semantic_runtime/search_selection.py';target=checkout/name
    target.write_bytes((package/'blobs'/state['files'][name]['before']).read_bytes())
    run('apply')
    # Reject foreign edits for both retry and rollback, preserving the foreign bytes.
    expected=target.read_bytes();target.write_bytes(expected+b'\n# foreign edit\n')
    foreign=sha(target);run('apply',False);run('rollback',False);assert sha(target)==foreign
    target.write_bytes(expected)
    # Metadata moved into code; original NFS selection is still absent.
    assert (sidecar.read_bytes() if sidecar.exists() else None)==sidecar_before
    if configured:assert json.loads((checkout/'00_SYSTEM/GENOS_SERVING_PATHS.json').read_text())['operator_note']=='preserve existing field setting'
    assert json.loads((checkout/'00_SYSTEM/SEARCH_SELECTION/generation.json').read_text())['counts']['excluded_documents']==1
    # A broken rollback snapshot is detected before touching the checkout.
    backup=package/'blobs'/state['files'][name]['before'];backup_raw=backup.read_bytes();backup.write_bytes(backup_raw+b'x')
    run('rollback',False);backup.write_bytes(backup_raw)
    # The runner must not consume unrelated staged work.
    (checkout/'unrelated.txt').write_text('preserve\n');git('add','unrelated.txt')
    run('commit',False);git('reset','-q','--','unrelated.txt')
    run('commit');run('commit');run('gate-code');run('gate')
    assert json.loads((package/'RELEASE_GATE.json').read_text())['genos_verified'] is False
    # Test module resolution in a second real deployed directory (no CODE_ROOT mock).
    deployed=tmp_path/'app/src/service';shutil.copytree(checkout,deployed,ignore=shutil.ignore_patterns('.git'))
    subprocess.run([str(ROOT/'.venv/bin/python'),str(package/'selection_worker.py'),str(deployed),'verify',str(g),str(tmp_path/'deployed.json')],
                   env=env,check=True,capture_output=True,text=True)
    assert json.loads((tmp_path/'deployed.json').read_text())['selection_path']==str(deployed/'00_SYSTEM/SEARCH_SELECTION/generation.json')
    run('rollback');run('rollback');run('gate-code',False)
    for n,h in before_code.items():assert sha(checkout/n)==h,n
    assert not (checkout/'00_SYSTEM/SEARCH_SELECTION/generation.json').exists()
    assert before_data=={str(p.relative_to(g)):sha(p) for p in g.rglob('*') if p.is_file()}
    # The same preserved state supports a clean reapply after an explicit rollback.
    run('apply')
    (tmp_path/'RESULT.json').write_text(json.dumps(dict(commands=len(records),expected_rejections=sum(not r['expected_success'] for r in records),
        code_relocation=True,nfs_unchanged=True,api_model_calls=0,genos_verified=False),indent=2))
