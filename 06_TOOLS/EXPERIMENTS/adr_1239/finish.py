from pathlib import Path
import json,hashlib,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1239-main124-gold-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369';U=R/'09_ARTIFACTS/AUDITS/20261030-main124-gold-live';U.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def mutable(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
r=read(P/'result.json');a=read(P/'audit.json');e=read(O/'ontology-e2e.json');post=read(P/'post-audit.json');sql=read(P/'sql-audit.json');f=read(D/'freeze.json');integrity={p:sha(R/p)==h for p,h in f['files'].items()};assert all(integrity.values());write_summary(O/'post-run-integrity.json',{'checked':len(integrity),'unchanged':all(integrity.values()),'files':integrity})
case2={'case_id':'cm-009','status':'NOT_RUN','reason':'First gold-369 failed at RECALL; frozen sequential stop rule','model_calls':0,'embedding_calls':0};write_summary(O/'cm-009-not-run.json',case2)
functions={}
for release in ('schema-factor-20261029-r1','judgment-gold-20261030-r1'):
 p=R/'08_DEPLOYMENT/RELEASES'/release/'code/02_BACKEND/semantic_runtime/legal_agent/law_candidates.py';s=p.read_text();start=s.index('def fulltext_scope_keys');end=s.index('\ndef ',start+5);functions[release]=hashlib.sha256(s[start:end].encode()).hexdigest()
assert len(set(functions.values()))==1
failure={'stage':'RECALL','classification':'IMPLEMENTATION_FAILURE','error_type':r['error_type'],'error':r['error'],'location':'02_BACKEND/semantic_runtime/legal_agent/law_candidates.py:359','callee':'Oracle oracle_query_fulltext.UnitIndex.connect() returns self; no SQLite execute method','trigger':'Actual model selected FULLTEXT + NAMED_SCOPE for article369; fulltext_scope_keys directly executes SQLite JSON SQL on Oracle unit index','same_function_MAIN120_MAIN124':functions,'fix_needed':'Introduce a typed scope-to-unit-key port implemented for SQLite and Oracle and call it from fulltext_scope_keys; preserve subtree/exclusion/ACL/release/hash semantics. Avoid changing model decision or forcing another search mode to conceal the failure.','implemented_in_this_experiment':False};write_summary(O/'failure-diagnosis.json',failure)
summary={'status':'REJECTED_MAIN124_GOLD_LIVE_RECALL_PORT_MISSING','actual':{k:r[k] for k in ('seconds','model_calls','unknown','sql_calls','error','error_type','engine_code_unchanged')},'case_status':'FAILED','final_answer_chars':0,'http_response_returned':False,'physical_budget_matches':a['physical_budget_matches'],'reported_cost_usd':a['reported_cost_usd'],'provider_switches':post['provider_switches'],'source_evidence_checks':0,'source_or_ontology_correctness_checked':False,'ontology_acquired':False,'actual_embedding_calls':0,'actual_vector_queries':0,'supervisor_unknown_stop_exercised':False,'next_case':case2,'integrity_files_unchanged':len(integrity),'model_input_wire_matches':a['wire_request_matches'],'sql_boundary_seconds':sql['SQL_boundary_seconds'],'code_changed':False,'database_content_changes':0,'main_generation':124,'main_promoted':False,'quality_certified':False,'evidence':{'result':str((P/'result.json').relative_to(R)),'audit':str((P/'audit.json').relative_to(R)),'post_audit':str((P/'post-audit.json').relative_to(R)),'SQL':str((P/'sql-audit.json').relative_to(R)),'diagnosis':str((O/'failure-diagnosis.json').relative_to(R))}}
write_summary(O/'result.json',summary);write_summary(U/'result.json',summary)
report=f'''MAIN124·Gold 실제 실험 결과 — 2026-10-30 / ADR1239

결론: 실제 전체 RAG 미통과. Gold의 지정 조문 전체 읽기 경로에 Oracle 포트 누락이 확인됐다.
현재 MAIN124 / judgment-gold-20261030-r1과 Gold ON/DB·R18(VCTR_SCTN_ID/DTLS_HASH_VALU)을 그대로 실행했다.
제품 코드·MAIN 선택·DB 내용·GENOS·Git·메일 변경0. 이번 실험에서 결함 수정은 하지 않았다.

질문: {read(D/'cases.json')[0]['request']['json']['question']}
실제 모델은 FULLTEXT + NAMED_SCOPE(상법369조)를 선택했다.
RECALL → vector_navigation.discover → query_scope.fulltext → law_candidates.fulltext_scope_keys:359
→ Oracle UnitIndex에 SQLite db.execute를 호출해 AttributeError: {r['error']}
Oracle UnitIndex.connect()는 자신을 반환하며 execute 메서드를 제공하지 않는다.
실제 journal은 FAILED/END, 분류 IMPLEMENTATION_FAILURE. 모델 판단 오류나 공백·UNKNOWN으로 분류하지 않는다.
TestClient가 서버 예외를 다시 던졌으므로 실제 API HTTP 상태를 500/422로 단정하지 않는다. 답변0, 최종ASSESS0.
fulltext_scope_keys의 MAIN120/MAIN124 함수 해시가 같다. 이번 통합에서 수정한5파일의 새 회귀라는 근거는 없다.
이전 부분 검사와 다른 실제 검색 선택 경로에서 기존 호환 누락이 드러났다.

계측
- 실행 {r['seconds']:.3f}초: 모델 통신 {a['model_seconds']:.3f}초, 나머지 {a['other_seconds']:.3f}초.
  나머지를 순수SQL시간이라고 부르지 않는다. 별도로 계측한 oracle.sql 시작→완료 경계 합계 {sql['SQL_boundary_seconds']:.3f}초.
  시작/종료 경계에는 통신·Oracle 처리·반환 처리가 포함되며 Oracle CPU만 측정한 값은 아니다.
- 실제 모델 물리2회: Parasail429 1회 → 정책상 NearAI 전환1회 → 정상 stop/JSON 1회.
  UNKNOWN0·자동재실행0·출력토큰상한없음·보고비용 ${a['reported_cost_usd']:.8f}.
  보고 토큰 입력{a['input_tokens']:,}/출력{a['output_tokens']:,}. 사용량 미보고429 비용은0이라고 단정하지 않는다.
- 실제 추적SQL {r['sql_calls']:,}회 + 매핑 메타데이터SELECT1 = {sql['all_observed_sql_including_mapping_preflight']:,}회.
  별도 사전접속 검사는 추적4 + 메타1 =5회, 위 실제실행 SQL과 분리한다.
  2개 주요 조회형태가166회/166.490초,115회/115.838초 반복됐다. WHERE문서·owner/페이지 조건의 게시자료 조회다.
  실행계획/인덱스 원인 미확인, DB지연 개선은 이번에 하지 않았다.
- 물리호출 예산2 일치, 실제전송2개 canonical→wire 일치, 출력상한0, 원문corpus SQLite우회0.
- 확보 evidence0·최종 입력0: 원문/권한 불일치가 없다는 공집합 결과를 원문대조 통과로 해석하지 않는다.
- 온톨로지 설정 ON/DB 확인·실제입력 전달0, 새임베딩0·벡터검색0.
- 감독 단계에 도달하지 않아 UNKNOWN 즉시중단 수정의 실모델 실효는 이번에 미검증.
- swap증가 {a['resource']['max_host_swap_growth_MiB']:.3f}MiB, 가용RAM최소 {a['resource']['minimum_available_GiB']:.3f}GiB,
  프로세스RSS최대 {a['resource']['max_rss_GiB']:.3f}GiB, 자원중단없음.
- 동결 {len(integrity)}개 파일(선택489/작업489/연결기/설정/데이터 등) 전후 동일.

범위와 다음 수정 지점
사전 기준대로 첫 실패에서 종료했다. CM009는 NOT_RUN(미실행), 실패한 두 번째 표본으로 세지 않는다.
현재 통합본의 최종답변·온톨로지·벡터 전체 동작이 완료됐다고 볼 수 없다.
1. SQLite 직접SQL 대신 Oracle에도 구현된 범위→unit key 조회 포트를 연결하고, 하위범위·제외·ACL·판본/hash 보존을 검사해야 한다.
2. 반복 게시자료 조회의 실제 실행계획과 반환량을 확인해야 한다. 약287초 조회 경계가 관찰됐지만 구조개선효과는 미측정이다.
3. 수정 후보는 새 ADR에서 동결·동일 경로 검사 후 별도 실제 재검증해야 한다. 실패한1239를 덮어쓰거나 검색 방식을 강제해 통과로 바꾸지 않는다.

실험 준비 기록
전송 실패분류/1회429전환7검사, 실제사전접속 MAIN124489/13테이블60컬럼 ON/DB 통과.
ADR validate 최초 잘못된 --adr-dir 옵션과 SQL 로그집계 최초 hash필드 가정오류를 보존하고 정정했다.
두 오류는 외부모델 호출이나 실행 중 제품에 영향을 주지 않았다.

원시근거
{O.relative_to(R)}/live/gold-369/raw/ 및 canonical/ : 실제 요청/응답·조립 입력 gzip과 복원 해시.
{P.relative_to(R)}/error.txt : 원래 예외.
{P.relative_to(R)}/sql-audit.json : 실제조회시간/횟수.
{O.relative_to(R)}/failure-diagnosis.json : 코드경계 및 MAIN120/124 함수 대조.
{O.relative_to(R)}/cm-009-not-run.json : 미실행 근거.
법률 품질 인증·성능 개선 주장 없음.
'''
(U/'실제실험_결과와_남은결함.txt').write_text(report)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True,'source':'ADR1238 selected MAIN124 component validation'},'live':summary},comparisons=[],usage={'physical_calls':2,'provider_switches':1,'unknown':0,'reported_cost_usd':a['reported_cost_usd']},latency={'seconds':r['seconds'],'SQL_boundary_seconds':sql['SQL_boundary_seconds'],'population_claim':False},error_taxonomy=[{'category':'IMPLEMENTATION_FAILURE','stage':'RECALL','code':'AttributeError','detail':'Oracle UnitIndex missing SQLite execute port'}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,case in zip(m['questions'],read(D/'cases.json')):
 run=q['case_id']=='gold-369';vals=['run-001/live; immutable rev001; actual MAIN124489',case['request']['json']['question'],'기준답변 제품 미제공·채점모델0.','[동결입력](../artifacts/design/cases.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\nRECALL 예외로 evidence/최종입력0. cm009는 첫실패 후 미실행.','[실제 raw/canonical](../artifacts/run-001/live/gold-369/) 모든본문 무손실 보존.' if run else '미실행. 실제모델0.', 'request-entry Parasail429→NearAI stop2물리. 추가모델0.' if run else '미실행.', '사후 읽기전용 wire/예산/SQL·실패경로 검사; 법률채점 미도달.', summary['status'] if run else 'NOT_RUN — frozen first-failure stop rule'];p=A/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
mutable(A/'실험/manifest.json',m);(A/'실험/README.md').write_text('# 실험 인덱스\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+'): '+('REJECTED' if q['case_id']=='gold-369' else 'NOT_RUN') for q in m['questions'])+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령'];vals=['Rejected: MAIN124 실제 Gold 전체RAG 미통과. 첫실패에서종료·MAIN124유지.','MAIN124 통합·구성요소 검사 후 실제 검색선택 전체 경로 검증.', '[criteria.json](artifacts/design/criteria.json) 호출전동결; 첫질문전체통과후에만009.', '선택MAIN124489·Gold ON/DB·최신R18·정확질문, 두번째조건부미실행.', '1062파일 해시고정·Qwen3.8·Parasail우선/확인429만NearAI1전환·정답주입0.', report, 'Oracle UnitIndex에SQLite 직접SQL. MAIN120/124동일함수. 실패원본보존.',f"{r['seconds']:.3f}초·물리2·SQL1503+메타1·보고${a['reported_cost_usd']:.8f}", '모델유효응답 이후 RECALL 구현실패. 공백/UNKNOWN 실패로 해석하지 않는다.', '원문·온톨로지·벡터·감독·최종미도달; 함수동일은전체코드인과A/B아님.', '실험만 수행·수정/승격/DB변경0. 이전223계약과 이번전체실패를별도기록.', 'audit.py gold-369, post_audit.py gold-369, sql_audit.py gold-369는사후검사구조. 완료산출물중복생성/실모델재실행금지; 다음수정은새ADR.']
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');(A/'README.md').write_text('---'+front+'---\n\n# ADR-1239: MAIN124 Gold 실제 재검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=A/'artifacts/manifest.json';v=read(p);v['files']=[{'path':str(x.relative_to(R)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen design, real run or read-only audit evidence','contains_raw_prompts_and_outputs':'/raw/' in str(x) or '/canonical/' in str(x)} for x in (A/'artifacts').rglob('*') if x.is_file() and x!=p];v.pop('notes',None);mutable(p,v)
print(summary['status']);print(U/'실제실험_결과와_남은결함.txt')
