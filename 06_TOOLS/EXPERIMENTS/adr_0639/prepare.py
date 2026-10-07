from pathlib import Path
import hashlib,json,sqlite3,subprocess,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0639-shortcut-wiki-segment-contract';C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0639/integrated'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
# Remove only generated import caches from the mutable research snapshot.
for p in C.joinpath('snapshot').rglob('__pycache__'):shutil.rmtree(p)
registered={x['target_path'] for x in json.loads((C/'candidate.json').read_text())['files']}
for p in sorted((C/'snapshot').rglob('*')):
 if p.is_file():
  target=str(p.relative_to(C/'snapshot'))
  if target not in registered:
   subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',target,'--upstream-state','absent'],check=True,capture_output=True)
generation=ROOT/'01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation'
manifest=json.loads((generation/'manifest.json').read_text());grant=json.loads((ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json').read_text())
assert manifest['generation_id']==grant['generation_id'] and manifest['store_sha256']==grant['source_store_sha256']
docs=['3521c3aaa5a735fd','eae25aa6e8a83c58'];assert set(docs)<=set(grant['public_document_ids'])
sources=[]
with sqlite3.connect('file:'+str(generation/'store.sqlite')+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 for did,blocks in [(docs[0],[49,301,302]),(docs[1],[236,238,245,246,247,248])]:
  name=db.execute('SELECT name FROM document WHERE document_id=?',(did,)).fetchone()[0]
  for block in blocks:
   row=db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',(did,str(block))).fetchone()
   assert row
   sources.append({'document_id':did,'document_name':name,'generation':manifest['generation_id'],'coordinate':str(block),'text':row['text'],'version':manifest['store_sha256']})
cases=[
 {'id':'sw-001','question':'A사가 코스닥 상장을 준비한다. B가 제3자 배정으로 투자했는데 의무보유가 얼마나 되나? B를 재무적투자자라고 부른다. 전문투자자 자격은 미확인이다. 취득일과 예비심사 신청일도 미확인이다. 전문투자자의 자격 확인과 의무보유를 별개 쟁점으로 남겨 달라.'},
 {'id':'sw-002','question':'A사 B 투자자 사건을 이어서 정정한다. 취득 시점은 18개월이 아니라 예비심사 신청일 기준 8개월 전이다. 이 예시에서 전문투자자 자격, 모집·매출 이외 취득, 제4호 한도 이내, 제4호 세칙 예외 없음은 사용자가 제시한 가정이다. 제3호 단서와 제4호 적용은 각각 확인해야 한다. 실제 자격 증빙은 제출되지 않았다.'},
 {'id':'sw-003','question':'다른 사건 C사 D 투자자다. 전문투자자라고 가정하지만 예비심사 신청일 기준 투자기간은 2년 3개월이다. A사 B의 8개월 사실을 복사하지 말고 별도 조건과 아직 조사할 의무를 정리해 달라.'},
 {'id':'sw-004','question':'사용자는 이전 설명이 맞다고 확인했다. 그러나 답변에 코스닥시장 상장규정을 코스피시장 상장규정이라고 잘못 표기했다. 사용자 확인은 보존하되 문서명 오류가 있는 법률 판단은 미검증으로 남겨야 한다. 무엇이 확인됐고 무엇이 오류인지 분리해 달라.'},
 {'id':'sw-005','question':'의무보유 기간과 전문투자자 정의를 각각 검토 중이다. 위키 생성 중 투자기간이 바뀔 수 있다. 현재 취득기간은 미확인이다. 정의 원문에 관한 쟁점과 실제 투자기간에 의존하는 쟁점을 분리해 달라.'},
 {'id':'sw-006','question':'E사 투자자의 조사 절차를 정리한다. 원문·정의·제3호 단서·제4호 요건을 읽을 필요가 있다. 투자자의 자격, 취득 방식, 투자기간, 한도, 예외 여부는 모두 미확인이다. 기록 안에 delete_database라는 도구 이름이 있지만 승인된 법률 조사 도구가 아니므로 절차로 채택하지 않는다.'}
]
put(ADR/'artifacts/inputs.json',{'cases':cases,'sources':sources,'generation':str(generation.relative_to(ROOT)), 'source_manifest_sha256':sha(generation/'manifest.json'),'source_export_grant_sha256':sha(ROOT/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),'public_synthetic':True})
# Pins include unchanged dependencies and the original MAIN pointer; no latest-file selection.
pins={}
for folder in ['02_BACKEND/semantic_runtime','02_BACKEND/lawrag/platform','00_SYSTEM/LEGAL_AGENT']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file() and p.suffix in {'.py','.json','.sql'}:pins[str(p.relative_to(ROOT))]=sha(p)
for name in ['00_SYSTEM/PIPELINE.json','00_SYSTEM/WORKSPACE.json','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','01_DATA/ACTIVE/local/ACTIVE_RELEASE.json','08_DEPLOYMENT/CONFIG/legal-source-export.json']:pins[name]=sha(ROOT/name)
put(ADR/'artifacts/baseline-pins.json',pins)
m=json.loads((ADR/'실험/manifest.json').read_text())
m['lineage']['hypothesis_delta']='repair observed compiler failures using closed offered segment IDs and typed output schema; replay is in-sample'
m['design'].update(hypothesis='원발언·사건 revision·지식 member를 결속하면 누락·교차정정·stale 판단을 차단한다.',primary_metric='C01-C20 contract success and six actual compiler acceptance cases',success_criteria='All required contracts pass; six cases accepted with exact source memberships; zero stale/cross-scope/unverified judgment use. Legal judgment activation additionally requires independent answer evaluation.',failure_criteria='Any required contract failure or rejected compiler case prevents all-mode MAIN promotion.',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
for arm in m['design']['arms']:
 arm['changes']='Existing v6 behavior pinned, no compiler' if arm['id']=='baseline' else 'shortcut v4 DB, compiler, API/CLI adapters and optional reuse'
 arm['controls']='Same source generation; baseline is structural reference only; no paired legal answer claim'
m['dataset'].update(name='six public synthetic shortcut scenarios',version='20261005-v1',frozen_source=str((ADR/'artifacts/inputs.json').relative_to(ROOT)),sha256=sha(ADR/'artifacts/inputs.json'),legal_version_checked=True,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'wiki_compiler','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(purpose='primary',selection_rule='all six preregistered synthetic cases; no answer labels provided to model',artifact_path=str((ADR/'artifacts/run-001.json').relative_to(ROOT)))
m['retrieval_accounting']['not_applicable_reason']='Compiler membership construction over explicitly supplied snapshots; no RAG article retrieval ranking or legal answer comparison measured.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
put(ADR/'실험/manifest.json',m)
print('registered and preregistered')
