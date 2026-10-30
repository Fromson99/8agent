from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1166-investigation-supervisor';D=A/'artifacts/design';T=Path(__file__).parent

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
a=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');m=read(R/a['manifest_path']);assert a['generation']==112
put(D/'baseline.json',{'active':a,'release':m,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
old=R/'04_EXPERIMENTS/ADR/ADR-1161-cm3-focused-qwen/artifacts'
for n in ('cases.json','corpus.json','authorization.json'):shutil.copyfile(old/'design'/n,D/n)
auth=read(D/'authorization.json');auth.update(user_request='한번 구현해보고 실험해봐',scope='MAIN112 isolated supervisor candidate, CM001/007/009 once, no MAIN promotion',max_model_calls=120);put(D/'authorization.json',auth)
put(A/'artifacts/evaluation-only/cases.json',read(old/'evaluation-only/cases.json'))
criteria={'hypothesis':'A bounded supervisor can cancel stalled actions and select authorized alternate routes or assessment while preserving independent source recovery.', 'primary_metric':'Actual intervention, original delivery, validated claims and published answer; known3 in-sample only', 'success':['Empty-basis schema satisfiable','Reference dictionary keys and values coherent; legal text unchanged','Supervisor cancellation enforced before tool, valid dependency retained','No more than2 physical supervisor calls within40, no retries, resume preserves budget','Source/ACL/hash invariants and existing MAIN112 vector/ontology functions preserved','Known CM3 each at most1 sequential request with actual final publication distinguished from technical/limited outcomes'], 'failure':'Any technical invariant failure blocks live; frozen resource guard blocks startup or next send; no whole-case retry; no fallback/evaluator; ordinary answer failure retained and next case only if no repeated root-cause or resource/integrity issue.', 'limits':{'model':40,'tools':1024,'wall_seconds':1800,'supervisor_physical':2,'directive_actions':2,'unchanged_trigger':2,'periodic_trigger':8}, 'resource':{'max_rss_bytes':4*1024**3,'min_mem_available_bytes':3*1024**3,'max_swap_used_bytes':512*1024**2,'min_disk_bytes':20*1024**3,'runtime':'workspace disk, not tmpfs'}, 'baseline':'MAIN112 exact frozen code zero-model compatibility checks; ADR1161 historical failures descriptive only, not a paired MAIN112 quality baseline', 'live_fallback':'If host resource guard prevents full-corpus execution, run at most one supervisor request on each frozen saved navigation fixture (007 call8,009 call8), separate lightweight phase, no corpus or gold. Report full3 not run; do not claim end-to-end success.', 'implementation_scope':'MVP gate in compact native navigation; progress opinions, frontier metadata/current authorized tool menu, up to2 subsequent actions; no autonomous whole-corpus coverage proof. Shadow/off compatibility. Failure contract and detailed design retained.'}
put(D/'criteria.json',criteria)
f=read(A/'실험/manifest.json');f['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'supervised','role':'candidate','derived_from':['ADR-1165-experiment-v1/integrated'],'changes':'Bounded progress supervisor execution gate and precondition defects','controls':'Same MAIN112 data/model/budgets, source/judgment/ontology/vector contracts retained'}]);f['runs'][0].update(arm_ids=['supervised'],selection_rule='Known cm001/cm007/cm009 once; predeclared lightweight saved-fixture fallback on host pressure',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
f['dataset'].update(name='Known CM001/007/009 and frozen saved ADR1161 inputs',version='CM approved',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
f['llm_policy']['llm_calls']=[{'role':'product_and_supervisor','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
f['retrieval_accounting'].update(changed=True,not_applicable_reason=None);f['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
f['design']['retrieval_stage_plan']['stages_by_arm']={'supervised':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
put(A/'실험/manifest.json',f)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
names=list(m['files']);present=[n for n in names if (R/n).is_file()];C=ac.snapshot(A,'supervised',present,experiment_id=f['experiment_id'],arm_id='supervised',run_ids=['run-001']);S=C/'snapshot'
for n,h in m['files'].items():
 assert sha(R/m['code_root']/n)==h,n
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/m['code_root']/n,S/n)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
print('Reserved and prepared',len(names),'MAIN112 files; model0')
