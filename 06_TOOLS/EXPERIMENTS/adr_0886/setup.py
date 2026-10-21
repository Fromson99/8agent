from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0886-delivered-original-continuity';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==86
release=read(R/pointer['manifest_path']);assert all(sha(R/n)==h for n,h in release['files'].items())
put(D/'baseline.json',dict(pointer=pointer,pointer_sha256=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),release=release))
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0876/scoped/candidate.json')
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']})
cases=read(R/'04_EXPERIMENTS/ADR/ADR-0882-condition-expression-host-contract/artifacts/design/cases.json')
refs=read(R/'04_EXPERIMENTS/ADR/ADR-0882-condition-expression-host-contract/artifacts/design/offline-reference.json')
registered=read(R/'01_DATA/review/cm_core_e2e_v3.json')['cases']
for cid in ('cm-011','cm-022','cm-038'):
 c=next(c for c in registered if c['id']==cid)
 cases.append({'id':cid,'question':c['question'],'api_type':'RAG_ASK','new_call_limit':40})
 refs.append({'id':cid,'reference_answer':c['reference_answer'],'targets':c['evidence_articles']+c.get('required_companions',[])})
put(D/'cases.json',cases);put(D/'offline-reference.json',refs)
criteria={'hypothesis':'Any currently selected, actually delivered original remains available across navigation and final assessment regardless of article/parent/scope/reference acquisition; preserve explicit exclusions and bounded full-page context.',
'success':['All8frozen CM cases run serially once; failures and all citations audited','Reference/scope origins survive window changes and final handoff without requiring adoption; exact page/source/ACL checks retained','Current compact one-decision tool dispatch, fact provenance, original MAIN86 workflows/compression/basis/Oracle all preserved','Final delivery uses whole-page bounded context and exposes budget omissions, never converts them to source absence','CM008subject/extension,CM003exception/classification,CM051operativeformula evaluated on frozen original sources; detailed judgment misses separately recorded'],
'failure':['Lost or fabricated originals/ACL/hash/state/deadline/replay integrity','Required tests/actual service consumer fail or resource ceiling hit'],
'design':['Available group registry is selected original reads, not only READ_ARTICLES tracking. Retain exact accepted pages from all read paths, never candidate previews','Navigation uses existing50kcharacter bound. Final extra context uses same bound, preserving explicitly selected completion basis and reporting omitted page IDs','No new query ranking/index/data changes; previous model prompts/tool choice/fact separation retained. Eight cases all attempted unless resource guard stops; semantic issues alone do not stop scheduled cases'],
'limits':{'calls_per_case':40,'wall_seconds':1800,'concurrency':1,'rss_gib':8,'as_gib':9},
'evaluation':'Existing five and additional CM011/022/038 from registeredCM51 unchanged; historically exposed, no legal holdout claim. Known failures/partial answers explicitly reported, not automatic promotion block. Independent finite technical qualification and actual service checks before MAIN.',
'resource_policy':'One worker, shared immutable generation, exact compressed raw histories; no new dataset copy'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','continuity','--experiment-id','ADR-0886-experiment-v1','--arm-id','continuity','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0885-coherent-navigation-fact-provenance/artifacts/design/freeze.json');PC=R/parent['code_root']
C=R/'02_BACKEND/lawrag/research/candidates/adr_0886/continuity/snapshot'
for n,h in read(R/'04_EXPERIMENTS/ADR/ADR-0885-coherent-navigation-fact-provenance/artifacts/design/working-before.json').items():
 if sha(PC/n)!=h:(C/n).write_bytes((PC/n).read_bytes())
m=read(A/'실험/manifest.json');m.update(in_sample=True,decision_eligible=False);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact requested original reading, completed useful answer, no diagnostic generation loop',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'continuity','role':'candidate','derived_from':['ADR-0885-experiment-v1/coherent'],'changes':criteria['design'],'controls':'Same MAIN86 data, eight original CM questions, model/profile40/1800 unchanged; no reference answer in product'}]
m['runs'][0].update(arm_ids=['continuity'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':320}]
m['dataset'].update(name='CM51 five known and three additional cases',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['design']['retrieval_stage_plan']['stages_by_arm']={'continuity':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['changed']=True;m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
print('MAIN86 preserved; prospective criteria and isolated snapshot ready')
