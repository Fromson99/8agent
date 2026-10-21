from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency';P=R/'04_EXPERIMENTS/ADR/ADR-0894-mixed-source-modality';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
assert not (D/'freeze.json').exists()
base=read(P/'artifacts/design/baseline.json');before=read(P/'artifacts/design/working-before.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
assert all(sha(R/n)==h for n,h in before.items())
for n in ['baseline.json','working-before.json','data-binding.json','cases.json','offline-reference.json']:shutil.copy2(P/'artifacts/design'/n,D/n)
prior=read(P/'artifacts/followup-design.json');notes={'candidate_plan':prior['next_changes'],'checks':prior['tests']}
criteria={'hypothesis':'Canonical limitation text deduplication before commit and immutable completion projection eliminate duplicate-text publication mismatch without dropping distinct gap identities or weakening saved-source integrity.',
 'design':notes['candidate_plan'],'required_contracts':notes['checks'],
 'success':['All8sameCMquestions attempted serially on exactcandidate','Distinct gaps retain identities/reasons while identical publictext appears once','Saved legacyduplicate limitations remain byte-identical in completion publication; tamper andnewuncommitted text remain rejected','All597retained checks and new API duplicate/partial/recovery/publication cases pass','CM003/008/051 andextra3 manuallyreviewed; semanticmisses explicit'],
 'failure':['Source ACL hash state budget consumerregression or newtechnicalpublicationfailure','Lost gap/source/uncertainty records or acceptedpublictext not identical to savedcomposition','Resource ceiling exceeded'],
 'run_order':['cm-033','cm-001','cm-003','cm-008','cm-051','cm-011','cm-022','cm-038'],
 'limits':{'calls_per_case':40,'wall_seconds':1800,'final_reserve':3,'workers':1,'rss_gib':8,'as_gib':9},
 'recovery':{'owner':'Canonical completion materialization and existing publicresult boundary; no added modelretry','preserve':'Distinct detailedgap records and allpastcommits; unchangedmodeljudgments and exactverifiedtext','final':'Strict publication comparison and existing bounded partialanswers'},
 'resource_policy':'GENOS_RESIDENT_DATAoff,sharedread-onlySQLite,oneworker,compressedrawhistory',
 'evaluation':'SameCM001/003/008/033/051 andadditionalCM011/022/038. Knownin-sample diagnosticreplay, not legalholdout; independentfinite technicalqualification aftercomplete.'}
put(D/'criteria.json',criteria)
parent=read(P/'artifacts/design/freeze.json');PC=R/parent['code_root'];cm=read(R/parent['candidate']['manifest_path'])
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','consistent','--experiment-id','ADR-0895-experiment-v1','--arm-id','consistent','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0895/consistent/snapshot'
for n,h in before.items():
 if sha(PC/n)!=h:(C/n).write_bytes((PC/n).read_bytes())
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Requested original access and useful final answer with bounded durable recovery',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'consistent','role':'candidate','derived_from':['ADR-0894-experiment-v1/mixed'],'changes':criteria['design'],'controls':'SameMAIN86 data, frozenCM8, Qwen3.8ParasailFP8 reasoningnone nofallback,40calls1800s; no gold inproduct'}]
m['runs'][0].update(arm_ids=['consistent'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':320}]
m['dataset'].update(name='CM51 five known and three additional cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'consistent':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN86 exact; completed0894 inherited; criteria frozen before implementation')
