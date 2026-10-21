"""Build synthetic source generation and freeze unchanged MAIN94 with its grant."""
from pathlib import Path
import datetime, hashlib, importlib.util, json, os, re, shutil, sqlite3, subprocess, sys
from design import CASES, DOCUMENTS, GOLD, CRITERIA
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0955-main94-design-weakness-probe'
D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
selected=read(R/pointer['manifest_path'])
assert pointer['generation']==94 and len(selected['files'])==393
for n,h in selected['files'].items():
    assert sha(R/selected['code_root']/n)==h,n
    assert sha(R/n)==h,n
put(D/'cases.json',CASES);put(D/'criteria.json',CRITERIA)
put(D/'gold-evaluation-only.json',GOLD)
put(D/'documents.json',{'synthetic':True,'documents':DOCUMENTS})
put(D/'selected-main.json',{'pointer':pointer,'manifest':selected})
m=read(A/'실험/manifest.json')
m['lineage']['hypothesis_delta']=CRITERIA['hypothesis']
m['lineage'].update(root_ref='ADR-0955-experiment-v1/observed',root_refs=['ADR-0955-experiment-v1/observed'])
m['design'].update(hypothesis=CRITERIA['hypothesis'],primary_metric=CRITERIA['primary_metric'],
    success_criteria=CRITERIA['success'],failure_criteria=CRITERIA['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'observed','role':'candidate','derived_from':[],
    'changes':'No product behavior change; synthetic source generation and isolated grant only. MAIN94 is a maintenance release, not an ADR arm, so exact release hashes are the root binding.',
    'controls':CRITERIA['controls']}]
m['runs'][0].update(arm_ids=['observed'],selection_rule=CRITERIA['selection'],
    artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':160}]
m['dataset'].update(name='synthetic-main94-design-four-cases',version='20261020-r1',
    frozen_source=str((D/'documents.json').relative_to(R)),sha256=sha(D/'documents.json'),
    legal_version_checked=False,reference_version_checked=True)
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},
        {'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},
        {'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':stages}
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Unchanged retrieval policy measured on synthetic inputs; complete read/return/cite ledger.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
    artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
put(D/'preimplementation-design.json',{'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'criteria_sha256':sha(D/'criteria.json'),'cases_sha256':sha(D/'cases.json'),'documents_sha256':sha(D/'documents.json'),
    'gold_sha256':sha(D/'gold-evaluation-only.json'),'manifest_sha256':sha(A/'실험/manifest.json')})
sys.dont_write_bytecode=True
sys.path[:0]=[str(R/'02_BACKEND'),str(R/'05_TESTS/CONTRACTS'),str(R/'05_TESTS')]
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(R),LAWRAG_TOOL_WORKSPACE_ROOT=str(R))
from test_document_release import source
import conftest
from lawrag.pipeline.term_generation import build_generation
from lawrag.pipeline.search_selection import plan,activate
from semantic_runtime.unit_fulltext import build
data=A/'artifacts/synthetic-data';data.mkdir(exist_ok=True)
if not (data/'built/generation/manifest.json').exists():
    glossary=conftest.term_glossary.__wrapped__(data)
    raw=source(data/'raw.sqlite',[(i,n,t) for i,n,c,t in DOCUMENTS])
    with sqlite3.connect(raw) as db:
        for did,name,category,texts in DOCUMENTS:
            db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps({
                'document_category':category,'document_metadata':{'team':'risk_team','synthetic':True},
                'workflow_version':{'verified':True,'valid_from':'2020-01-01','valid_to':None}}),did))
            for i,text in enumerate(texts):
                heading=re.match(r'제\d+조\(([^)]+)\)',text).group(1)
                db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',
                    (json.dumps({'family':'kr_article','surface':f'제{i+1}조','title':heading,'span':[i,i+1]}),did,str(i)))
    build_generation(raw,glossary,data/'built',serving=True)
G=data/'built/generation'
if not (G.parent/'unit-fulltext').exists():build(G,G/'navigation',G.parent/'unit-fulltext',workers=1)
activate(plan(G,latest=True))
gm=read(G/'manifest.json');ids=sorted(d[0] for d in DOCUMENTS)
put(D/'baseline.json',{'pointer':pointer,'manifest':{**selected,'data_path':str(G.relative_to(R)),'data_manifest_sha256':sha(G/'manifest.json')}})
authorization={'authorized_by':'user','authorization_text':'2026-10-20 사용자: 아쉬운 부분 있나 지금 설계에서 실험 한번해봐. 새로 작성한 합성 문서만 사용한다.',
    'workflow_ids':['risk_team_compare_workflow'],'teams':['risk_team'],'document_ids':ids,
    'generation_id':gm['generation_id'],'store_sha256':gm['store_sha256'],'generation_manifest_sha256':sha(G/'manifest.json'),
    'internal_source_is_public':True,'synthetic_only':True}
put(D/'authorization.json',authorization)
def link(ident,inside,outside):
    return {'id':ident,'internal':[{'document_id':inside[0],'unit_id':str(inside[1])}],
        'external':[{'document_id':outside[0],'unit_id':str(outside[1])}], 'kind':'BASIS',
        'reason':'합성 문서로 만든 격리 시험 연결. 연결 상태와 원문 적용성은 별도로 판단한다.',
        'provenance':{'type':'USER_SELECTION','experiment_id':m['experiment_id'],'synthetic':True,'legal_relation_certified':False}}
graph={'test_only':True,'links':[link('scope-link',['i-sec',1],['e-bank',0]),link('transfer-link',['i-sec',2],['e-transfer',0])]}
put(D/'graph-input.json',graph)
put(D/'schedule.json',[{'arm':'observed','case_id':c['id']} for c in CASES])
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),
    '--candidate-id','observed','--experiment-id',m['experiment_id'],'--arm-id','observed','--run-id','run-001']
for n in selected['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0955/observed';S=C/'snapshot'
grant=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
grant.update(generation_id=gm['generation_id'],source_store_sha256=gm['store_sha256'],
    public_document_ids=ids,workflow_authorization=authorization,
    basis_path=str((D/'authorization.json').relative_to(R)),basis_sha256=sha(D/'authorization.json'),
    rebinding_proof_path=str((D/'authorization.json').relative_to(R)),rebinding_proof_sha256=sha(D/'authorization.json'),
    authorization=authorization['authorization_text'])
put(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',grant)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
    v=read(p);changed=False
    for n,h in v.get('files',{}).items():
        actual=sha(S/n)
        if actual!=h:
            assert n=='00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',n
            v['files'][n]=actual;changed=True
    if changed:put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
for engine in v['engines'].values():engine['sha256']=sha(S/engine['manifest'])
put(p,v)
for command in ('refresh','freeze','validate'):
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],check=True,stdout=subprocess.DEVNULL)
rev=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
files={n:sha(code/n) for n in selected['files']}
changed=[n for n,h in files.items() if h!=selected['files'][n]]
assert all(n in ('00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','00_SYSTEM/PIPELINE.json') or n.startswith('02_BACKEND/ENGINES/') for n in changed),changed
candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':'observed',
    'arm_id':'observed','experiment_id':m['experiment_id'],'run_ids':['run-001'],
    'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
put(D/'observed-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':files,'candidate':candidate,
    'release_id':'adr0955-observed','generation':94,'configuration_and_pins_changed':changed,'product_behavior_identical_MAIN94':True})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[candidate])
put(A/'실험/manifest.json',m)
frozen={str(Path(code.relative_to(R))/n):h for n,h in files.items()}
paths=[*T.glob('*.py'),*D.glob('*.json'),R/'06_TOOLS/EXPERIMENTS/resource_guard.py',
    R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
    R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',G.parent/'SEARCH_SELECTION/generation.json']
paths += [G/n for n in ('manifest.json','store.sqlite','navigation/manifest.json','navigation/navigation.sqlite','fulltext/manifest.json')]
paths += [G.parent/'unit-fulltext'/n for n in ('manifest.json','units.sqlite')]
for p in paths:frozen[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':frozen,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('Frozen MAIN94 behavior, synthetic corpus, two test edges, four sequential requests, maximum160 physical calls.')
