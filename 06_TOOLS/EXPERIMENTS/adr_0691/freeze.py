"""Bind exact complete serving inventory and runners before any model request."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0691-judgment-loop-unstarted-holdout';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0691/repaired'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],cwd=R,check=True)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';b=read(D/'baseline.json')
sys.dont_write_bytecode=True;sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.control import prepare
prepare(R,code,R/b['manifest']['data_path'],'judgment-loop-frozen-preview',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
d=read(D/'integration-draft.json');binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']};d['candidate']=binding
for row in d['changes']:row['reason']='Preserve prior completed investigation/core-route development and judgment recovery; repair gap identity, shared issue render and per-gap receipts; bind actual configuration and alias projection. Concurrent factorized-audit code excluded.'
files=dict(b['manifest']['files'])
for row in d['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for f,h in files.items():assert sha(code/f)==h,f
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':b['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,
 'excluded_candidate_paths':{row['target_path']:'Non-serving evaluator client or synthetic contract test' for row in cm['files'] if row['target_path'] not in files},
 'reviewed_changes':d['changes'],'base_code_root':b['manifest']['code_root'],'stage':str(code.relative_to(R)),
 'reason':'Entire frozen package evaluated directly; only scoped judgment edits installed into mutable working code, preserving concurrent storage work.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};d['rebase_receipt']=ref;put(D/'integration.json',d)
from semantic_runtime.release_integration import check
check(R,{'pointer':b['pointer'],'pointer_sha256':b['pointer_sha256']},files,d)
put(D/'bindings.json',{'baseline_code':b['manifest']['code_root'],'stage':str(code.relative_to(R)),'source_generation':b['manifest']['data_path'],'experiment_client':str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(R))})
m=read(A/'실험/manifest.json');m['design']['release_rebase']=ref
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'repaired','experiment_id':m['experiment_id'],'arm_id':'repaired','run_ids':['run-001'],**binding,'runner_path':'06_TOOLS/EXPERIMENTS/adr_0691/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0691/run_case.py')}])
dataset=read(D/'dataset.json')
for q,c in zip(m['questions'],dataset['cases']+dataset['regression_cases']):
 p=A/'실험'/q['file'];p.write_text(f"# {c['case_id']}\n\n## 1. 실행 메타\nADR-0691/run-001, paired baseline and repaired. Frozen inputs and exact code hashes: artifacts/design/freeze.json.\n\n## 2. 사용자 질문 원문\n{c['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\nPrimary public source text is pinned separately in design/gold.json. Known regressions do not count as unseen cases. Semantic detail is diagnostic; no offline judge model.\n\n## 4. 제품 입력을 구성한 원값\nDataset contains only public questions. Per-case request/profile and provider request transcripts preserve complete product inputs.\n\n### 회수·탈락 단계 원장 — run·arm별\nNative journals bind catalogue → recall → acquired original → source-text presented. Canonical article root ledger is computed after output; gold never enters product process.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\nQwen3.8 / Parasail FP8 / reasoning none / no fallback;40 calls maximum,6400 output tokens. Raw prompts/responses under artifacts/run-001/<arm>/{c['case_id']}/provider.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\nAll product phases and bounded repairs use the same audited client and are recorded, no hidden calls.\n\n## 7. 채점 호출과 반복 판정\nNo judge LLM; exact quote/scope/state/binding contracts and post-output source review.\n\n## 8. 사례 최종 판정\nResults will be recorded once in result.json; no rerun, case replacement or post-output candidate modification.\n")
 q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
shared=list(Path(__file__).parent.glob('*.py'))+list((R/'05_TESTS').rglob('*.py'))+list(D.glob('*.json'))+[C/'candidate.json',R/'06_TOOLS/EXPERIMENTS/adr_0689/test_review_repairs.py']
shared+=list((R/'04_EXPERIMENTS/ADR/ADR-0689-judgment-loop-review-repair/artifacts/fixture-code').rglob('*.py'))
shared+=[R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
def receipts(v):
 if isinstance(v,dict):
  for k,x in v.items():
   if isinstance(x,str) and 'receipt' in k and (R/x).is_file():shared.append(R/x)
   else:receipts(x)
 elif isinstance(v,list):
  for x in v:receipts(x)
receipts(read(R/'00_SYSTEM/WORKSPACE.json'))
frozen={str(p.relative_to(R)):sha(p) for p in shared}
for root in (code,R/b['manifest']['code_root']):frozen.update({str(p.relative_to(R)):sha(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':frozen,'serving_files':files,'candidate':binding})
print('Complete serving package frozen',len(files),'files; paired public cases12; model calls0')
