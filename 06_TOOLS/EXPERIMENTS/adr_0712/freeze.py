from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0712-compact-direct-read-context';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();base=read(D/'baseline.json');codes={'baseline':base['manifest']['code_root']};bindings=[]
for arm in ['compact']:
 C=R/'02_BACKEND/lawrag/research/candidates/adr_0712'/arm
 if '--reuse-frozen' not in sys.argv:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],cwd=R,check=True)
 cm=read(C/'candidate.json');rev=cm['revisions'][-1];codes[arm]=str((C/'revisions'/rev['revision_id']/'snapshot').relative_to(R))
 bindings.append({'candidate_id':arm,'arm_id':arm,'experiment_id':'ADR-0712-experiment-v1','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0712/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0712/run_case.py')})
code=R/codes['compact'];sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
prepare(R,code,R/base['manifest']['data_path'],'compact-input-frozen-preview',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
integration=read(D/'integration-draft.json');binding={k:bindings[-1][k] for k in ('manifest_path','manifest_sha256','revision_id','revision_sha256')};integration['candidate']=binding
for row in integration['changes']:
 row['reason']='Preserve MAIN49; lazy selection detail, one original text per source in navigation wire view with assessment quote text retained, concise full action ledger and empty-array schema simplification. Same original scopes, citations and state guards.'
files=dict(base['manifest']['files'])
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for name,h in files.items():assert sha(code/name)==h,name
cm=read(R/binding['manifest_path'])
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Synthetic contract test, research-only client or build fixture' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':integration['changes'],'base_code_root':base['manifest']['code_root'],'stage':codes['compact'],'reason':'Frozen complete package verified in the same data/profile/service path; reviewed scoped edits will be installed without overwriting unrelated working files.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};integration['rebase_receipt']=ref;put(D/'integration.json',integration)
from semantic_runtime.release_integration import check
check(R,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},files,integration)
put(D/'bindings.json',{'codes':codes,'stage':codes['compact'],'baseline_code':codes['baseline'],'source_generation':base['manifest']['data_path'],'experiment_client':str((code/'02_BACKEND/lawrag/research/experiment_client.py').relative_to(R))})
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=bindings;m['design']['release_rebase']=ref
for q,c in zip(m['questions'],read(D/'dataset.json')['cases']):
 p=A/'실험'/q['file'];p.write_text(f"# {c['case_id']}\n\n## 1. 실행 메타\nADR0712/run-001, MAIN49/compact. Exact code and data: design/freeze.json.\n\n## 2. 사용자 질문 원문\n{c['question']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\nPinned original is separately held in design/gold.json. Product runner never reads it.\n\n## 4. 제품 입력을 구성한 원값\nPublic question, approved65 documents, same generation/model/budgets. Per-case request/profile and complete raw provider inputs are retained.\n\n### 회수·탈락 단계 원장 — run·arm별\nCatalogue, recalled, acquired and physically presented canonical article roots are computed from native journals and provider inputs after outputs.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\nQwen3.8/Parasail FP8/reasoning none/no fallback. artifacts/run-001/<arm>/{c['case_id']}/provider stores actual request/response/usage.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\nAll phases and bounded repairs use the same audited client; maximum40 attempts per request.\n\n## 7. 채점 호출과 반복 판정\nNo evaluator LLM. Quote/access/binding/state checks and post-output original-source review; no case replacement or rerun.\n\n## 8. 사례 최종 판정\nSingle result.json per arm and case. No result yet at freeze.\n")
 q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
paths=list(D.glob('*.json'))+[R/b['manifest_path'] for b in bindings]+[R/'06_TOOLS/EXPERIMENTS/adr_0712/run_case.py',R/'06_TOOLS/EXPERIMENTS/adr_0712/run_all.py',R/'06_TOOLS/EXPERIMENTS/adr_0712/run_contracts.py',R/'06_TOOLS/EXPERIMENTS/adr_0712/test_compact_input.py',R/'06_TOOLS/EXPERIMENTS/adr_0712/audit.py',R/'06_TOOLS/EXPERIMENTS/adr_0707/test_entry.py',R/'06_TOOLS/EXPERIMENTS/adr_0707/test_title_search.py',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
frozen={str(p.relative_to(R)):sha(p) for p in paths}
for root in codes.values():
 frozen.update({str(p.relative_to(R)):sha(p) for p in (R/root).rglob('*') if p.is_file() and '__pycache__' not in p.parts})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':codes['compact'],'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen complete package:',len(files),'serving files;8 public requests not started')
