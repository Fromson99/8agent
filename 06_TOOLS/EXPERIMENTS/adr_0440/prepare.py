import json,hashlib,shutil,subprocess
from pathlib import Path
from lawrag.platform.workspace import load_layout
R=load_layout().root;D=R/'04_EXPERIMENTS/ADR/ADR-0440-task-harness-flash-medium';A=D/'artifacts';OLD=R/'04_EXPERIMENTS/ADR/ADR-0438-task-harness-live-validation';T=R/'06_TOOLS/EXPERIMENTS/adr_0440';C=R/'02_BACKEND/lawrag/research/candidates/adr_0440/flash-medium'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(p.relative_to(R))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 if (A/'frozen-design.json').exists():raise ValueError('already prepared')
 for name in ['dataset/product-cases.json','grading/gold.json','source-inventory.json']:
  dest=A/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OLD/'artifacts'/name,dest)
 shutil.copyfile(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',A/'policy-snapshot.json')
 auth={'source':'user_message','text':'걍 바보네... 모델 성능 조금만 올려보자 한 중상정도','scope':'ADR0440 isolated same-code harness comparison: Gemini3.8Flash medium product and offline evaluator; existing Lite baseline retained. No global default or MAIN change. Public law and authored synthetic questions only.','fallback_allowed':False}
 configs={'baseline':{'model':'gemini-3.1-flash-lite','thinking_level':'minimal'},'flash-medium':{'model':'gemini-3.8-flash','thinking_level':'medium'}}
 parent=read(OLD/'실험/manifest.json');limits=parent['design']['limits']
 design={'scope_authorization':auth,'configs':configs,'limits':limits,'temperature':0,'max_output_tokens':4096,'repeats':1,'baseline':'Historical completed ADR0438/harness outputs, identical cases/source/code. Not contemporaneous; no new baseline calls.','runtime':'Exact ADR0438 candidate rev-001, no runtime/prompt changes','criteria':{'answer_min':4,'answer_total':6,'guard_min':2,'guard_total':2,'baseline_only_regression':0,'invalid_adoption':0,'scope_escape':0,'max_calls':20,'soft_seconds':180},'grader':'Source-grounded anonymous alternating X/Y, same ADR0438 rubric; upgraded same Gemini3.8Flash medium single evaluator. Regrade BOTH old baseline and candidate here. Answer must FINISH; guards require WAITING_USER, no failure and meaningful user explanation. No error-only guard passes. Old scores unchanged.','selection_evidence':{'api_models_list':'read-only authenticated GET /v1beta/models returned models/gemini-3.8-flash on 2026-09-16 before reservation; successful generation not yet established','official_model':'https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash','official_price':'https://ai.google.dev/gemini-api/docs/pricing','price_per_million_usd':{'input':0.75,'output_including_thinking':3.75},'price_valid_through':'2026-12-31'}}
 write(A/'frozen-design.json',design)
 sourceauth=read(OLD/'artifacts/authorization.json');sourceauth.update(model='gemini-3.8-flash',authorization_user_message=auth['text'],scope_authorization=auth,prior_authorization_sha256=sha(OLD/'artifacts/authorization.json'),max_product_calls=160,max_judge_calls=8)
 write(A/'authorization.json',sourceauth)
 m=read(D/'실험/manifest.json');m['lineage']['hypothesis_delta']='A moderately stronger Flash model with medium thinking can overcome task interpretation/contract failures without changing harness code.'
 m['design'].update(hypothesis=m['lineage']['hypothesis_delta'],primary_metric='Grounded complete answers among same six explanation cases; two guards separately',success_criteria=design['criteria'],failure_criteria='Any failed criterion means no adoption; no fallback, no reruns in this ADR.',criteria_frozen_before_run=True,limits=limits,controls=design['runtime'],judge=design['grader'],historical_baseline=design['baseline'])
 for arm in m['design']['arms']:
  arm['changes']= 'Exact historical ADR0438/harness outputs' if arm['id']=='baseline' else 'Only provider model and thinking level upgraded; common transport plus explicit frozen scoped policy'
  arm['controls']='Same immutable runtime, questions, data, source scope, task definition, prompts, temperature0, output4096, aggregate budgets'
 stages=parent['design']['retrieval_stage_plan']['stages_by_arm']['harness'];m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in configs}
 m['runs'][0].update(selection_rule='Same eight frozen ADR0438 cases once; historical baseline retained; both variants graded with the same new evaluator and deterministic gates',artifact_path=rel(A/'results.json'))
 m['dataset']=parent['dataset'].copy();m['dataset'].update(version='0438-exact-reuse-for-0440',frozen_source=rel(A/'dataset/product-cases.json'))
 m['llm_policy']['experiment_override']={'schema_version':'user-authorized-experiment-models-v1','main_wiring':'unchanged','authorization':auth,'allowed_models':[c['model'] for c in configs.values()],'frozen_design_path':rel(A/'frozen-design.json'),'frozen_design_sha256':sha(A/'frozen-design.json')}
 m['llm_policy']['llm_calls']=[{'role':role,'class':cls,'model':configs['flash-medium']['model'],'thinking_level':'medium','arm_id':'flash-medium','repeats':1,'temperature':0} for role,cls in [('task_interpret','product'),('task_navigation','product'),('task_evidence_review','product'),('judge','offline_evaluator')]]
 m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=rel(A/'retrieval-ledger.json'),sha256='PENDING',not_applicable_reason=None)
 write(D/'실험/manifest.json',m)
 cmd=[str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py','snapshot','--adr',str(D),'--candidate-id','flash-medium','--experiment-id',m['experiment_id'],'--arm-id','flash-medium','--run-id','run-001']
 for p in [T/'run_probe.py',T/'score.py',R/'02_BACKEND/lawrag/research/experiment_client.py',A/'frozen-design.json']:cmd.extend(['--source',rel(p)])
 subprocess.run(cmd,check=True);subprocess.run([str(R/'.venv/bin/python'),str(R/'06_TOOLS/run_tool.py'),'adr_candidate.py','freeze',str(C/'candidate.json')],check=True)
 cm=read(C/'candidate.json');rev=cm['revisions'][-1];m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'flash-medium','experiment_id':m['experiment_id'],'arm_id':'flash-medium','run_ids':['run-001'],'manifest_path':rel(C/'candidate.json'),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':rel(T/'run_probe.py'),'runner_sha256':sha(T/'run_probe.py')}])
 write(D/'실험/manifest.json',m);write(A/'pre-call-manifest.json',m)
 oldlock=read(OLD/'artifacts/input-lock.json')['files'];files={p:h for p,h in oldlock.items() if '/generation/' in p or 'candidates/adr_0438/' in p}
 for p in [R/'06_TOOLS/EXPERIMENTS/adr_0438/run_probe.py',OLD/'artifacts/results.json',OLD/'artifacts/policy-binding.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'02_BACKEND/lawrag/research/experiment_client.py',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',C/'candidate.json',*T.glob('*.py'),A/'frozen-design.json',A/'authorization.json',A/'dataset/product-cases.json',A/'pre-call-manifest.json']:
  files[rel(p)]=sha(p)
 for f in rev['files']:files[f['frozen_path']]=f['snapshot_sha256']
 write(A/'input-lock.json',{'files':files,'gold_visible_to_product':False,'data_reuse':'Read-only ADR0438 immutable generation; task journal written only under ADR0440'})
 print('Design and candidate frozen; no generation calls',len(files))
if __name__=='__main__':main()
