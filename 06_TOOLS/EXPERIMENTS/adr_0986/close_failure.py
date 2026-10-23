"""Seal the observed model0 integrity failure; no retry or altered success."""
from common import *
import sys,sqlite3
sys.path.insert(0,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0987'))
from report_common import finish_documents,seal
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
m=read(ADR/'실험/manifest.json');cases=read(DES/'cases.json');result=read(RUN/'result.json');assert sum(x['model_calls'] for x in result['results'])==0
ledger=[]
for row in result['results']:
    rec=StageLedgerRecorder(row['case_id'],row['arm'],identity_canonicalizer)
    rec.record_stage('original_read','source',[],executed=False,skip_reason='Engine code pin mismatch before model or source investigation')
    rec.record_stage('final_cited','present',[],parent_stage_ids=['original_read'],executed=False,skip_reason='No answer published')
    ledger.append(grade_capture(rec.capture(),[]))
led=build_experiment_artifact('ADR-0986',m['experiment_id'],[build_run_artifact('run-001',ledger,{a:['original_read','final_cited'] for a in ['baseline','knowledge']})]);put(RUN/'retrieval-ledger.json',led)
failure={'status':'complete','outcome':'BLOCKED_BEFORE_MODEL','api_attempts':8,'product_model_calls':0,'answers':0,
 'cause':'Candidate knowledge_bridge changed but engine manifests retained original code hash.',
 'runner_defect':'HTTP422 nested hash mismatch was not recognized as fatal; remaining7API requests repeated the same model0 failure. Corrected only in successor ADR0987.',
 'storage_verified':'4source wiki units,9ontology records,public source checks,AND truth table and7guards',
 'speed_or_quality_evidence':False,'main_changed':False,'genos_executed':False}
put(ART/'failure-summary.json',failure)
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={a:{'status':'complete','correct':0,'total':4,'accuracy':0,'criteria_met':False,'answer_quality':'NOT_ASSESSED_NO_MODEL_CALLS'} for a in ['baseline','knowledge']},
 usage={'product_model_calls':0,'offline_evaluator_calls':0},latency={'basis':'pre-model failure only; not a speed comparison'},judge_disagreements=0,error_taxonomy=[failure])
m['retrieval_accounting'].update(corpus_total=0,before_filter=0,after_filter=0,presented_total=0,presented_mean=0,presented_p50=0,presented_p95=0,golden_recall=0,selectivity=0,
 not_applicable_reason='No retrieval executed; zero counts are dispatch outcome, not coverage or corpus-size measurement.')
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json');put(ADR/'실험/manifest.json',m)
parts=['원문 중심 저장 검사는 통과했지만 네이티브 API8요청은 엔진 코드 해시 불일치로 모두 모델 호출 전에 차단됐다. 실제 모델0회. 속도·정답 비교 불가.',
 '과거 실제 실패 로그를 원문 보완한 가정 성공 입력으로 사용해 지식 저장과 재사용을 연결하려 했다. 실패 로그의 성공 판정은 바꾸지 않았다.',
 '[사전 기준](artifacts/design/criteria.json). 원문·권한·코드·상태 무결성 실패는 중단 대상이다.',
 '공개 CM4×2arm. baseline off/knowledge consume, 같은 후보 네이티브 API. 원문4개를 일차 저장 단위로 변경한 뒤 동결했다.',
 'MAIN99 원문 세대·후보422파일·Qwen3.8 정책. 실제 모델 호출 전 차단. [동결](artifacts/design/freeze.json).',
 json.dumps(failure,ensure_ascii=False,indent=2),
 'knowledge_bridge 변경 후 engine manifest 파일 해시를 갱신하지 않았다. 차단 자체는 올바르게 동작했다. 실행기가 중첩된422오류를 치명적 실패로 분류하지 않아 같은 차단을8요청에 반복한 결함도 기록한다.',
 '모델 호출0, 응답0. API 실패 소요시간은 재사용 효과로 계산하지 않는다. [원장](artifacts/run-001/retrieval-ledger.json).',
 '위키·온톨로지 저장 성공과 실제 RAG 답변 성공은 별개다. 저장만으로 E2E 성공이라고 보고하지 않는다.',
 '로컬 연구 SQLite·공개 자료 검사. Oracle/Dataiku/GENOS 접속·배포 없음. 완성한 자동 추출 파이프라인도 아님.',
 '실패 원시 기록과 frozen rev-001을 보존. [후속 ADR0987](../ADR-0987-cm-source-ontology-native-e2e/README.md)에서 엔진 핀과 조기 중단을 수정한다.',
 '준비·저장 검사·동결·실제 API실패 기록을 보존했다. 이 완료 run을 덮어쓰거나 재호출하지 않는다.']
cp={c['id']:['run-001 baseline/knowledge, model0',c['question'],'평가 자료는 제품에 투입하지 않았다. 모델 호출 없어 법률 답변 평가 미실시.',
 '[원문·개념 저장](../artifacts/run-001/gold_layer/source-concept-registry.json)과 [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json): 두 단계 모두 미실행.',
 '모델 호출0; 각 arm/'+c['id']+'/response.json에 API 오류 보존.', '중간 모델 호출0. 해시 검사 실패.', '채점 호출0; 미실행을 정답·오답률로 해석하지 않음.',json.dumps(failure,ensure_ascii=False)] for c in cases}
finish_documents(ADR,'원문 중심 저장 통과·네이티브 해시 검사 차단',parts,cp);seal(ADR)
print('ADR0986 failure preserved; model0,8API failures; successor0987')
