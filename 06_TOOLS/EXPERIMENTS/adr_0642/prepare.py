from pathlib import Path
import json,hashlib,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0642-shortcut-main-integration-holdout';D=A/'artifacts/design'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def read(p):return json.loads(p.read_text())
assert not (D/'freeze.json').exists()
cases=[{'case_id':'privacy-definition','document_id':'ab58f0d6419c6868','question':'개인정보 보호법 제2조제1호가 정한 개인정보의 정의와 가목·나목·다목의 범위를 설명해 주세요.'},
 {'case_id':'commercial-law-order','document_id':'7bbe815ff43b6635','question':'상법 제1조에 따르면 상사에 관하여 상법에 규정이 없는 경우 적용할 규범의 순서는 무엇인가요?'},
 {'case_id':'disclosure-principle','document_id':'c880f601a60ef856','question':'공공기관의 정보공개에 관한 법률 제3조가 정한 정보공개의 원칙을 설명해 주세요.'}]
put(D/'inputs.json',cases)
generation=R/'01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation';manifest=read(generation/'manifest.json');grant=read(R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
assert manifest['generation_id']==grant['generation_id'] and sha(generation/'store.sqlite')==grant['source_store_sha256']
assert {c['document_id'] for c in cases}<=set(grant['public_document_ids'])
gold={};coordinate={};scope=set(c['document_id'] for c in cases)
blocks={'privacy-definition':[2,3,4,5,6],'commercial-law-order':[2],'disclosure-principle':[11]}
rubrics={'privacy-definition':'살아 있는 개인 정보라는 범위, 직접 식별 정보, 다른 정보와 쉽게 결합해 식별 가능한 정보 및 시간·비용·기술·입수가능성 고려, 추가정보 없이는 식별할 수 없는 가명정보를 모두 포함한다. 법인을 개인정보 주체로 단정하거나 가명정보를 제외하지 않는다.',
 'commercial-law-order':'상사에 관하여 상법(본법) 규정이 없으면 상관습법, 상관습법이 없으면 민법을 적용한다. 우선순위를 역전하지 않는다.',
 'disclosure-principle':'공공기관 보유·관리 정보는 국민의 알권리 보장 등을 위해 법에서 정하는 바에 따라 적극 공개하여야 한다. 모든 정보를 예외 없이 공개한다고 확대하지 않는다.'}
with sqlite3.connect('file:'+str(generation/'store.sqlite')+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 for c in cases:
  originals=[dict(db.execute('SELECT document_id,block_id,text,unit_id FROM source_block WHERE document_id=? AND block_id=?',(c['document_id'],str(b))).fetchone()) for b in blocks[c['case_id']]]
  gold[c['case_id']]={'rubric':rubrics[c['case_id']],'originals':originals,'version':manifest['generation_id'],'source_hash':manifest['store_sha256']}
 for doc,uid,raw in db.execute('SELECT document_id,unit_id,json FROM source_unit'):
  if doc not in scope:continue
  value=json.loads(raw)
  if value.get('family')=='article':coordinate[doc+'|'+str(uid)]={'doc_id':doc,'node':str(uid)}
put(D/'gold.json',gold);put(D/'coordinates.json',coordinate)
active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path'])
binding={'generation':str(generation.relative_to(R)),'generation_manifest_hash':sha(generation/'manifest.json'),'source_sha256':manifest['store_sha256'],
 'policy_hash':sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'grant_hash':sha(R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'),
 'active_pointer_hash':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'baseline_release':active,'baseline_code':release['code_root'],
 'baseline_files':release['files'],'candidate':'02_BACKEND/lawrag/research/candidates/adr_0642/integrated','scope':sorted(scope)}
put(D/'bindings.json',binding)
m=read(A/'실험/manifest.json');m['design'].update(hypothesis='새 지속 기록·위키 계약을 전체 v6 실행에 연결해도 독립 공개 법률 질의에서 기존 MAIN 대비 답변 품질을 회귀시키지 않는다.',primary_metric='Three independent legal-family pairwise source-supported answers; zero per-case regression',success_criteria='Candidate 3/3 source-supported by both offline judges; zero baseline-only successes; no source/ACL/intake loss. Candidate median latency <= baseline*1.30+10 seconds and total online cost <= baseline*1.30+0.01 USD. All 81 prior contracts pass in the staged integration. Full MAIN additionally needs a valid provenance-bound non-waiver promotion path.',failure_criteria='Any quality regression, product failure, missing usage, exceeded cost/latency tolerance, contract or provenance failure prevents MAIN promotion.',criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
m['design']['arms'][0]['changes']='Frozen active local MAIN v5 code, common max40 model attempts, wall480s/output6400 budget; no shortcut'
m['design']['arms'][1]['changes']='Full current v6 + frozen ADR0641 shortcut integration; all flags enabled; no preapproved judgment data'
for arm in m['design']['arms']:arm['controls']='Same explicit documents, source generation, model/provider, physical-call cap40, wall480s, output6400; same public question; no gold in product context'
m['dataset'].update(name='three independent public-law document families',version='20261005-holdout-v1',frozen_source=str((D/'inputs.json').relative_to(R)),sha256=sha(D/'inputs.json'),legal_version_checked=True,reference_version_checked=True,current_law_verified=False,caveat='Stored source version only; not a current-law advice claim. These three families were not used in shortcut compiler development.')
stages=[{'stage_id':'source','kind':'source','parent_stage_ids':[]},{'stage_id':'read','kind':'retrieve','parent_stage_ids':['source']},{'stage_id':'present','kind':'present','parent_stage_ids':['read']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['baseline','integrated']}
m['retrieval_accounting'].update(changed=True,corpus_total=len(coordinate),not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-stage-ledger.json').relative_to(R)),not_applicable_reason=None)
m['runs'][0].update(purpose='primary',selection_rule='All three preregistered independent legal document families, paired baseline then candidate; no case replacement or rerun after output',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1},{'role':'offline-source-judge','class':'offline_evaluator','model':'qwen/qwen3.8-27b','repeats':2}]
put(A/'실험/manifest.json',m)
put(D/'freeze.json',{'files':{str(p.relative_to(R)):sha(p) for p in D.glob('*.json')},'success_criteria':m['design']['success_criteria']})
print('holdout inputs, gold and acceptance frozen before calls')
