import copy
import importlib.util
import json
import shutil
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('host',ROOT/'02_BACKEND/PIPELINE/engine_host.py')
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)

def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
@pytest.fixture
def workspace(tmp_path):
    for directory in ['00_SYSTEM/SCHEMAS','02_BACKEND/ENGINES','06_TOOLS/AUDIT']:
        shutil.copytree(ROOT/directory,tmp_path/directory)
    for file in ['00_SYSTEM/LEGAL_SCHEMA.json','00_SYSTEM/PIPELINE.json']:
        shutil.copyfile(ROOT/file,tmp_path/file)
    config=H.load(tmp_path)
    return tmp_path,config

def install(root,config,name,inputs,outputs,body,kind='AUDITOR',migration=None):
    base=root/'02_BACKEND/ENGINES'/name/'1';p=base/'engine.py';p.parent.mkdir(parents=True)
    p.write_text('def run(inputs, parameters, context):\n    '+body+'\n')
    manifest={'schema_version':'pipeline-engine-v1','id':name,'version':'1','kind':kind,'maturity':'TOOL','inputs':inputs,'outputs':outputs,'entrypoint':{'path':str(p.relative_to(root)),'function':'run'},'files':{str(p.relative_to(root)):H.sha(p)},'parameters_schema':{'type':'object','properties':{},'additionalProperties':False},'migration':migration,'experiment_binding':None}
    m=base/'engine.json';write(m,manifest);config['engines'][name]={'manifest':str(m.relative_to(root)),'sha256':H.sha(m)}
    return m

def test_default_inventory_truthfully_marks_unmigrated_profiles():
    result=H.inventory(H.load())
    assert result['profiles']['semantic-contract-check']['ready']
    assert not result['profiles']['legal-rag']['ready']
    assert result['legacy_runtime']['migration_required']

def test_real_contract_engine_execution_and_immutable_run(workspace):
    root,c=workspace;p=ROOT/'01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json'
    inputs={'observation':{'path':str(p),'sha256':H.sha(p)}};out=root/'runs/one'
    r=H.execute(c,'semantic-contract-check',inputs,out,root=root)
    assert r['status']=='COMPLETE' and not r['approval_verified']
    assert H.read(out/'validate--report.json')['valid']
    with pytest.raises(H.ContractError,match='already exists'):H.execute(c,'semantic-contract-check',inputs,out,root=root)

def test_same_contract_engine_can_be_swapped(workspace):
    root,c=workspace
    install(root,c,'audit-alternate',{'observation':'semantic.observation'},{'report':'audit.semantic-report'},"return {'report': {'valid': True, 'record_id': inputs['observation']['id'], 'approval_verified': False, 'source_verified': False}}")
    p=ROOT/'01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json'
    r=H.execute(c,'semantic-contract-check',{'observation':{'path':str(p),'sha256':H.sha(p)}},root/'runs/swapped',{'validate':'audit-alternate'},root)
    assert r['steps'][0]['engine']=='audit-alternate'

@pytest.mark.parametrize('mutation,expected',[
    (lambda c:c['profiles']['semantic-contract-check']['nodes'][0]['bindings'].update(observation='missing.out'),'cycle or unknown'),
    (lambda c:c['profiles']['semantic-contract-check']['nodes'][0]['bindings'].clear(),'input ports'),
    (lambda c:c['profiles']['semantic-contract-check']['inputs'].update(observation='semantic.canonical'),'explicit MIGRATOR'),
    (lambda c:c['profiles']['semantic-contract-check']['nodes'][0].update(engine='unregistered'),'unregistered'),
    (lambda c:c['profiles']['semantic-contract-check']['nodes'][0].update(slot='extract'),'kind'),
    (lambda c:c['profiles']['semantic-contract-check']['nodes'][0]['parameters'].update(hidden=True),'Additional properties'),
])
def test_incompatible_swaps_and_bad_topology_rejected(workspace,mutation,expected):
    root,c=workspace;mutation(c)
    with pytest.raises(Exception,match=expected):H.plan(c,'semantic-contract-check',root=root)

def test_engine_file_drift_rejected(workspace):
    root,c=workspace;p=root/'02_BACKEND/ENGINES/semantic_contract/1.0.0/engine.py';p.write_text(p.read_text()+'\n# drift\n')
    with pytest.raises(H.ContractError,match='code hash drift'):H.plan(c,'semantic-contract-check',root=root)

def test_input_hash_drift_rejected_before_run(workspace):
    root,c=workspace;p=ROOT/'01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json'
    with pytest.raises(H.ContractError,match='input artifact hash'):H.execute(c,'semantic-contract-check',{'observation':{'path':str(p),'sha256':'0'*64}},root/'runs/bad',root=root)
    assert not (root/'runs/bad').exists()

def test_failure_receipt_preserved(workspace):
    root,c=workspace
    install(root,c,'broken',{'observation':'semantic.observation'},{'report':'audit.semantic-report'},'raise RuntimeError("synthetic failure")')
    p=ROOT/'01_DATA/CONTRACTS/LEGAL_SEMANTIC_V2/observation.json';out=root/'runs/failed'
    with pytest.raises(RuntimeError):H.execute(c,'semantic-contract-check',{'observation':{'path':str(p),'sha256':H.sha(p)}},out,{'validate':'broken'},root)
    assert H.read(out/'receipt.json')['status']=='FAILED'

def test_research_manifest_cannot_enter_tool_profile(workspace):
    root,c=workspace;m=install(root,c,'research-only',{'observation':'semantic.observation'},{'report':'audit.semantic-report'},'return {}')
    d=H.read(m);d['maturity']='RESEARCH';dest=root/'02_BACKEND/lawrag/research/candidates/test/engine.json';write(dest,d)
    c['engines']['research-only']={'manifest':str(dest.relative_to(root)),'sha256':H.sha(dest)}
    with pytest.raises(H.ContractError,match='research engine cannot run'):H.plan(c,'semantic-contract-check',{'validate':'research-only'},root)

def test_explicit_schema_migration_stage_executes(workspace):
    root,c=workspace
    for name,key in [('old','old'),('new','new')]:
        path=root/('00_SYSTEM/SCHEMAS/test-'+name+'.json')
        write(path,{'type':'object','properties':{key:{'type':'integer'}},'required':[key],'additionalProperties':False})
        c['contracts'][name]={'schema_path':str(path.relative_to(root)),'schema_sha256':H.sha(path)}
    install(root,c,'convert',{'input':'old'},{'output':'new'},"return {'output': {'new': inputs['input']['old']}}",'MIGRATOR',{'from_contract':'old','to_contract':'new','loss_policy':'LOSSLESS'})
    c['slots']['migrate']={'kind':'MIGRATOR','inputs':{'input':'old'},'outputs':{'output':'new'}}
    c['profiles']['migration']={'mode':'tool','status':'READY','inputs':{'old':'old'},'nodes':[{'id':'convert','slot':'migrate','engine':'convert','bindings':{'input':'$input.old'},'parameters':{}}],'outputs':{'new':'convert.output'}}
    p=root/'old.json';write(p,{'old':3})
    r=H.execute(c,'migration',{'old':{'path':str(p),'sha256':H.sha(p)}},root/'runs/migrated',root=root)
    assert H.read(root/'runs/migrated/convert--output.json')=={'new':3}
    assert r['status']=='COMPLETE'

def test_bad_migration_declaration_rejected(workspace):
    root,c=workspace
    install(root,c,'bad-migration',{'input':'semantic.observation'},{'output':'semantic.canonical'},'return {}','MIGRATOR',{'from_contract':'semantic.canonical','to_contract':'semantic.observation','loss_policy':'REJECT_LOSS'})
    with pytest.raises(H.ContractError,match='does not match ports'):H.engine(c,'bad-migration','tool',root)

def test_migration_required_does_not_hide_bad_topology(workspace):
    root,c=workspace;c['profiles']['legal-rag']['nodes'][0]['bindings']['query']='missing.output'
    with pytest.raises(H.ContractError,match='cycle or unknown'):H.inventory(c,root)
