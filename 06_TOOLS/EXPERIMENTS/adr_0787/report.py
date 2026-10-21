"""Offline inspection of immutable actual calls; never invokes or modifies product."""
from pathlib import Path
from types import SimpleNamespace
from collections import defaultdict
import gzip,hashlib,json,re,sqlite3,sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
from lawrag.core.rag.legal_coordinates import article_root
A=R/'04_EXPERIMENTS/ADR/ADR-0787-risk-compare-qwen-connected';D=A/'artifacts/design';O=A/'artifacts/run-001'
P=R/'04_EXPERIMENTS/ADR/ADR-0786-risk-compare-qwen-live-probe'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
g=read(D/'authorization.json');gold=read(D/'gold-offline.json');f=read(D/'freeze.json')
assert all(sha(R/n)==h for n,h in f['files'].items())
rawpool=json.loads(gzip.decompress((P/'artifacts/run-001/retrieval-ledger.json.gz').read_bytes()))['runs'][0]['arms'][0]['cases'][0]['stages'][0]['after']
units=defaultdict(dict)
with sqlite3.connect('file:'+str(R/g['generation_path']/'store.sqlite')+'?mode=ro',uri=True) as db:
 for did,uid,parent,surface in db.execute("SELECT document_id,unit_id,parent_id,json_extract(json,'$.surface') FROM source_unit WHERE document_id IN ("+','.join('?' for _ in g['documents'])+")",list(g['documents'])):
  if did in g['documents']:units[did][int(uid)]={'id':int(uid),'parent':int(parent) if parent is not None else None,'surface':surface}
def canonical(coordinate):
 d,u=coordinate
 return d,int(article_root(SimpleNamespace(by_id=units[d]),int(u)))
pool={canonical((r['doc_id'],r['node'])) for r in rawpool}
target=(gold['external']['document_id'],int(gold['external']['unit_id']))
assert target in pool
qp=O/'qwen';p=next(qp.glob('runtime/workflows/*/journal.sqlite'))
with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 state=json.loads(db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()[0])
 handles={r['handle']:json.loads(r['identity_json']) for r in db.execute("SELECT * FROM navigation_handle WHERE kind='U'")}
 evidence={r['evidence_id']:dict(r) for r in db.execute('SELECT * FROM evidence_unit')}
 spans=[dict(r) for r in db.execute('SELECT * FROM evidence_span')]
 views=[json.loads(r[0]) for r in db.execute('SELECT body_json FROM model_view ORDER BY created_seq')]
 errors=[{'kind':r[0],**json.loads(r[1])} for r in db.execute("SELECT kind,payload_json FROM event WHERE kind IN ('OUTPUT_SCHEMA_INVALID','WORKFLOW_STOPPED','WORKFLOW_CALL_FAILED') ORDER BY seq")]
 attempts=[dict(r) for r in db.execute('SELECT attempt_id,status,receipt_json,input_tokens,output_tokens,cost_usd FROM model_attempt ORDER BY created_seq')]
def coords(value):
 out=set()
 if isinstance(value,list):
  for x in value:out.update(coords(x))
 elif isinstance(value,dict):
  h=handles.get(value.get('node'))
  if h:out.add(canonical((h['document_id'],h['unit_id'])))
  e=evidence.get(value.get('evidence_id'))
  if e:out.add(canonical((e['document_id'],e['unit_id'])))
  for x in value.values():
   if isinstance(x,(dict,list)):out.update(coords(x))
 return out
readcoords={canonical((e['document_id'],e['unit_id'])) for e in evidence.values()}
retrieved=coords(state['history'])|readcoords
presented=coords(views)
assert presented<=retrieved
searches=[]
for row in state['history']:
 if row['action']['operation'].startswith('search'):
  searches.append({'side':row['action']['side'],'query':row['action']['args'].get('query'),
   'items':len(row['result']['items']),'has_next_page':bool(row['result'].get('next_cursor')),
   'target_in_result':target in coords(row['result'])})
graded=[]
for arm,got,shown in [('baseline',set(),set()),('qwen',retrieved,presented)]:
 rec=StageLedgerRecorder('liquidity-ratio',arm,identity_canonicalizer)
 rec.record_stage('source','source',sorted(pool))
 rec.record_stage('retrieve','retrieve',sorted(got),parent_stage_ids=['source'],
  discard_reasons=[(p,'No successful source result before run ended; inherited import failure' if arm=='baseline' else 'Not returned by completed searches/reads; remaining pages were not investigated') for p in sorted(pool-got)])
 rec.record_stage('present','present',sorted(shown),parent_stage_ids=['retrieve'],discard_reasons=[(p,'Not included in a submitted workflow model view') for p in sorted(got-shown)])
 graded.append(grade_capture(rec.capture(),[target]))
ledger=build_experiment_artifact('ADR-0787','ADR-0787-experiment-v1',[build_run_artifact('run-001',graded,{a:['source','retrieve','present'] for a in ('baseline','qwen')})])
lp=O/'retrieval-ledger.json.gz';lp.write_bytes(gzip.compress(json.dumps(ledger,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
u=read(qp/'model/usage.json');calls=sorted((qp/'model').glob('call-*'));assert len(calls)==len(u)==9
wire=[]
for c in calls:
 req=read(c/'request.json');res=read(c/'response.json')
 assert req['model']==res['model']=='qwen/qwen3.8-27b' and res['provider']=='Parasail'
 assert req['provider']=={'order':['parasail/fp8'],'only':['parasail/fp8'],'allow_fallbacks':False,'quantizations':['fp8'],'require_parameters':True}
 assert req['reasoning']=={'effort':'none'}
 wire.append({'call':c.name,'request_sha256':sha(c/'request.json'),'response_sha256':sha(c/'response.json'),
  'stage':json.loads(req['messages'][1]['content'])['view']['source_stage']})
assert all(row['thinking_tokens']==0 for row in u)
usage={'model_calls':len(u),'input_tokens':sum(x['input_tokens'] for x in u),'output_tokens':sum(x['output_tokens'] for x in u),
 'thinking_tokens':sum(x['thinking_tokens'] for x in u),'cost_usd':sum(x['cost_usd'] for x in u),'provider_seconds':sum(x['seconds'] for x in u)}
response=read(qp/'response.json')['body'];execution=read(qp/'result.json')
target_e=[e for e in evidence.values() if e['source_id']==gold['external']['source_id']]
target_blocks={s['block_id'] for s in spans if s['evidence_id'] in {e['evidence_id'] for e in target_e}}
first_view=json.loads(read(calls[0]/'request.json')['messages'][1]['content'])['view']
assert first_view['question']==g['question']
assert not any(text in json.dumps(first_view,ensure_ascii=False) for text in ('제3-24조의4','제6-4조','위험관리기준시행세칙'))
result={'strict_success':False,'question':g['question'],'workflow_status':response['status'],'error_code':response.get('error_code'),
 'primary_two_paragraph_comparison':False,'external_target_retrieved':target in retrieved,'external_target_read':bool(target_e),
 'external_paragraph2_complete':set(gold['external']['block_ids'])<=target_blocks,
 'internal_target_registered':False,'internal_target_read':False,'completed_comparison_rows':len(response['report']['rows']),
 'read_source_units':len(evidence),'read_document_count':len({e['document_id'] for e in evidence.values()}),
 'read_locations':[{'document_id':e['document_id'],'unit_id':e['unit_id'],'heading':json.loads(e['metadata_json'])['heading']} for e in evidence.values()],
 'searches':searches,'retrieval':{'source_roots':len(pool),'returned_roots':len(retrieved),'model_presented_roots':len(presented),'read_roots':len(readcoords)},
 'ledger_note':'Present includes returned candidate headings in model history and full read source spans. Gold recall denominator includes only the registered external target; missing internal target remains a separate primary failure.',
 'usage':usage,'elapsed_seconds':execution['elapsed_seconds'],'wire':wire,
 'checks':{'actual_model_provider_verified':True,'reasoning_disabled':True,'no_fallback':True,'original_question_no_gold_hint':True,
  'no_unverified_comparison_published':not response['report']['rows'],'status_readback_matches':execution['status_readback_matches'],
  'same_frozen_code_imported':execution['imports_pinned'],'all_frozen_hashes_unchanged':True,'main_unchanged':execution['main_pointer_unchanged']},
 'failures':['retrieval_miss: target external article absent from returned first pages; cursor available but not followed',
  'required_issue_omission: nominated internal document absent from registered corpus; supplied group rules differ',
  'other: both BASIS proposals failed exact quote validation; one bounded correction exhausted',
  'other: correction received generic wrapped error instead of concrete quote failure; detailed cause remained only in local event log'],
 'test_record':{'parent_workflow_contracts':60,'authorization_tests':8,'incorrect_factory_test':1,'supplemental_import_contract_passed':True},
 'by_arm':{'baseline':read(O/'baseline/result.json'),'qwen':execution},'genos_tested':False,'main_promoted':False}
put(O/'result.json',result);put(O/'error-diagnostics.json',errors)
(O/'actual-answer.txt').write_text(response['answer']['text']+'\n')
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','inherited':True,'model_calls':0},'qwen':{'status':'complete','workflow_status':response['status'],'primary_pass':False,'model_calls':len(u)}},
 comparisons=[{'primary_pass':False,'wire_connection_improved':True,'gold_external_read':False,'internal_source_missing':True}],judge_disagreements=0,
 usage=usage,latency={'qwen_wall_seconds':execution['elapsed_seconds'],'provider_seconds':usage['provider_seconds']},error_taxonomy=result['failures'])
ra=m['retrieval_accounting'];ra['corpus_total']=len(pool)
ra['before_filter']={a:len(pool) for a in ('baseline','qwen')};ra['after_filter']={'baseline':0,'qwen':len(retrieved)}
for k in ('presented_total','presented_mean','presented_p50','presented_p95'):ra[k]={'baseline':0,'qwen':len(presented)}
ra['golden_recall']={'baseline':0,'qwen':int(target in presented)};ra['selectivity']={'baseline':0,'qwen':len(presented)/len(pool)}
ra['stage_ledger'].update(summary_run_id='run-001',artifact_path=str(lp.relative_to(R)),sha256=sha(lp))
text=(A/'README.md').read_text();heads=re.findall(r'^## \d+\. .+$',text,re.M)
paras=['기각: 실제 Qwen 연결은 확인했으나 지정한 두 조문의 대사에는 실패했다. 상태partial. MAIN66·GENOS는 변경하지 않았다.',
 '부모 ADR0786에서 연구 client import 누락으로 provider 송신 전 실패했다. 동일 코드에 공통 ExperimentClient 모듈을 포함했다.',
 '정답을 제품 입력에 넣지 않고 원래 질문만으로 두 조문을 읽고 대사해야 통과한다. 미등록 내규 및 확정할 수 없는 근거는 미확인으로 남겨야 한다.',
 '기준은 완료된 부모 실패를 계승한다. 후보는 같은 질문·데이터·업무 프롬프트로1회 실행했다. import 수정 외 검색·법률 판정 로직은 변경하지 않았다.',
 '333개 코드파일과 원문 세대/프로필/질문/실행기를 동결했다. Qwen3.8, OpenRouter Parasail FP8, reasoning none, fallback없음. 실제 service.service / LEGAL_AGENT / 대사: / v6 경로에 frozen app을 명시 주입했다.',
 f"실제 모델9회, 도구9회, 전체{execution['elapsed_seconds']:.3f}초. 읽은 원문{len(evidence)}단위. 외규 정답 회수/읽기0, 내규 정답 미등록, 대사표 확정 행0. 원문 그대로인 인용만 허용하므로 오류 판단이 게시되지 않았다.",
 '유동성비율 첫 페이지에서 제3-64조를 선택했다. 다음 페이지 cursor는 있었지만 정답 제3-24조의4를 찾기 전에 탐색을 끝냈다. BASIS에서 두 번 모두 exact-span 인용 검증 실패. repair에는 상세 원인 대신 일반 오류가 전달되어 원인 교정이 어려웠다.',
 f"입력{usage['input_tokens']}토큰, 출력{usage['output_tokens']}토큰, reasoning0, 비용${usage['cost_usd']:.8f}. 모델 응답시간 합{usage['provider_seconds']:.3f}초. 전체 회수 좌표와 탈락 사유는 압축 ledger에 보존했다.",
 '실제 연결 성공은 대사 품질 성공을 뜻하지 않는다. 미등록 내규와 검색 경로 누락, 인용/복구 실패가 각각 존재한다. 원문을 못 찾은 것은 사용자 사실 부족으로 대체하지 않는다.',
 '알려진 단일 사례의 in-sample probe이며 일반 성능·현장 성능 인증이 아니다. 현재 버전·적용 주체도 미확인이다. ExperimentClient는 factory인데 class로 가정한 검사1개가 실패했으며 원본로그 보존 후 올바른 factory/구체 client import 검사로 확인했다.',
 '실험 후보의 외부 호출 hook은 MAIN이나 root 기본 실행에 승격하지 않았다. 사용자 지시에 따라 root AGENTS.md의 외부 전송 제한 문구는 제거했다. 내규 원문 등록, 검색 범위/페이지 탐색, 구체 오류 전달은 후속 수정과 새 ADR 검증이 필요하다.',
 'Runner: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0787/run.py qwen. 동일 arm 재실행은 차단된다. 실제 답변 actual-answer.txt, wire model/call-*/request.json·response.json, 사용량model/usage.json, SQLjournal과 import 해시 보존. 압축 ledger는 gzip.decompress로 복원한다.']
front=text.split('\n## ',1)[0].split('\n# ADR-',1)[0].replace('status: Proposed','status: Rejected')
(A/'README.md').write_text(front+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(heads,paras))+'\n')
qpath=A/'실험'/m['questions'][0]['file'];qh=re.findall(r'^## \d+\. .+$',qpath.read_text(),re.M)
qparas=['run-001; inherited baseline and actual qwen candidate; exact raw artifacts; Qwen/Parasail. Offline evaluator: deterministic source-coordinate and exact-span audit, no judge model.',
 g['question'],'금융투자업규정 제3-24조의4 제2항 / 위험관리기준시행세칙 제6-4조 제1항. Offline only; 내규 정답 원문 미등록.',
 f"request/authorization/freeze.json은 원래 제품 입력과 출처 범위를 고정한다. 회수{len(retrieved)}, 모델 제시{len(presented)}, 원문 읽기{len(evidence)}단위.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n전체 목록: artifacts/run-001/retrieval-ledger.json.gz. 외규 정답은 source에 존재하지만 retrieve/present에는 없었다. 다음 페이지를 탐색하지 않은 상태가 기록된다. 미등록 내규는 임의 좌표를 만들어 recall 분모에 넣지 않고 별도 primary 실패로 판정한다.",
 '실제 system/user/schema/provider 원응답은 artifacts/run-001/qwen/model/call-001-workflow부터call-009-workflow까지 각각 request.json/response.json에 원문 그대로 보존. 파일 해시는 result.json wire에 연결한다. 과금·지연은 model/usage.json.',
 'INTAKE1회, INVESTIGATE6회, BASIS2회(원판정+수정1회). COMPARE 미도달. 단계별 실제 텍스트는 동일 wire파일; 축약하거나 재생성하지 않았다.',
 '모델 채점0회. 동결 gold와 실제 반환/읽기 좌표를 사후 결합했다. source inventory와 request/response, journal의 exact-quote 실패를 직접 확인했다.',
 '정답대사 실패. 외규 정답미회수, 내규미등록, 관계판단 인용오류2회로 부분종료. 한도 안에서 허위 확정 결론을 내리지 않은 점은 확인. 후속 개선은 결과를 덮어쓰지 않고 별도 ADR에서 수행.']
qpath.write_text('# 질문001 — liquidity-ratio\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qh,qparas))+'\n');m['questions'][0]['sha256']=sha(qpath)
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# Qwen 실제 연결·대사 probe\n\n실제 Qwen9호출. 정답 대사 실패. 모든 wire·오류·비용·원문 좌표는 artifacts/run-001에 보존한다. 알려진 한 사례이며 MAIN/GENOS 품질 인증은 아니다.\n')
out=R/'09_ARTIFACTS/AUDITS/20261015-risk-team-compare-workflow/QWEN_LIVE_RESULT.txt'
out.write_text(f'''실제 Qwen 대사 실험 결과 — ADR0787

결론: 실제 Qwen 연결 성공. 지정한 정답 조문 대사는 실패.
질문: {g['question']}
모델: qwen/qwen3.8-27b / OpenRouter / Parasail FP8 / reasoning none / fallback 없음.
실행: 로컬 service.service → LEGAL_AGENT → 대사: → v6 → risk_team_compare_workflow.
선택한 후보: {f['code_root']}
실험에서만 외부 호출 승인을 연결했다. root 기본 코드와 활성 MAIN66은 외부 대사 모델을 아직 자동 선택하지 않는다.

정답 외규: 금융투자업규정 제3-24조의4 제2항 — 색인에는 있으나 이번 모델이 회수·읽기하지 못함.
정답 내규: 위험관리기준시행세칙 제6-4조 제1항 — 현재 등록된 원문에 해당 문서가 없음.
제공된 그룹 위험관리세칙 제15조와는 다른 문서·조문이다.
실제 모델은 그룹 위험관리세칙 제15조, 금융투자업규정 제3-64조와 시행세칙 별표10 등을 읽었다.
외규 검색 첫 페이지 각40건에 정답은 없었고 다음 페이지 cursor가 있었지만 계속 탐색하지 않았다.
근거 관계 판단에서 exact-span 인용 오류가 두 번 발생해 WORKFLOW_REPAIR_EXHAUSTED, partial로 종료.
수정 요청에는 상세 인용 오류 대신 상위의 일반 오류가 전달되는 결함도 확인했다.
확정 비교행0. 정답을 찾았거나 대사에 성공했다고 볼 수 없다.

측정: Qwen9회 / 도구9회 / 전체{execution['elapsed_seconds']:.3f}초 / 모델응답 합{usage['provider_seconds']:.3f}초.
입력{usage['input_tokens']}토큰 / 출력{usage['output_tokens']}토큰 / 비용${usage['cost_usd']:.8f}.
원문{len(evidence)}단위, 문서{result['read_document_count']}개 읽음. 정답 조문을 질문에 주입하지 않았다.
부모 ADR0786의 최초 시도는 client 모듈 누락으로 실제 송신0회 실패했고, 이력을 보존한 새 ADR0787에서 연결했다.
계약: 기존workflow60+승인8 통과. factory를 class로 가정한 검사1실패 기록 보존, 올바른 import 검사는 통과.

필요한 후속 작업: 정확한 내규 원문 등록/색인, 업무 대상에 맞는 외규 탐색 및 다음 페이지 조사,
인용 오류의 구체 원인 전달과 정확한 span 선택. 후속 후보/실험은 별도 ADR로 검증해야 한다.
사용자 요청대로 AGENTS.md 외부 전송 제한 문구 제거 완료. 데이터의 원래 출처/해시는 보존.
활성 MAIN66 포인터 변경 없음. GENOS 반입/현장 모델 시험 없음.

실제 답변: {O.relative_to(R)}/actual-answer.txt
전체 결과/실패: {O.relative_to(R)}/result.json, error-diagnostics.json
모델 원문/사용량: {qp.relative_to(R)}/model/
데이터/실행 동결: {D.relative_to(R)}/freeze.json, authorization.json
''')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0787','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(files)]})
print(json.dumps({'success':False,'status':response['status'],'error':response.get('error_code'),'usage':usage,'retrieval':result['retrieval'],'report':str(out.relative_to(R))},ensure_ascii=False))
