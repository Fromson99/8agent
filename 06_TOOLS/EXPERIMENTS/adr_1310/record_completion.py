from common import *
import datetime,shutil
report=ROOT/'09_ARTIFACTS/AUDITS/20261103-main136-latency-profile'
p=report/'graph-after.json'
if p.read_text().startswith('wrote '):p.rename(report/'graph-command-output.txt')
shutil.copy2(ROOT/'04_EXPERIMENTS/ADR/EXPERIMENT_GRAPH.json',p)
before=read(ROOT/'09_ARTIFACTS/AUDITS/20261103-gold-query-optimization/final/graph-before.json')['errors']
after=read(p)['validation_errors'];added=sorted(set(after)-set(before));assert not added and len(after)==16
(report/'graph-check.json').write_text(json.dumps({'existing_errors':len(before),'current_errors':len(after),'new_errors':added,'global_pass':False,'adr1310_final_pass':True},indent=2)+'\n')
p=ROOT/'AGENTS.md';s=p.read_text();marker='MAIN136_PROFILE_1310_20261103'
block='''<!-- MAIN136_PROFILE_1310_20261103 -->
**2026-11-03 — MAIN136 지연 주원인 확인, 수정은 미실행:** [함수·SQL·중단 분석 TXT](09_ARTIFACTS/AUDITS/20261103-main136-latency-profile/느린이유_함수_SQL_중단로직_분석.txt) · [ADR1310](04_EXPERIMENTS/ADR/ADR-1310-main136-latency-profile/README.md). ADR1309 후보369 원응답8개를 두 번 재생, **보호입력16/16·최종답변2/2 동일·새모델/Oracle0**. 첫 재생121.306초 중 **Nodes.children 표본88.273초(72.8%)**, resolve16/verify14/children2672회. SQLite에서 부모마다 전체256848노드 순회, 코드·횟수로 **6.86억 조건검사 계산**; 이미 있는 document_tree.children 색인 미사용. FTS5 MATCH2회/0.374초, 관측SQLite API5.516초(순수DB 전체시간 아님). source JSON1345/원문블록2281 점조회·첫준비19.204초 잔존. **FINISH 뒤 감독REDIRECT→추가선택 모델24.537초**, 기존 no_progress 복구 제한과 별도 경로. Gold 비root는owner_id 조건사용: 공통재검증/root목록/SourceScope 열거 위험만 확인, SQLite88초를Oracle로 일반화 금지. 상세cProfile163.372초는 계측부담 포함·누적시간 이상으로 횟수만 사용. runtime2 전파일해시 보존·최종ADR통과/graph기존16·새0, 최초 artifact manifest 형식오류는 완료전 정정. **제품/MAIN136/Gold/원문/DDL/배포 변경0·속도개선 미측정**. 우선 기존children색인 연결→요청내 검증 재사용→개별조회 축소→FINISH 감독조건 제한.
<!-- /MAIN136_PROFILE_1310_20261103 -->

'''
assert marker not in s;s=s.replace('# 8-AGENT 작업 가이드\n\n','# 8-AGENT 작업 가이드\n\n'+block,1);p.write_text(s)
p=ROOT/'04_EXPERIMENTS/ADR/README.md';s=p.read_text();p.write_text(s.replace('# ADR workspace\n\n','# ADR workspace\n\n- [ADR1310 MAIN136 함수·SQL·중단 지연 원인](ADR-1310-main136-latency-profile/README.md) — 모델0 재생2회·보호입력16/16/최종동일. 구조 전수순회 약88.3초/재생121.3초, FTS2회0.374초·FINISH 감독 추가모델24.537초. 제품/MAIN 변경0.\n\n',1))
skill=Path('/mnt/c/Users/Jin/.codex/skills/legal-rag-db-optimization/references')
p=skill/'incidents.md'
with p.open('a') as f:f.write('''\n\n## 2026-11-03 ADR1310 MAIN136 지연 원인 — 구조 전수순회와 FINISH 감독\n\n- ADR1309 after369의 동일517파일·저장8응답을 두 번 오프라인 재생. 보호입력16/16, 최종본문/claims/원문/범위 동일2/2. 새모델/Oracle0·제품/MAIN136 변경0. 첫 재생121.306초, 상세cProfile163.372초는 서로 다른 계측 부담이므로 속도 비교 불가.\n- SQLite structure_selection.Nodes.children(:121)는 매 부모마다 전체 matcher.units 256848항목을 순회. 해당문서3946노드. resolve16/verify14/children2672, generator재개10546384=2672×3947 → 686297856회 전체항목 조건검사는 코드·횟수·행수 계산치. 독립스택표본 children88.273초/72.8%. connection_scope.offer_choices9회50.102초와 중첩되므로 합산 금지.\n- structure_query.document_tree(:648)에 이미 문서별 children index가 있으나 느린 경로가 미사용. Nodes가 resolve마다 새로 만들어져 child_cache 폐기. connection_scope/need_continuity/query_scope가 검증 재해석을 증폭. 기존색인 연결 후 요청/판본/ACL/선택hash 결속 성공검증 재사용이 우선이며 검증 삭제가 아님.\n- 관측SQLite API5.516초(원문3.100/journal2.416), FTS5 MATCH2회0.374초8행. block PK2281회0.047초/source JSON1345회0.013초. query_scope.search_sources는 document_id 확인에 개별JSON 로드; SQL모양별 caller는 최초관측만이며 전횟수 단일caller 귀속 금지. 초기 준비19.204초·source_unit 전체256848 두 번 및 source39992/term_surface210431 로드, warm에도 매번 발생한다고 주장 금지.\n- 실제3번 세목표 ANSWERABLE,5번FINISH,6번감독REDIRECT로371/준용확대,7번FINISH,8번ASSESS. 6+7 실제 모델통신24.537초. investigation_supervisor FINISH gate는 앞선 request_repair.no_progress_recovery 수정과 별개. supervisor enforce/read_judgment가 실제모드이며 answer_progress_control 자동종료가 켜졌다고 혼동 금지. 최종검토표OFF도 감독OFF 아님.\n- Gold children_for는 비root owner_id 조건, root는 문서목록 뒤Python필터. 상위resolve/verify 반복·SourceScope열거 공통. 167부모/해석 대 캐시128항목/16MiB는 퇴출위험이지 측정Gold왕복 아님. SQLite88초를Gold예상으로 쓰지 않는다.\n- worker한스레드 cProfile에서도 generator cumulative 포함관계 이상이 있어 해당시간 폐기·횟수만 사용. 시간근거는 독립표본/명시wall timer. 후보/입력동결·두runtime 전파일SHA복원 보존. artifact manifest schema/adr_id 형식오류는 완료전 정정, 원실행 변경0. ADR최종통과/graph기존16·새0.\n- 근거: ADR1310/artifacts/{diagnosis.json,profile-analysis.json,deep-analysis.json,run-001/result.json}; 09_ARTIFACTS/AUDITS/20261103-main136-latency-profile/느린이유_함수_SQL_중단로직_분석.txt. 후속 구현/새속도검증은 미실행.\n''')
p=skill/'source-map.json';d=read(p)
paths=[ART/'diagnosis.json',ART/'profile-analysis.json',ART/'deep-analysis.json',RUN/'result.json',ADR/'README.md',report/'느린이유_함수_SQL_중단로직_분석.txt',report/'graph-check.json']
d['main136_latency_profile_1310']={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_main':136,'new_model_calls':0,'new_oracle_calls':0,'product_changed':False,'diagnostic_replays':2,'protected_request_matches':16,'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in paths}}
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print('Recorded diagnosis and memory; final validation PASS, existing graph errors16/new0.')
