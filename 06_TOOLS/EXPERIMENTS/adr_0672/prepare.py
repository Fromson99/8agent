from pathlib import Path
import json,hashlib,sys,shutil,importlib.util
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0672-investigation-chain-parent-collision';arm='chain-parent-fix'
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((A/'실험/manifest.json').read_text());parent=R/'04_EXPERIMENTS/ADR/ADR-0671-persistent-investigation-chain/실험/manifest.json';pm=json.loads(parent.read_text())
changes='Keep the complete action chain/menu restoration candidate. Resolve READ_ARTICLES by the actual source+parent-offer group ID, rather than assuming its first hit is the article root. A paragraph hit and a root hit sharing the same parent group reuse the same provenance-bound original. No prompt, ranking, model or source changes.'
m['lineage']['hypothesis_delta']=changes
m['design'].update(hypothesis='Correct parent group identity avoids the reproduced accounting StopIteration while preserving full originals, explicit adoption and all investigation history.',primary_metric='All73 contracts and both natural public API requests complete; all later action reasons retained.',success_criteria='Existing71 and two collision contracts pass. Both fresh questions HTTP200 complete with exact citation validation and unbroken chain; original menus still restorable; no hidden retry/fallback or MAIN cutover.',failure_criteria='Group ownership/citation/history/restore regression or request failure. Preserve original outcome and freeze unchanged after observation.',criteria_frozen_before_run=True)
m['design']['arms']=[{'id':arm,'role':'candidate','derived_from':['ADR-0671-experiment-v1/investigation-chain'],'changes':changes,'controls':'Same completed parent frozen271 code files except group lookup and two tests; same public145 corpus/Qwen3.8 Parasail FP8/no reasoning/no fallback/output6400/40calls/1800sec. Fresh accounting first then venture. Previous successful/failing results remain archived descriptive comparators.'}]
m['design']['retrieval_stage_plan']=pm['design']['retrieval_stage_plan'];m['design']['retrieval_stage_plan']['stages_by_arm']={arm:m['design']['retrieval_stage_plan']['stages_by_arm']['investigation-chain']}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
dataset=json.loads((R/pm['dataset']['frozen_source']).read_text());put(A/'artifacts/design/dataset.json',dataset)
m['dataset'].update(name='Same two unchanged user supplied public legal questions',version=dataset['source_generation'],frozen_source=str((A/'artifacts/design/dataset.json').relative_to(R)),sha256=sha(A/'artifacts/design/dataset.json'))
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':[arm],'selection_rule':'Fresh accounting first then venture. No answer, coordinates or forced decisions/returns injected. Collision and restoration separately tested against genuine synthetic reader/store contracts.','status':'planned','artifact_path':str((A/'artifacts/run-001/results.json').relative_to(R)),'sha256':'PENDING'}]
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/stage-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m);put(A/'artifacts/design/preimplementation-design.json',{'design':m['design'],'dataset':m['dataset'],'runs':m['runs'],'lineage':m['lineage']})
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));spec=importlib.util.spec_from_file_location('candidate_tools',R/'06_TOOLS/COMMANDS/adr_candidate.py');ac=importlib.util.module_from_spec(spec);spec.loader.exec_module(ac)
p=R/'02_BACKEND/lawrag/research/candidates/adr_0671/investigation-chain';cm=json.loads((p/'candidate.json').read_text());source=p/'revisions/rev-001/snapshot'
present=[x['target_path'] for x in cm['files'] if (R/x['target_path']).is_file()]
c=ac.snapshot(A,arm,present,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
for row in cm['files']:
 target=row['target_path'];dest=c/'snapshot'/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/target,dest)
 if target not in present:ac.register_file(c,target,upstream_state='absent')
for name in ['run_probe.py','run_contracts.py','summarize_probe.py','freeze.py','audit_chain.py']:
 text=(R/f'06_TOOLS/EXPERIMENTS/adr_0671/{name}').read_text().replace('ADR-0671-persistent-investigation-chain','ADR-0672-investigation-chain-parent-collision').replace('adr0671','adr0672').replace('adr_0671/investigation-chain','adr_0672/chain-parent-fix').replace('adr_0671/run_probe','adr_0672/run_probe')
 if name=='freeze.py':text=text.replace("'investigation-chain'", "'chain-parent-fix'")
 if name=='run_contracts.py':text=text.replace("files=['", "files=['test_chain_parent_collision_adr0672.py','")
 if name=='summarize_probe.py':text=text.replace('contracts_count=71','contracts_count=73')
 if name=='audit_chain.py':text=text.replace('20261006-investigation-chain-r1','20261006-investigation-chain-r2').replace("'contracts':71", "'contracts':73").replace('71개 계약','73개 계약')
 (R/f'06_TOOLS/EXPERIMENTS/adr_0672/{name}').write_text(text)
code=c/'snapshot/02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';text=code.read_text();old="group=next(g for g in self.p['groups'].values() if g['source_id']==sid and g['hit']['unit_id']==g['hit']['article_unit_id'])";new="group=self.p['groups'][lc.token(self.s,'B',[sid,lc.parent_offer(self.s,root_hit)['id']])]";assert text.count(old)==1;code.write_text(text.replace(old,new))
print(c)
