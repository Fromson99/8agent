from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0723-source-target-recovery-complete';D=A/'artifacts/design';P=R/'02_BACKEND/lawrag/research/candidates/adr_0720/resumed'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
bp=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(bp);base=read(R/pointer['manifest_path']);assert pointer['generation']==50
pcm=read(P/'candidate.json');rev=pcm['revisions'][-1];src=P/'revisions'/rev['revision_id']/'snapshot'
drift=[p for p,h in base['files'].items() if not (R/p).is_file() or sha(R/p)!=h]
assert not drift,drift
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(bp),'manifest':base})
criteria={'scope':'Complete inherited request repair with source-bound gap routes for exact and ambiguous targets, canonical subset read suppression including saved-view choices, typed failure guidance and bounded transient tool recovery; preserve source/ACL/hash/unknown transmission safety.', 'required':['all inherited23 contract tests and new native tool failure/resume tests pass','zero new failures against the same MAIN50 legacy contract set','unique exact target exposes original READ; ambiguous/inaccessible/partial lookup never proves absence','failed read has no adopted new evidence; exact failed operation suppressed while alternatives remain','partial batch completed read receipts survive interruption; no schema/hash/ACL failure swallowed','fresh user request can retry; same request retains failure and no-progress history','current-visible saved and subset originals use existing evidence without read; missing current body can be re-presented','no global forced fulltext fallback; scoped options remain model-selected'], 'execution':{'order':[['cm-019','baseline'],['cm-019','integrated'],['cm-050','integrated'],['cm-050','baseline'],['cm-051','baseline'],['cm-051','integrated']],'model':'qwen/qwen3.8-27b','provider':'Parasail','quantization':'fp8','reasoning':'none','fallback':False,'max_calls':40,'adaptive_reruns':False},'probe_gate':'No candidate HTTP500, valid returned citations/state/ACL/bindings, no false absence; semantic answer errors separately recorded. Known CM questions cannot qualify MAIN. All failures retained; subsequent changed code gets new ADR.', 'promotion':'Separate eligible unseen-public qualification of identical final code, then selective integration and actual local service selection; user explicitly authorized MAIN apply. GENOS excluded.'}
put(D/'criteria.json',criteria)
auth={'schema_version':'scoped-question-export-v1','user_instruction':'일부구현된거 + 부족한거 전부다 구현해서 메인에 반영하고 실험도 돌려 외부에 데이터쏴도됨 몇몇문제만 돌려','session':'01a12fea-e875-7d33-90e2-ce2701f6c853','questions':['cm-019','cm-050','cm-051'],'model':criteria['execution']['model'],'provider':'Parasail FP8','source_scope':'Selected release approved public65 documents only; exact selected questions and work contexts. Reference answers/keys/internal documents excluded; immutable export flags unchanged.'}
put(A/'artifacts/question-export-authorization.json',auth)
old=read(R/'04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile/artifacts/design/dataset.json')
cases=[x for x in old['cases'] if x['case_id'] in auth['questions']]
put(D/'dataset.json',{'cases':cases,'version':'v1','type':'known regression probes; gold is offline-only','source_generation':base['data_path']})
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Native source-target and tool recovery invariants; known CM behavior reported separately',success_criteria=criteria['required'],failure_criteria=criteria['probe_gate'],criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:arm.update(changes='MAIN50 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same public65 originals, native API, model/provider/deadline/call budget; no product gold')
m['runs'][0].update(selection_rule='Exact six known CM paired requests in frozen order after contracts',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='CM019/050/051 authorized known regression',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':criteria['execution']['model'],'repeats':1}]
stages=[{'stage_id':n,'kind':k,'parent_stage_ids':[] if i==0 else [names[i-1]]} for names in [['catalogue','recall','acquired','presented']] for i,(n,k) in enumerate(zip(names,['source','retrieve','select','present']))]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','integrated']};m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for x in pcm['files']:
 if (R/x['target_path']).is_file():cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL);C=R/'02_BACKEND/lawrag/research/candidates/adr_0723/integrated'
for x in pcm['files']:
 p=x['target_path'];dst=C/'snapshot'/p;dst.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(src/p,dst)
 if not (R/p).is_file():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',p,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'parent-inheritance.json',{'parent':'ADR-0720-experiment-v1/resumed','manifest_sha256':sha(P/'candidate.json'),'revision':rev['revision_id'],'files':{x['target_path']:sha(src/x['target_path']) for x in pcm['files']}})
print('Scope frozen; parent candidate copied; working/release files unchanged.')
