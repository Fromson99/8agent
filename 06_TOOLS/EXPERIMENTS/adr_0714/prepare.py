"""Freeze an unchanged MAIN50 replica and one known public question before calls."""
from pathlib import Path
import hashlib,json,sqlite3,subprocess,sys
sys.path.insert(0,str(Path.cwd()/'02_BACKEND'))
from lawrag.platform.workspace import load_layout
layout=load_layout();R=layout.root
A=layout.path('experiments')/'ADR/ADR-0714-main50-cm018-call-retest';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pp=layout.path('data')/'ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(pp);assert pointer['generation']==50
base=read(R/pointer['manifest_path']);assert sha(R/pointer['manifest_path'])==pointer['release_manifest_sha256']
for n,h in base['files'].items():assert sha(R/n)==sha(R/base['code_root']/n)==h,n
prior=R/'04_EXPERIMENTS/ADR/ADR-0705-cm-max-call-bottleneck-probe/artifacts/design/dataset.json'
dataset=read(prior);dataset['prior_selection']={'path':str(prior.relative_to(R)),'sha256':sha(prior)}
dataset['selection']+=' Reuse the previously identified high-call CM018 exactly; no new all-history maximum claim. One MAIN50 request only.'
criteria={'hypothesis':'MAIN50 fused entry, law-title hints and compact direct reading can reach CM018 originals and answer without the old repetitive navigation; measure without changing product behavior.',
 'primary_metric':'Physical model attempt count and sum of physical API attempt wall time; code/cache time excluded from headline.',
 'diagnostic_success':['One and only one product request recorded, including failure','Every physical attempt counted, timed and linked to exact request/response','Frozen code/profile/data/public scope and active MAIN pointer unchanged','Final user-visible answer compared to pinned original, separately from transport success'],
 'behavioral_expectation':{'http_status':200,'model_calls_max':8,'all_paragraph1_blocks_presented':True,'complete_structure_answer':True},
 'execution':{'requests':1,'repeats':1,'model_attempts_max':40,'wall_seconds':1800,'max_output_tokens':6400,'model':'qwen/qwen3.8-27b','provider':'Parasail','quantization':'fp8','reasoning':'none','fallback':False,'profiling':False,'warmup':False},
 'failure':'Preserve failure and partial trace; no adaptive rerun or product edits in this ADR.',
 'semantic_review':'Offline source-bound inspection of final visible answer. Expect paragraph1 main rule, appraisal period and its gift distinction, proviso for outside-period transactions with review and conditions, alternative items1/2/3 and exclusions; do not describe alternatives as all required or apply appraisal to excluded shares. Separate original delivery, model structured content and final assembly. Not an independent expert legal certification.',
 'limits':['Known in-sample one-request probe; no speedup significance or population p50/p95','Historical code/data/profiling differ; old values descriptive only','No GENOS execution','No past user-session state reused; no private transaction facts','No MAIN changes or promotion']}
put(D/'criteria.json',criteria);put(D/'dataset.json',dataset);put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(pp),'manifest':base})
allowed=set(read(R/base['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
with sqlite3.connect((R/base['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
 s=json.loads(db.execute('SELECT json FROM source WHERE id=?',('article:8f93f2a1bfc043dd9a90e23f',)).fetchone()[0])
assert s['document_id'] in allowed
put(D/'gold.json',{'product_visible':False,'version':'Pinned MAIN50 local original; no claim of current law certification','source':s,'required_block_ids':[str(n) for n in range(1038,1050)]})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['diagnostic_success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,repeats=1,behavioral_expectation=criteria['behavioral_expectation'],semantic_review=criteria['semantic_review'])
m['design']['arms']=[{'id':'measured-main50','role':'candidate','derived_from':['ADR-0712-experiment-v1/compact'],'changes':'No product changes; byte-identical selected MAIN50; isolated audited transport','controls':'Selected generation, exact profile, approved65 public documents, policy Qwen3.8 Parasail FP8; one fresh public session'}]
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['design']['retrieval_stage_plan']['stages_by_arm']={'measured-main50':[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'acquired','kind':'filter','parent_stage_ids':['catalogue']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]}
m['dataset'].update(name='Known public CM018 high-call request',version='unchanged-0705-question-v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['measured-main50'],selection_rule=dataset['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Product retrieval unchanged; newly measured paths on a known request, recorded in a dedicated stage ledger.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','measured-main50','--experiment-id',m['experiment_id'],'--arm-id','measured-main50','--run-id','run-001']
for n in sorted(set(base['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}):cmd+=['--source',n]
subprocess.run(cmd,cwd=R,check=True)
print('Frozen plan: unchanged MAIN50, known public question, one request; no model calls yet')
