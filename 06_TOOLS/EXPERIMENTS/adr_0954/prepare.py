"""Freeze the approved two-question inspection; retain MAIN92 product bytes."""
from pathlib import Path
import datetime, hashlib, json, shutil, subprocess, sys

R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0954-risk-photo-forced-graph'
D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
selected=read(R/pointer['manifest_path'])
assert pointer['generation']==92 and len(selected['files'])==389
for n,h in selected['files'].items():assert sha(R/selected['code_root']/n)==h,n
G=R/'01_DATA/TERM_RELEASES/risk-photo-0951-r2/named-documents/generation'
gm=read(G/'manifest.json')
source=read(R/'04_EXPERIMENTS/ADR/ADR-0951-risk-photo-workflow-inspection/artifacts/design/scoped-data.json')
ids=sorted(d['id'] for d in source['documents'])
internal='7a3907e193ec6c14';assert internal in ids and len(ids)==4
oldcases=read(R/'04_EXPERIMENTS/ADR/ADR-0951-risk-photo-workflow-inspection/artifacts/design/cases.json')['cases']
cases=[{'id':c['id'],'api_type':'LEGAL_AGENT','question':'대사: '+c['query']} for c in oldcases if c['id']!='document']
put(D/'cases.json',cases)
put(D/'reference-hints-evaluation-only.json',{
    'approved_legal_gold':False,'visible_to_product':False,
    'cases':[{k:v for k,v in c.items() if k!='query'} for c in oldcases if c['id']!='document']})
put(D/'selected-main.json',{'pointer':pointer,'manifest':selected})
put(D/'baseline.json',{'pointer':pointer,'manifest':{
    **selected,'data_path':str(G.relative_to(R)),'data_manifest_sha256':sha(G/'manifest.json')}})
authorization={
    'authorized_by':'user','approved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'authorization_text':'2026-10-20: 사용자가 기존 두 질문의 내규와 외규를 직접 그래프로 연결하여 일부 문서에서 실제 대사를 확인하라고 요청함. 앞서 승인된 동일 사진 내규·외규·모델 범위의 후속 두 질문. 격리 시험 관계 활성화만 승인하며 법적 관계 정본/운영 승인이 아님.',
    'session_id':'01a157e6-3559-7313-b8fd-bf38cc13a575',
    'purpose':'Two frozen questions with manual graph seeds through existing basis APIs; one live request each; historical ADR0953 control, no live baseline replay.',
    'case_file':str((D/'cases.json').relative_to(R)),'case_file_sha256':sha(D/'cases.json'),
    'workflow_ids':['risk_team_compare_workflow'],'teams':['risk_team'],'document_ids':ids,
    'generation_id':gm['generation_id'],'store_sha256':gm['store_sha256'],
    'generation_manifest_sha256':sha(G/'manifest.json'),
    'internal_source_is_public':False,'production_grant_changed':False,'automatic_replay':False,
}
put(D/'authorization.json',authorization)
from graph_design import criteria, graph
put(D/'forced-graph.json',graph(G))
put(D/'criteria.json',criteria)
put(D/'schedule.json',[{'arm':'linked','case_id':c['id']} for c in cases])
m=read(A/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],
    success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'linked','role':'candidate','derived_from':['ADR-0953-experiment-v1/live'],
    'changes':'User-forced source-coordinate edges seeded and activated in isolated basis DB before each question. Product behavior code unchanged.',
    'controls':criteria['controls']}]
m['runs'][0].update(arm_ids=['linked'],selection_rule=criteria['selection'],
    artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b',
    'repeats':1,'temperature':0,'max_calls':80}]
m['dataset'].update(name='photo-r2-forced-graph-two-questions',version='20261020-r1',
    frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),
    legal_version_checked=False,reference_version_checked=False)
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},
        {'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},
        {'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'linked':stages}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None,corpus_total=0,before_filter={},after_filter={},presented_total={},presented_mean={},presented_p50={},presented_p95={},golden_recall={},selectivity={})
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
    artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),
    '--candidate-id','linked','--experiment-id',m['experiment_id'],'--arm-id','linked','--run-id','run-001']
for n in selected['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0954/linked'
for n,h in selected['files'].items():
    if sha(C/'snapshot'/n)!=h:shutil.copyfile(R/selected['code_root']/n,C/'snapshot'/n)
grant_path=C/'snapshot/00_SYSTEM/LEGAL_AGENT/local-gemma-public.json';grant=read(grant_path)
grant.update(generation_id=gm['generation_id'],source_store_sha256=gm['store_sha256'],
    public_document_ids=[d for d in ids if d!=internal],basis_path=str((D/'authorization.json').relative_to(R)),
    basis_sha256=sha(D/'authorization.json'),authorization=authorization['authorization_text'],
    rebinding_proof_path=str((D/'authorization.json').relative_to(R)),rebinding_proof_sha256=sha(D/'authorization.json'),
    workflow_authorization={k:authorization[k] for k in [
        'authorized_by','authorization_text','teams','document_ids','generation_id','store_sha256',
        'generation_manifest_sha256','internal_source_is_public','workflow_ids']})
put(grant_path,grant)
# Rebind the approved configuration through the existing engine/pipeline pins.
# Only the known authorized file hash may differ; never bless arbitrary drift.
S=C/'snapshot'
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
    value=read(p);original=read(p)
    for n,h in value.get('files',{}).items():
        observed=sha(S/n)
        if observed!=h:
            assert n=='00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',n
            value['files'][n]=observed
    if value!=original:put(p,value)
p=S/'00_SYSTEM/PIPELINE.json';value=read(p);original=read(p)
for engine in value['engines'].values():
    engine['sha256']=sha(S/engine['manifest'])
if value!=original:put(p,value)
for command in ('refresh','freeze','validate'):
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],check=True,stdout=subprocess.DEVNULL)
rev=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
files={n:sha(code/n) for n in selected['files']}
changed=[n for n,h in files.items() if h!=selected['files'][n]]
assert '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json' in changed
assert all(n in ('00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','00_SYSTEM/PIPELINE.json')
           or n.startswith('02_BACKEND/ENGINES/') for n in changed),changed
for n in changed:
    if n.startswith('02_BACKEND/ENGINES/'):
        before=read(R/selected['code_root']/n);after=read(code/n)
        before.pop('files');after.pop('files');assert before==after,n
candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
    'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'candidate_id':'linked',
    'arm_id':'linked','experiment_id':m['experiment_id'],'run_ids':['run-001'],
    'runner_path':str((T/'linked.py').relative_to(R)),'runner_sha256':sha(T/'linked.py')}
put(D/'linked-binding.json',{'code_root':str(code.relative_to(R)),'serving_files':files,
    'candidate':candidate,'release_id':'adr0954-linked','generation':92,
    'changed_configuration_and_pin_files':changed,'product_behavior_code_identical_to_MAIN92':True})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[candidate])
put(A/'실험/manifest.json',m)
frozen={str(Path(code.relative_to(R))/n):h for n,h in files.items()}
paths=[*T.glob('*.py'),*D.glob('*.json'),R/'06_TOOLS/EXPERIMENTS/resource_guard.py',
    R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
    R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',G.parent/'SEARCH_SELECTION/generation.json']
paths += [G/n for n in ('manifest.json','navigation/manifest.json','fulltext/manifest.json')]
for p in paths:frozen[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':frozen,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('Frozen 389 files; scoped authorization and its checked engine/pipeline pins rebound; 2 sequential questions, max80 physical calls; forced graph input is explicitly product-visible, not discovery accuracy evidence.')
