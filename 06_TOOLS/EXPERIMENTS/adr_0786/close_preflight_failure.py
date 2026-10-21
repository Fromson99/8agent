"""Close the observed import failure without replaying or rewriting its run."""
from pathlib import Path
import gzip,hashlib,json,re,sqlite3,sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
A=R/'04_EXPERIMENTS/ADR/ADR-0786-risk-compare-qwen-live-probe';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
g=read(D/'authorization.json');gold=read(D/'gold-offline.json');pool=set()
with sqlite3.connect('file:'+str(R/g['generation_path']/'navigation/navigation.sqlite')+'?mode=ro',uri=True) as db:
 for did,raw in db.execute('SELECT document_id,json FROM source'):
  if did in g['documents']:
   v=json.loads(raw);pool.add((did,int(v['unit_id'])))
graded=[]
for arm in ('baseline','qwen'):
 rec=StageLedgerRecorder('liquidity-ratio',arm,identity_canonicalizer)
 rec.record_stage('source','source',sorted(pool))
 rec.record_stage('retrieve','retrieve',[],parent_stage_ids=['source'],discard_reasons=[(p,'Run ended before source search: '+('external model blocked' if arm=='baseline' else 'local research import missing')) for p in sorted(pool)])
 rec.record_stage('present','present',[],parent_stage_ids=['retrieve'])
 graded.append(grade_capture(rec.capture(),[(gold['external']['document_id'],int(gold['external']['unit_id']))]))
ledger=build_experiment_artifact('ADR-0786','ADR-0786-experiment-v1',[build_run_artifact('run-001',graded,{a:['source','retrieve','present'] for a in ('baseline','qwen')})])
lp=O/'retrieval-ledger.json.gz';lp.write_bytes(gzip.compress(json.dumps(ledger,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
result={'strict_success':False,'by_arm':{a:read(O/a/'result.json') for a in ('baseline','qwen')},
 'model_physical_calls':0,'usage':{'model_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},
 'cause':'Pinned lawrag package has no research subpackage; lazy ExperimentClient import failed before client construction or HTTP send',
 'reproduction':'candidate-only sys.path -> from lawrag.research.experiment_client import ExperimentClient -> ModuleNotFoundError: lawrag.research',
 'external_target_read':False,'internal_target_registered':False,'primary_two_paragraph_comparison':False,
 'ledger_gold_scope':'Only registered external article has a real coordinate. Missing internal gold is a separate primary failure; no invented coordinate.',
 'contracts_passed':68,'main_changed':False,'genos_tested':False}
put(O/'result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={a:{'status':'complete','workflow_status':result['by_arm'][a]['workflow_status'],'model_calls':0} for a in ('baseline','qwen')},
 comparisons=[{'primary_pass':False,'cause':result['cause']}],judge_disagreements=0,usage=result['usage'],latency={a:result['by_arm'][a]['elapsed_seconds'] for a in ('baseline','qwen')},error_taxonomy=['other: local import failure before provider send','required_issue_omission: internal target not registered'])
ra=m['retrieval_accounting'];ra['corpus_total']=len(pool)
for key in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):ra[key]={a:len(pool) if key=='before_filter' else 0 for a in ('baseline','qwen')}
ra['stage_ledger'].update(summary_run_id='run-001',artifact_path=str(lp.relative_to(R)),sha256=sha(lp))
text=(A/'README.md').read_text();heads=re.findall(r'^## \d+\. .+$',text,re.M)
paragraphs=['기각: 실제 Qwen 호출 전 연구 모듈 로딩 실패. 모델 호출0회. MAIN66 유지.',
 '기존 workflow는 외부 모델을 차단한다. 명시 사용자 승인에 따른 실험 전용 authorization을 추가했다.',
 '원문 질문만 입력하고 지정된 두 정답 조문을 실제로 읽고 대사해야 통과한다. 정답은 offline 파일에 분리했다.',
 '동일 데이터로 부모 baseline과 후보를 각각1회 실행했다. 외부 연결의 모듈 누락이 발견되어 재시도하지 않고 새 ADR에서 수정한다.',
 'Qwen3.8/Parasail FP8/none/fallback없음 정책,331개 코드파일,360개 문서 범위를 동결했다. 정답 내규는 이 corpus에 없다.',
 '계약68개 통과. baseline blocked, 후보 failed. provider HTTP 호출은0회이며 모델 성능 결과가 아니다.',
 result['cause'],
 '모델 토큰·비용0. 후보 전체 실행23.716초. 실제 원문 읽기0. 전체 좌표와 미회수 사유는 압축 ledger에 보존했다.',
 'gateway의 MODEL_TRANSPORT_ERROR는 실제 provider 장애가 아니라 local adapter import 실패를 감쌌다. 재현 가능한 실행기 결함이다.',
 '실제 LLM 검색·관계·대사 정확도 미검증. 내규 정답 원문 미등록과 현재 버전 미확인은 별도 한계다.',
 '기존 실패를 보존한다. 제품 검색/프롬프트 변경 없이 공통 client 모듈을 후보에 포함하는 후속 ADR을 선점한다. MAIN/GENOS 미변경.',
 '실행: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0786/run.py baseline 또는 qwen. 이미 실행된 arm 재사용은 차단된다. 원장 복원: Python gzip.decompress로 retrieval-ledger.json.gz 해제.']
front=text.split('\n## ',1)[0].split('\n# ADR-',1)[0].replace('status: Proposed','status: Rejected')
(A/'README.md').write_text(front+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(heads,paragraphs))+'\n')
qpath=A/'실험'/m['questions'][0]['file'];qh=re.findall(r'^## \d+\. .+$',qpath.read_text(),re.M)
qp=['run-001; baseline/qwen; raw exact; no actual HTTP model call. Timestamp and code binding in artifacts/run-001/*/result.json.',
 g['question'],'금융투자업규정 제3-24조의4 제2항 / 위험관리기준시행세칙 제6-4조 제1항. Offline only.',
 'Exact request and code/data scope: artifacts/design/request.json, authorization.json, freeze.json. Complete coordinate transitions: artifacts/run-001/retrieval-ledger.json.gz. Internal gold has no registered coordinate.',
 'Baseline no reserved attempt. Qwen one locally reserved attempt, no provider send; exact system/user/schema retained in runtime/workflows/*/journal.sqlite model_attempt.request_json. No provider response exists.',
 'No intermediate model response; import failure at intake. Local attempt classified UNKNOWN by gateway; actual HTTP send count0.',
 'No model evaluator. Deterministic inspection of client absence, journal and source inventory; no regrade or majority vote.',
 'Both gold paragraphs were not read or compared. Failure: other (local import), plus missing internal data. Next branch bundles ExperimentClient and checks import before request.']
qpath.write_text('# 질문001 — liquidity-ratio\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qh,qp))+'\n')
m['questions'][0]['sha256']=sha(qpath);put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 실제 Qwen 연결 probe\n\n결과: provider 송신 전 로컬 모듈 로딩 실패. 계약68개 통과. 원래 실패 및 모든 입력은 artifacts에 보존. 원문·토큰·법률 비교 성공 주장은 없다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0786','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(files)]})
print(json.dumps({'strict_success':False,'physical_calls':0,'corpus_article_roots':len(pool),'contracts':68}))
