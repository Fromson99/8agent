"""Codespace without deployment settings; synthetic contracts, no latency claim."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest
from test_legal_agent_double_harness import generation

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'08_DEPLOYMENT/GENOS/patches'
PATCH=BASE/'fulltext_location_20260929_r2'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

@pytest.fixture
def codespace(tmp_path,monkeypatch,generation):
    root=tmp_path/'workspace';root.mkdir()
    (root/'00_SYSTEM').mkdir()
    shutil.copy2(ROOT/'00_SYSTEM/WORKSPACE.json',root/'00_SYSTEM/WORKSPACE.json')
    data=module('codespace_generation_fixture',PATCH/'codespace_data.py')
    shared=tmp_path/'nfs-root/diamo/8-agent/term-releases';shared.mkdir(parents=True)
    monkeypatch.setattr(data,'SHARED_ROOT',shared)
    path=shared/'published-pecab/generation';shutil.copytree(generation,path)
    return root,data,path,shared

def test_no_deployment_env_or_current_selects_one_existing_nfs_generation(codespace):
    root,data,path,shared=codespace
    selection=data.select(root,{},env={})
    assert selection['path']==str(path)
    assert selection['selection']=='codespace-auto-single'
    assert selection['source_count']==3
    assert data.unchanged(selection)
    assert not (root/'.env').exists()
    assert not any(shared.rglob('CURRENT.json'))

def test_multiple_candidates_require_real_selection_and_never_choose_latest(codespace):
    root,data,path,shared=codespace
    other=shared/'a-older-looking-generation/generation';shutil.copytree(path,other)
    with pytest.raises(ValueError,match='후보가 여러 개'):data.select(root,{},env={},interactive=False)
    selected=data.select(root,{},env={},interactive=True,choose=lambda _: '2')
    assert selected['path']==str(path) and selected['selection']=='codespace-user-selected'
    assert data.select(root,{},env={},index=1)['path']==str(other)
    with pytest.raises(ValueError,match='범위'):data.select(root,{},env={},index=3)

def test_workspace_term_release_and_current_metadata_binding(codespace):
    root,data,path,shared=codespace
    local=root/'01_DATA/TERM_RELEASES/run/serving/generation';shutil.copytree(path,local)
    shutil.rmtree(shared)
    selected=data.select(root,{},env={})
    assert selected['path']==str(local)
    pointer=root/'01_DATA/generations/CURRENT.json';pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({'schema_version':'genos-current-generation-v1','path':str(local),'manifest_sha256':data.sha(local/'manifest.json')}))
    selected=data.select(root,{},env={})
    assert selected['selection']=='codespace-current'
    pointer.write_text(pointer.read_text()+' ')
    assert not data.unchanged(selected)
    value=json.loads(pointer.read_bytes());value['manifest_sha256']='0'*64;pointer.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='CURRENT generation manifest hash mismatch'):data.select(root,{},env={})

def test_explicit_generation_invalid_binding_and_symlinks_not_silently_skipped(codespace):
    root,data,path,shared=codespace
    value=data.select(root,{},explicit=path,env={})
    assert value['path']==str(path)
    link=shared/'linked';link.symlink_to(path,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):data.select(root,{},explicit=link,env={})
    nav=path/'navigation/manifest.json';nav.write_bytes(nav.read_bytes()+b' ')
    with pytest.raises(ValueError,match='metadata hash mismatch'):data.select(root,{},explicit=path,env={})
    with pytest.raises(ValueError,match='후보가 없습니다'):data.select(root,{},env={})

def test_no_data_is_clear_offline_diagnostic_not_serving_error(codespace):
    root,data,path,shared=codespace;shutil.rmtree(shared)
    with pytest.raises(ValueError,match='검색용 generation 후보가 없습니다') as caught:data.select(root,{},env={})
    assert 'Code-serving settings' not in str(caught.value)

def test_final_zip_hashes_excluded_js_syntax_and_no_serving_selector():
    archive=BASE/'GENOS_FULLTEXT_LOCATION_20260929_R2_BENCH.zip'
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();inventory=json.loads(z.read('CODE_MANIFEST.json'))
        assert set(names)=={r['path'] for r in inventory['files']}|{'CODE_MANIFEST.json'}
        for row in inventory['files']:
            import hashlib
            assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
            assert Path(row['path']).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
        assert b'operator_generation' not in z.read('benchmark.py')
        assert b'genos_generation_e2e' not in z.read('benchmark.py')
    subprocess.run(['bash','-n',str(BASE/'GENOS_FULLTEXT_LOCATION_20260929_R2_BENCH.txt')],check=True)

def copy_checkout(root):
    config=json.loads((ROOT/'00_SYSTEM/PIPELINE.json').read_bytes())
    names={'00_SYSTEM/WORKSPACE.json','00_SYSTEM/PIPELINE.json'}
    for entry in config['engines'].values():
        names.add(entry['manifest']);names.update(json.loads((ROOT/entry['manifest']).read_bytes())['files'])
    for row in config['contracts'].values():names.add(row['schema_path'])
    for profile in config['profiles'].values():
        for node in profile['nodes']:
            settings=node.get('parameters',{}).get('term_agent',{}).get('legal_agent',{})
            for key in ('profile','domain'):
                if key in settings:names.add(settings[key]['path'])
    # Import package marker files that do not carry engine pins.
    names.update(str(p.relative_to(ROOT)) for p in (ROOT/'02_BACKEND/semantic_runtime').rglob('__init__.py'))
    names.update(str(p.relative_to(ROOT)) for p in (ROOT/'02_BACKEND/lawrag/platform').rglob('*.py'))
    names.add('02_BACKEND/lawrag/__init__.py')
    for name in names:
        destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
    subprocess.run(['git','init','-q',str(root)],check=True)
    subprocess.run(['git','-C',str(root),'add','00_SYSTEM','02_BACKEND'],check=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','-qm','synthetic checkout'],check=True)

def test_mailed_txt_end_to_end_in_checkout_without_env_current_or_serving_script(tmp_path,generation):
    root=tmp_path/'workspace';root.mkdir();copy_checkout(root)
    path=root/'01_DATA/TERM_RELEASES/fixture/serving/generation';shutil.copytree(generation,path)
    # Photo's situation: existing checkout via ~/DEV symlink, no deployment env/CURRENT.
    home=tmp_path/'home';home.mkdir();(home/'DEV').symlink_to(root,target_is_directory=True)
    matrix=tmp_path/'synthetic-cases.json';matrix.write_text('[{"team":null,"query":"승인"}]')
    env={k:v for k,v in os.environ.items() if not k.startswith('GENOS_')}
    env.update(HOME=str(home),PYTHON_BIN=sys.executable,PAIRS='2',CASES_FILE=str(matrix),TMPDIR=str(tmp_path))
    env.pop('DEPLOY_ROOT',None);env.pop('SEMANTIC_LLM_BACKEND',None)
    txt=BASE/'GENOS_FULLTEXT_LOCATION_20260929_R2_BENCH.txt'
    result=subprocess.run(['bash',str(txt)],cwd=home/'DEV',env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'PACKAGE_HASHES PASS' in result.stdout and 'OFFLINE_RESULTS' in result.stdout
    assert 'Code-serving settings' not in result.stdout
    assert not (root/'06_TOOLS/COMMANDS/genos_generation_e2e.py').exists()
    out=next((root/'TRANSFER/fulltext-location-20260929-r1').glob('offline-*'))
    plan=json.loads((out/'FROZEN_PLAN.json').read_bytes());report=json.loads((out/'RESULTS.json').read_bytes())
    assert plan['data_selection']['selection']=='codespace-auto-single'
    assert report['llm_calls']==0 and report['cases'][0]['same_results'] is True
    assert len(report['rows'])==4
    assert subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],text=True).strip()==''
    assert not (root/'.env').exists() and not any((root/'01_DATA').rglob('CURRENT.json'))
