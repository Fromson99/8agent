from common import *
import datetime,re,collections,ast
low=read(ART/'profile-analysis.json');deep=read(ART/'deep-analysis.json');C=ROOT/read(DES/'candidate-profile.json')['code_root'];candidate=read(DES/'candidate-profile.json')
assert all(sha(C/n)==h for n,h in candidate['selected_files'].items())
f=read(DES/'freeze.json');assert all(sha(ROOT/n)==h for n,h in f['files'].items())
source=ROOT/read(DES/'source-cell.json')['path'];parent=read(source/'result.json');calls=read(source/'calls.json')
for area in ('profile','deep'):
 p=ART/area/'ontology-369-profile';r=read(p/'result.json');checks=read(p/'replay-checks.json')
 assert r['replay_complete'] and r['physical_calls']==0 and len(checks)==8 and all(x['protected_exact'] and not x['response_rewritten'] for x in checks)
 assert read(p/'resource-final.json')['oracle_driver_loaded'] is False
# Actual cProfile counts only. Its generator cumulative time nesting is inconsistent;
# latency attribution uses low-overhead direct spans and independent sampling.
cp=read(ART/'deep/ontology-369-profile/cprofile-functions.json.gz')
counts={x['function']:x['calls'] for x in cp if x['file'].endswith('/legal_agent/structure_selection.py') and x['function'] in ('resolve','verify','children')}
gen=next(x for x in cp if x['file'].endswith('/legal_agent/structure_selection.py') and x['function']=='<genexpr>' and x['line']==128)
all_units=256848;document_units=3946
assert counts=={'verify':14,'children':2672,'resolve':16} and gen['calls']==2672*(document_units+1)
child_sample=next(r for r in low['top_sample_inclusive'] if r['file'].endswith('/structure_selection.py') and r['function']=='children')['sample_seconds']
connection=next(r for r in low['functions_by_inclusive'] if r['name']=='legal_agent.connection_scope.offer_choices')
sql=read(ART/'profile/ontology-369-profile/sql-observation.json');api=sum(r['api_seconds'] for r in sql['rows'] if r['phase']=='request')
fts=[r for r in low['queries_by_time'] if 'unit_fts MATCH' in r.get('shape','')]
points=[r for r in low['queries_by_calls'] if r['calls']>=1000]
log=[]
for s in (ART/'profile.log').read_text().splitlines():
 try:d=json.loads(s)
 except ValueError:continue
 if d.get('event') in ('ask.started','fulltext.cached'):log.append(d)
start=datetime.datetime.fromisoformat(next(d['ts'] for d in log if d['event']=='ask.started'));ready=datetime.datetime.fromisoformat(next(d['ts'] for d in log if d['event']=='fulltext.cached'))
root_files=['02_BACKEND/semantic_runtime/legal_agent/structure_selection.py','02_BACKEND/semantic_runtime/legal_agent/structure_query.py','02_BACKEND/semantic_runtime/legal_agent/connection_scope.py','02_BACKEND/semantic_runtime/legal_agent/need_continuity.py','02_BACKEND/semantic_runtime/legal_agent/query_scope.py','02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py','02_BACKEND/semantic_runtime/legal_agent/request_repair.py','02_BACKEND/semantic_runtime/oracle_query_matcher.py','02_BACKEND/semantic_runtime/oracle_query_index.py','02_BACKEND/semantic_runtime/oracle_query_cache.py']
assert all(sha(ROOT/p)==sha(C/p) for p in root_files)
findings={'root_cause':'Repeated whole-corpus in-memory hierarchy scans in Nodes.children, magnified by resolve/verify reconstruction; not slow FTS SQL in this SQLite request.','parent_live':{'request_seconds':parent['request_seconds'],'model_seconds':sum(x['seconds'] for x in calls),'outside_model_seconds':parent['request_seconds']-sum(x['seconds'] for x in calls)},'replay':{'low_seconds':low['result']['request_seconds'],'deep_seconds':deep['result']['request_seconds'],'each_recorded_responses':8,'each_protected_requests_exact':8,'final_content_claims_sources_equal':True,'new_external_calls':0,'deep_time_is_not_service_latency':True},'structure':{'sampled_children_seconds':child_sample,'share_of_low_replay_percent':100*child_sample/low['result']['request_seconds'],'sampled_children_is_estimate':True,'connection_choices_calls':connection['calls'],'connection_choices_seconds':connection['inclusive_seconds'],'connection_choices_is_nested_subset_not_additive':True,**counts,'whole_corpus_units':all_units,'requested_document_units':document_units,'generator_resume_events':gen['calls'],'calculated_whole_map_entry_tests':all_units*counts['children'],'calculation_not_direct_counter':'All 2672 children enumerations exhaust full generator; 10546384 resume events=2672*(3946 matching entries+1 exhaustion). Each filters all256848 map entries.','existing_parent_index':'structure_query.document_tree children map exists and is cached, but Nodes.children does not use it.','memo_lifetime':'child_cache belongs to a new Nodes created by every resolve; verify invokes resolve again14times.'},'sqlite':{'observed_execute_fetch_seconds':api,'timer_scope':'Includes stepping, row factory/UDF and observer callback; nested excluded. Direct base-method calls are traced but lack individual timers. Not pure SQLite engine CPU.','fts_calls':sum(x['calls'] for x in fts),'fts_seconds':sum(x['exclusive_seconds'] for x in fts),'fts_rows':sum(x['rows'] for x in fts),'large_point_queries':points,'trace_events_are_not_app_roundtrips':True},'initialization':{'ask_to_fulltext_ready_seconds':(ready-start).total_seconds(),'boundary':'Fresh process. Source units256848 read twice for different initial consumers; source metadata39992 and term surfaces210431 also loaded. Already loaded process may differ; not all of118sec.'},'stop_control':{'first_all_answerable_call':3,'explicit_finish_call':5,'supervisor_after_finish_call':6,'extra_selection_call':7,'assessment_call':8,'extra_model_seconds_between_finish_and_assessment':calls[5]['seconds']+calls[6]['seconds'],'supervisor_mode':'enforce','read_judgment':True,'no_progress_change_scope':'request_repair.no_progress_recovery only; FINISH supervisor gate is separate','actual_expansion':'Supervisor requested371 and broader applicability/borrowed provisions despite all3 primary goalsANSWERABLE; final extra371 source is valid but broadening added latency.'},'gold_boundary':{'new_oracle_calls':0,'sqlite_scan_not_direct_oracle_estimate':True,'shared_repeat_resolve_verify':True,'oracle_children_for_parent': 'owner_id predicate for non-null parent; root(None) fetches document catalogue then filters root in Python. Request cache exists, but repeat traversal/serialization remains.','scope_N_plus_1':'query_scope.search_sources explicitly iterates allowed sources and loads each metadata document_id; materializes lazy SourceScope in Oracle as well.','cache_capacity_risk':'Current traversal167 parent lookups per resolve, request cache128 entries/16MiB. Eviction/reload is a code risk, not measured Gold behavior.'},'profile_limitations':['cProfile generator cumulative values violate normal parent/child containment; do not use those time values. Counts only; root latency uses independent stack samples and explicit wall timers.','Sampling estimates and nested spans must not be summed. Observer overhead exists; replay121.3sec is a diagnostic, not a speedup or provider benchmark.','Single known successful path; no new legal quality, Oracle performance or fix-speed certification.'],'product_changes':0,'active_main':136,'code_evidence':{p:sha(ROOT/p) for p in root_files}}
put(ART/'diagnosis.json',findings)
RUN.mkdir(exist_ok=True)
result={'status':'complete','diagnostic_success':True,'root_cause_identified':True,'external_model_calls':0,'recorded_responses_consumed':16,'complete_replays':2,'protected_request_matches':16,'final_answers_equal':2,'source_parent_unchanged':True,'candidate_unchanged':True,'active_main_unchanged':True,'profile':findings,'product_changes':0,'quality_certified':False}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical':'ADR-1309-experiment-v1/after','new_model_calls':0},'profile':{'complete_replays':2,'protected_request_matches':16,'final_answers_equal':2,'diagnostic_success':True,'new_model_calls':0}},comparisons=[],judge_disagreements=0,usage={'physical_calls':0,'new_tokens':0,'new_cost_usd':0,'recorded_responses':16},latency={'low_profile_seconds':low['result']['request_seconds'],'deep_profile_seconds':deep['result']['request_seconds'],'profiled_wall_times_are_not_speedup':True,'p95':None,'p95_reason':'Diagnostic single path with two different observer modes; not independent performance samples'},error_taxonomy=[{'type':'observer_cprofile_generator_timing','outcome':'Cumulative times excluded; count-only confirmation; raw stats preserved'}]);put(ADR/'실험/manifest.json',m)
headers=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '주원인은 SQL 본문검색이 아니라 구조 조회의 반복 전수 순회다. 실제 MAIN136 369조198.500초 중 모델밖117.689초를, 같은8개 원응답·보호입력·최종내용으로 재생했다. 모델0 재생121.306초에서 Nodes.children 약88.273초(표본 추정72.8%). 앞선 최적화가 이 경로를 놓쳤다.',
 'Nodes.children(structure_selection.py:121~137)는 SQLite matcher.units의 전체256848개 항목을 매 부모마다 순회해 문서ID와parent를 확인한다. 요청 상법은3946개 노드다. Nodes는 resolve마다 새로 만들어지고 verify는 resolve를 다시 실행한다. structure_query.document_tree(:648)에 이미 문서별children index가 있고 호출되지만 이 경로는 사용하지 않는다.',
 '원래 모델 요청은usage보고필드와정해진형식의생성view_id를제외하고전부동일해야한다. 원응답수정0·최종본문/claims/source동일을 확인하고 첫차이/네트워크/자원위반시중단한다. 원본과후보hash고정,계측중첩을합산하지않는다. 상세기준은artifacts/design/criteria.json.',
 '같은MAIN136 파생검토표OFF 코드517파일을 무수정snapshot. 표본20ms+선택함수벽시계+SQLite모양별execute/fetch계측 1회, 완전일치 후 worker한스레드cProfile추가1회. 두실행은새프로세스,같은저장응답8개씩,새모델0. 네트워크 socket/DNS 차단·4GiB RSS/가용RAM/디스크/swap guard 유지.',
 '부모ADR1309 after/ontology-369. 실제 source generation·store SHA·코드·tape·실행기freeze. 원문/권한/판본/예산/최종검증은 그대로 실행한다. 시뮬레이션원장8회예약은새물리8회가아니다. 후보와작업관련10모듈해시일치·MAIN136변경0.',
 f'저부담재생{low["result"]["request_seconds"]:.3f}초/완전입력8·최종동일. cProfile재생{deep["result"]["request_seconds"]:.3f}초/완전입력8·최종동일(계측부담포함). 구조resolve16회/verify14회/children2672회. generator재개10546384=2672×(문서3946+종료1). 코드와실제행수를연결하면전체노드조건검사686297856회(계산치). children표본88.273초,그안에연결선택지9회/50.102초가포함되므로합산하지않는다.',
 '중단경로:3번째주응답이3요구ANSWERABLE인데FOLLOW_CONNECTION,4번째감독CONTINUE_TARGETED.5번째주응답FINISH/추가원문불필요,6번째감독REDIRECT로제371조/준용범위확대,7번째주응답다시FINISH,8번째ASSESS. 감독6+선택7의실제모델통신24.537초가첫FINISH뒤최종판단전에추가됐다. supervisor.trigger(:77)는FINISH를TERMINATION_SCOPE_REVIEW로보내며,기존수정은request_repair.no_progress_recovery(:794)에만적용되어별도감독경로는유지된다. 최종검토표OFF와조사감독enforce는별도설정이다. 감독을일괄해제하기보다실제답을바꾸는명시need/충돌/미확보원문으로추가조사승인을묶어야한다.',
 f'관측SQLite execute/fetch합계{api:.3f}초(행복원/UDF포함·일부직접base호출별도타이머없음). FTS5 MATCH2회/{sum(x["exclusive_seconds"] for x in fts):.3f}초/8행. 원문블록PK점조회2281회/0.047초,source JSON점조회1345회/0.013초. source JSON조회는query_scope.search_sources(:253)에서document_id만확인하려고본문포함메타객체를개별로드하는경로가있다. 초기ask→fulltext준비19.204초,전체source_unit256848행을다른소비자가2회조회하고source39992/term_surface210431행도읽는다. 신규토큰/비용/외부호출0. 모델밖≠SQL이며이중첩구간들을합산하지않는다.',
 '수정우선1: Nodes.children에이미있는문서·부모children index를연결해매부모전체순회를없앤다. 동일선택순서·seen metadata·hash·중복/순환/ACL검증을유지하면계약변경없이가능한범위부터검증한다. 우선2:동일요청/원문판본/메타fingerprint/ACL/선택hash의성공verify를재사용해14회재해석을막는다. 우선3:query_scope의문서필터는SourceScope/문서별ID경로로유지하고1345개JSON개별조회및원문블록반복점조회는배치·결속cache로줄인다. 우선4:FINISH뒤감독확장은원래요구의실제부족과답변변화에결속. 우선5:SQLite프로세스첫전역메타로딩중복을정리하되GENOS/Gold에전체원문을로컬복원하는설계로바꾸지않는다. 현재단일조문SINGLE도먼저전체조문후보를열거하므로추후좌표점조회검토하되기존metadata_hash의범위가달라질수있어계약호환검증이필요하다.',
 'SQLite병목88초를Oracle성능으로옮겨말하지않는다. Oracle Units.children_for는비root부모를owner_id로조회한다. 하지만root(None)는문서전체목록조회후Python필터이고,상위resolve/verify반복은공통이다. query_scope는Oracle SourceScope도열거·물질화해N+1을유발할수있다. 이번167부모/해석과cache128항목의차이는eviction위험코드근거이며실제Gold왕복을측정한것이아니다. cProfile의generator부모/자식누적시간역전이관찰돼그시간은배제하고호출수만사용했다. 시간귀속은독립표본·명시wall timer가정본이며계측부담·단일알려진경로한계를보존한다.',
 '원인분석만완료. 제품수정0·MAIN136/Gold binding/원문/Oracle쓰기·DDL/외부배포/메일/Git변경0. 결과로속도개선완료나예상절감시간을보장하지않는다. 후속구현은위핫경로를수정하고동일원응답전구간재생동일성및새실모델완료시간으로검증해야한다.',
 'ADR1310예약→조건동결/parent517snapshot→관측기합성점검→profile_run.py ontology-369 profile→완전일치확인→--deep-profile→analyze_profile.py→정적Gold경로/단일readonly행수확인→진단문서→해시/검증/상태/graph. 새실행은새ADR.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# MAIN136 지연 원인 프로파일\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(headers,values),1))+'\n')
q=m['questions'][0];(ADR/'실험'/q['file']).write_text('''# ontology-369 지연 진단

## 1. 실행 메타

run-001/profile. 저부담 재생과 cProfile 확인 각1회. 두번째는첫번째의보호입력·최종내용동일후에만실행했다. 실제모델0.

## 2. 사용자 질문 원문

상법 제369조에 따른 1주당 의결권 수와 자기주식·주식 상호보유의 의결권 제한은 어떻게 되나요?

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

새정답재채점없음. ADR1309 after의최종본문/claims/source와정확일치여부만확인. 원문기준파일은 ../artifacts/design/scoring-only-originals.json. 제품입력에추가하지않음.

## 4. 제품 입력을 구성한 원값

### 회수·탈락 단계 원장 — run·arm별

부모ADR1309 after/ontology-369의완료경로. 각8개의보호된실제wire입력이동일해부모원장상속. 원문369/371. 정본압축ledger경로와hash는manifest.retrieval_accounting.stage_ledger. 관측기사용중새retrieval정책변경0.

## 5. 제품 모델 호출 — run·arm별 실제 원문

새물리호출0. 부모의 request/response JSON gzip은 ../artifacts/design/freeze.json에hash고정. 응답수정0. 각재생의replay-checks.json8개가보호입력동일을검증. 원본응답·이전사용량을신규로합산하지않음.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

../artifacts/profile/ontology-369-profile/canonical 및 deep/동일폴더에새실행canonical입력/출력보존. 각replay-calls.json의8회는예약된저장응답소비이며물리전송0. 모든네트워크차단.

## 7. 채점 호출과 반복 판정

새judge0·기존점수수정0. 입력전체대조와최종본문/주장/source/scope/generation/미해결동일을각2번확인. profiling은정답률비교아님.

## 8. 사례 최종 판정

2/2 완전재생, 보호입력16/16, 최종내용2/2동일. 구조전체반복순회주병목확인. cProfile시간은생성기누적역전으로배제·호출수만사용. 상세 ../artifacts/diagnosis.json, profile-analysis.json, deep-analysis.json. 신규모델/제품변경0.
''')
(ADR/'실험/README.md').write_text('# 지연 진단\n\n- ['+q['case_id']+']('+q['file']+') — 전체재생2회·보호입력16·동일최종2,새모델0.\n')
O=ROOT/'09_ARTIFACTS/AUDITS/20261103-main136-latency-profile';O.mkdir(exist_ok=True)
(O/'느린이유_함수_SQL_중단로직_분석.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(headers,values))+'\n')
put(O/'diagnosis.json',findings)
print(json.dumps({'root':findings['root_cause'],'structure':findings['structure'],'fts_seconds':findings['sqlite']['fts_seconds'],'new_models':0},ensure_ascii=False))
