"""Freeze the existing maintenance changes against MAIN94; reuse immutable synthetic data."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess
import sys

R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-0956-comparison-required-scope-retest'
P=R/'04_EXPERIMENTS/ADR/ADR-0955-main94-design-weakness-probe/artifacts/design'
D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
selected=read(R/pointer['manifest_path'])
working=read(R/'09_ARTIFACTS/AUDITS/20261020-comparison-display-scope/BINDING.json')['files']
assert pointer['generation']==94 and set(working)==set(selected['files'])
for n,h in working.items():assert sha(R/n)==h,n
for n,h in selected['files'].items():assert sha(R/selected['code_root']/n)==h,n
cases=[c for c in read(P/'cases.json') if c['id'] in ('anchor-scope','reference-exception','missing-source')]
cases.append({'id':'explicit-formula','api_type':'RAG','question':
    '대사: 투자매매업자인 청명증권의 운영완충비율 산식과 분자·분모의 정의를 내규·외규로 비교해 줘. 유지상한만으로 답을 대신하지 말고, 산식 원문을 확보하지 못하면 그 부분을 미확인으로 남겨 줘.'})
cases[-1]['api_type']=cases[0]['api_type']
if 'workflow_id' in cases[0]:cases[-1]['workflow_id']=cases[0]['workflow_id']
gold=read(P/'gold-evaluation-only.json')
gold={c['id']:gold[c['id']] for c in cases if c['id'] in gold}
gold['explicit-formula']={'required':[['i-sec',0],['e-sec',0]],'criteria':[
    '산식과 분자·분모를 명시 요청의 필수 확인으로 유지한다.',
    '제공 원문에 없는 산식은 미확인으로 남기고 수치 상한으로 대체하거나 창작하지 않는다.']}
criteria={
    'hypothesis':'The pre-existing workflow1.20.2 instructions avoid optional formula/definition expansion while preserving answer-changing reference/exception investigation and explicitly requested formula research.',
    'primary_metric':'Scoped arm unnecessary parent followup tasks and request fields; required-source recall and requested-issue preservation.',
    'success':[
        'anchor-scope: scoped must not create a followup solely for missing formula/numerator/denominator or add those as independent requested fields.',
        'reference-exception: scoped final citations include i-sec/2, e-transfer/0 and e-outage/1 and retain outage, impossible prior approval, 3 business days and record conditions.',
        'missing-source: scoped keeps unavailable annex9 unconfirmed, cites available external deadline/exception and does not invent internal annex content.',
        'explicit-formula: scoped retains formula/numerator/denominator as required investigation, explicitly acknowledges unavailable formula and does not replace the answer with ratio limits.',
        'No original span/hash mismatch, ACL or state error; stored and duplicate consumers add no model calls and preserve the answer.',
        'Total physical calls of scoped <= 1.25 times control; report per-case costs and calls even if aggregate passes.'
    ],
    'failure':'Any failed scoped primary condition or integrity gate; preserve failure without adaptive retry or changes in this ADR.',
    'selection':'Four fixed synthetic cases: three known diagnostics and one newly worded explicit-request control. Same corpus, one execution per arm/case. In-sample probe, no general legal accuracy certification.',
    'controls':'Same 7 documents/16 articles, 2 approved test links, generation, profile, model/provider, prompt temperature, max40 calls/1800s; only scoped applies the existing 4 maintenance source files and dependent pins.',
    'limits':{'cases':4,'arms':2,'requests':8,'max_physical_calls_per_request':40,
        'max_total_physical_calls':320,'physical_timeout_seconds':180,'rss_gib':6,'address_space_gib':8,
        'min_available_gib':4,'min_disk_gib':10,'repeat':1,'adaptive_rerun':False},
    'limitations':['Small in-sample synthetic paired probe; not real Risk questions, GENOS internal model or Oracle performance.',
        'One offline source-grounded reviewer, no judge model or independent rater.',
        'False CONFLICT for stricter internal limits and broad approved-link lookup are separate pre-existing findings, not fixed here; record any recurrence.',
        'Display deduplication and scope instructions are bundled maintenance code; display is deterministic after all model decisions, so it cannot reduce earlier model calls.']
}
for name,value in [('cases.json',cases),('gold-evaluation-only.json',gold),('criteria.json',criteria),
                   ('documents.json',read(P/'documents.json')),('selected-main.json',{'pointer':pointer,'manifest':selected}),
                   ('baseline.json',read(P/'baseline.json'))]:
    put(D/name,value)
m=read(A/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],
    success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[
    {'id':'control','role':'candidate','derived_from':['ADR-0955-experiment-v1/observed'],
     'changes':'Unmodified MAIN94 behavior; isolated synthetic authorization only. Contemporary control, not reused old responses.',
     'controls':criteria['controls']},
    {'id':'scoped','role':'candidate','derived_from':['control'],
     'changes':'Existing user-requested maintenance workflow1.20.2: exact-original display merge and required-dependency instructions. No product edits during this experiment.',
     'controls':criteria['controls']}]
m['design']['existing_maintenance_source']='09_ARTIFACTS/AUDITS/20261020-comparison-display-scope/BINDING.json'
m['design']['existing_maintenance_note']='Working changes predate this experiment under separate user-authorized implementation; MAIN94 remains selected until separate user-directed maintenance cutover.'
m['runs'][0].update(arm_ids=['control','scoped'],selection_rule=criteria['selection'],
    artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0,'max_calls':320}]
m['dataset'].update(name='synthetic-required-scope-four-cases',version='20261020-r1',
    frozen_source=str((D/'documents.json').relative_to(R)),sha256=sha(D/'documents.json'),
    legal_version_checked=False,reference_version_checked=True)
stages=[{'stage_id':'acquired','kind':'source','parent_stage_ids':[]},
        {'stage_id':'returned','kind':'select','parent_stage_ids':['acquired']},
        {'stage_id':'cited','kind':'present','parent_stage_ids':['returned']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('control','scoped')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
    artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
put(D/'preimplementation-design.json',{'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'criteria_sha256':sha(D/'criteria.json'),'cases_sha256':sha(D/'cases.json'),
    'gold_sha256':sha(D/'gold-evaluation-only.json'),'manifest_sha256':sha(A/'실험/manifest.json')})
G=R/read(D/'baseline.json')['manifest']['data_path'];gm=read(G/'manifest.json')
authorization={**read(P/'authorization.json'),
    'authorization_text':'2026-10-20 사용자: 4번 재실험 확인 후 3·4번 MAIN 반영 및 삼성메일 전송. 합성 문서만 외부 모델에 사용한다.'}
put(D/'authorization.json',authorization)
graph=read(P/'graph-input.json')
for edge in graph['links']:edge['provenance']['experiment_id']=m['experiment_id']
put(D/'graph-input.json',graph)
put(D/'schedule.json',[{'arm':arm,'case_id':case['id']} for i,case in enumerate(cases)
                      for arm in (('control','scoped') if i%2==0 else ('scoped','control'))])
candidates=[];frozen={}
for arm in ('control','scoped'):
    command=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),
        '--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
    for n in working:command+=['--source',n]
    subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
    C=R/'02_BACKEND/lawrag/research/candidates/adr_0956'/arm;S=C/'snapshot'
    if arm=='control':
        for n in selected['files']:shutil.copyfile(R/selected['code_root']/n,S/n)
    grant=read(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
    grant.update(generation_id=gm['generation_id'],source_store_sha256=gm['store_sha256'],
        public_document_ids=authorization['document_ids'],workflow_authorization=authorization,
        basis_path=str((D/'authorization.json').relative_to(R)),basis_sha256=sha(D/'authorization.json'),
        rebinding_proof_path=str((D/'authorization.json').relative_to(R)),rebinding_proof_sha256=sha(D/'authorization.json'),
        authorization=authorization['authorization_text'])
    put(S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json',grant)
    for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
        value=read(p)
        if 'files' not in value:continue
        for n in value['files']:value['files'][n]=sha(S/n)
        put(p,value)
    p=S/'00_SYSTEM/PIPELINE.json';value=read(p)
    for engine in value['engines'].values():engine['sha256']=sha(S/engine['manifest'])
    put(p,value)
    for command in ('refresh','freeze','validate'):
        subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py',command,str(C)],check=True,stdout=subprocess.DEVNULL)
    revision=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/revision['revision_id']/'snapshot'
    files={n:sha(code/n) for n in working}
    expected=selected['files'] if arm=='control' else working
    actual_changes=[n for n,h in files.items() if h!=expected[n]]
    assert all(n in ('00_SYSTEM/LEGAL_AGENT/local-gemma-public.json','00_SYSTEM/PIPELINE.json') or n.startswith('02_BACKEND/ENGINES/') for n in actual_changes)
    candidate={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
        'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],'candidate_id':arm,
        'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],
        'runner_path':str((T/'live.py').relative_to(R)),'runner_sha256':sha(T/'live.py')}
    candidates.append(candidate)
    put(D/(arm+'-binding.json'),{'code_root':str(code.relative_to(R)),'serving_files':files,
        'candidate':candidate,'release_id':'adr0956-'+arm,'generation':94,
        'configuration_and_pins_changed':actual_changes,'maintenance_source_files':expected})
    frozen.update({str(code.relative_to(R)/n):h for n,h in files.items()})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=candidates)
put(A/'실험/manifest.json',m)
paths=[*T.glob('*.py'),*D.glob('*.json'),R/'06_TOOLS/EXPERIMENTS/resource_guard.py',
    R/'02_BACKEND/lawrag/research/experiment_client.py',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',
    R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',G.parent/'SEARCH_SELECTION/generation.json']
paths += [G/n for n in ('manifest.json','store.sqlite','navigation/manifest.json','navigation/navigation.sqlite','fulltext/manifest.json')]
paths += [G.parent/'unit-fulltext'/n for n in ('manifest.json','units.sqlite')]
for p in paths:frozen[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{'files':frozen,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
print('Frozen 8 sequential requests, 2 explicit code revisions, shared immutable synthetic generation; maximum320 calls.')
