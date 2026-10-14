"""Freeze reviewed code and exact comparators before measured outcomes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0689-judgment-loop-review-repair';D=A/'artifacts/design'
OLD=R/'02_BACKEND/lawrag/research/candidates/adr_0689/repaired'
C=OLD.with_name('reviewed')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*args):subprocess.run([str(R/'.venv/bin/python'),*map(str,args)],cwd=R,check=True)
assert not (D/'freeze.json').exists()
old=read(OLD/'candidate.json');m=read(A/'실험/manifest.json');b=read(D/'baseline.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
paths=[r['target_path'] for r in old['files']]+['05_TESTS/CONTRACTS/test_native_completion_consumer_adr0680.py']
cmd=['06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',A,'--candidate-id','reviewed','--experiment-id',m['experiment_id'],'--arm-id','repaired','--run-id','run-001']
for path in paths:cmd+=['--source',path]
if not C.exists():run(*cmd)
drift=[]
for row in old['files']:
 path=row['target_path'];current=sha(R/path)
 if current!=row['upstream_sha256']:
  assert path=='00_SYSTEM/PIPELINE.json' or path.startswith('02_BACKEND/ENGINES/') or path in ['02_BACKEND/semantic_runtime/'+x+'.py' for x in ('navigation_build','navigation_storage','term_index','term_links')],path
  drift.append({'path':path,'initial':row['upstream_sha256'],'current':current,
   'selection':'Preserve initial serving code; concurrent factorized-audit development remains outside this repair.'})
 shutil.copy2(OLD/'snapshot'/path,C/'snapshot'/path)
put(D/'concurrency-rebase.json',{'observed_before_freeze':drift,'previous_candidate_preserved':str(OLD.relative_to(R)),
 'reason':'Refresh upstream provenance using a new candidate; retain tested initial serving dependencies, without editing other task files.'})
run('06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',C/'snapshot')
run('06_TOOLS/run_tool.py','adr_candidate.py','refresh',C)
run('06_TOOLS/run_tool.py','adr_candidate.py','freeze',C)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
pre=D/'pre-review-code'
shutil.copytree(code,pre)
for path in ['02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py','02_BACKEND/semantic_runtime/legal_agent/law_navigation.py','05_TESTS/CONTRACTS/test_judgment_loop_recovery.py']:
 assert sha(R/path)==next(row['upstream_sha256'] for row in old['files'] if row['target_path']==path)
 shutil.copy2(R/path,pre/path)
run('06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',pre)
dataset={'version':'known-public-recovery-v1','in_sample':True,'cases':[
 {'case_id':'venture-exercise','question':'벤처기업의 주식매수선택권은 언제부터 행사할 수 있나요?'},
 {'case_id':'pf-allowance','question':'부동산 PF 사업성 평가가 악화되는 경우 금융투자회사는 자산건전성 분류와 대손충당금 적립을 어떻게 연계해야 하는가?'},
 {'case_id':'rp-bonds','question':'금융투자회사가 일반 고객과 원화 환매조건부매매(RP)를 하는 경우 대상 채권의 종류와 신용등급 요건은 무엇인가?'}]}
put(D/'dataset.json',dataset)
put(D/'bindings.json',{'baseline_code':b['manifest']['code_root'],'stage':str(code.relative_to(R)),
 'source_generation':b['manifest']['data_path'],'candidate_manifest':str((C/'candidate.json').relative_to(R)),
 'experiment_client':str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(R))})
regression=['test_completion_boundary_adr0679.py','test_session_runtime_without_wiki_signing.py',
 'test_investigation_completion_adr0678.py','test_investigation_reinspection_adr0676.py',
 'test_investigation_chain_adr0671.py','test_law_navigation_state_contract_adr0661.py','test_followup_structure_lookup.py']
put(D/'execution-plan.json',{'regression':regression,'primary':'test_review_repairs.py',
 'native':'Selected code root contains an unchanged copy of the exact-file native consumer tests.',
 'pre_review_code':str(pre.relative_to(R)),'new_regressions_allowed':0,'exclusions':[],
 'test_change':'Recovery NOT_AVAILABLE test now requires recall completion rather than merely requesting RESEARCH.',
 'model_cases':dataset['cases'],'order':[['baseline','repaired'],['repaired','baseline'],['baseline','repaired']],
 'abort':'Record any setup/transport failures as failures; no retry, replacement, or rerun inside this ADR.'})
for q,c in zip(m['questions'],dataset['cases']):
 p=A/'실험'/q['file'];p.write_text(f"# {c['case_id']}\n\n## 1. 실행 메타\nADR-0689/run-001; baseline, repaired.\n\n## 2. 제품 요청\n{c['question']}\n\n## 3. 기준답변\nKnown-case diagnostic, no fixed answer score. Public source attribution and resolution traces are checked after output.\n\n## 4. 제품 입력의 원값\nartifacts/design/dataset.json; exact requests, profiles, source binding and model views in each case directory.\n\n## 5. 제품 모델 호출\nQwen3.8 / Parasail FP8 / reasoning none; maximum40 calls, 6400 output tokens, zero transport retries.\n\n## 6. 중간 LLM 호출\nRecorded in product provider transcripts; no additional model.\n\n## 7. 채점 호출\nNo model judge; exact quote and trace diagnostics only.\n\n## 8. 최종 판정\nImmutable result and post-output diagnostics recorded under artifacts/run-001. No holdout or promotion claim.\n")
 q['sha256']=sha(p)
m['design']['arms'][0].update(changes='Exact selected MAIN45 public API comparator',controls='Same public dataset, provider/model, limits and source generation')
m['design']['arms'][1].update(changes=read(D/'criteria.json')['scope'],controls='Same public dataset, provider/model, limits and source generation')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
 'candidate_id':'reviewed','experiment_id':m['experiment_id'],'arm_id':'repaired','run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_0689/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0689/run_case.py')}])
m['dataset'].update(frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Exactly three known public failures, alternating arm order, one attempt per arm/case; no exclusion or replacement.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
put(A/'실험/manifest.json',m)
shared=list((R/'05_TESTS').rglob('*.py'))+list((A/'artifacts/fixture-code').rglob('*.py'))+list(Path(__file__).parent.glob('*.py'))
shared+=list(D.glob('*.json'))+[C/'candidate.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
files={str(p.relative_to(R)):sha(p) for p in shared}
for base in [code,pre,R/b['manifest']['code_root']]:
 files.update({str(p.relative_to(R)):sha(p) for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'files':files,'code_root':str(code.relative_to(R)),
 'serving_files':{r['target_path']:sha(code/r['target_path']) for r in cm['files']},'revision_sha256':rev['revision_sha256']})
print('Frozen reviewed candidate and test comparators; no model calls yet')
