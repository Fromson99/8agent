from common import *
s=read(ART/'diagnosis.json')
sections=[
('결정 요약', '''가장 큰 병목은 문서 구조 조회에서 일어나는 Python 메모리 전수 순회다. 앞선 SQL 최적화가 이 경로를 놓쳤다.

실제 MAIN136 상법 제369조 시험은 전체 198.500초, 모델 통신 80.810초, 모델 밖 처리 117.689초였다. 이번에는 그때의 모델 응답 8개를 그대로 재생해 서버 처리를 추적했다. 재생 121.306초 중 Nodes.children이 실행 중인 것으로 관측된 시간이 약 88.273초(표본 추정 72.8%)였다. FTS5 MATCH 검색은 2회, 0.374초였다.

SQL 반복 조회와 종료 후 추가 조사도 남아 있다. 다만 이번 SQLite 사례의 최대 병목을 본문 검색 SQL로 설명할 수는 없다.'''),
('문제와 변경 전 구조', '''structure_selection.py:121의 Nodes.children은 SQLite에서 자식 하나의 목록을 찾을 때마다 matcher.units 전체 256,848개 항목을 순회한다. 먼저 문서 ID로 걸러낸 뒤 parent를 비교한다. 해당 상법 문서는 3,946개 노드인데도 매 부모마다 전체 문서들의 노드를 다시 본다.

resolve마다 Nodes가 새로 만들어져 child_cache도 버려진다. verify는 resolve를 다시 실행한다. 연결 선택지, 필요 원문 연결, 검색 범위 결속에서 같은 선택을 반복 검증하면서 이 비용이 증폭된다.

structure_query.py:648의 document_tree에는 이미 문서별·부모별 children 색인이 준비되어 있다. 느린 Nodes.children 경로가 이 색인을 사용하지 않는다. 현재 SINGLE 조문 선택도 먼저 전체 조문 후보를 열거한다.'''),
('가설과 사전 판정 기준', '''원래 요청과 재생 요청의 메시지·스키마·값을 비교한다. 전송기가 넣은 usage 보고 필드와 사전 정의된 형식의 생성 view_id만 비교에서 제외한다. 나머지 보호 입력의 첫 불일치, 네트워크 접근, 자원 상한 위반이면 중단한다.

저장 원응답을 수정하지 않고 최종 본문·주장·원문 ID·범위·판본·미해결 항목의 동일성을 확인한다. 후보와 실행기 해시를 실행 전에 고정한다. 중첩 시간은 더하지 않는다. 상세 조건은 artifacts/design/criteria.json에 보존했다.'''),
('실험 설계', '''ADR1309의 MAIN136 파생 후보(최종 판단·질문충족 검토표 OFF) 517파일을 그대로 동결했다. 제품 코드 수정은 없다.

첫 실행은 20ms 간격 스택 표본, 선택 함수의 벽시계 타이머, SQLite SQL 모양별 execute/fetch 계측을 사용했다. 완전 일치를 확인한 뒤 두 번째 실행에서 실제 API worker 한 스레드에만 cProfile을 추가했다. 각각 새 프로세스이며 동일한 저장 응답 8개를 사용했다.

외부 socket/DNS는 차단했다. RSS 4GiB와 가용 RAM·swap 증가·디스크 상한을 유지했고 자원 중단은 없었다. 두 진단 시간은 계측 부담이 다른 값이며 서비스 속도 전후 비교가 아니다.'''),
('데이터·모델·재현성', '''부모는 ADR1309 after/ontology-369이다. 같은 SQLite 원문 세대, 저장소 해시, 후보 코드, 응답 기록을 사용했다. 원문·권한·판본·예산·최종 근거 검증은 원래 제품 경로에서 그대로 실행됐다.

두 실행 모두 보호 요청 8/8과 최종 답변이 일치했다. 합계 16개의 저장 응답 소비는 새 모델 호출이 아니다. 새 외부 모델 호출·토큰·비용은 0이다. 관련 작업 모듈 10개의 해시도 동결 후보와 같다. 선택 MAIN136과 Gold binding은 변경하지 않았다.'''),
('결과', '''첫 재생은 121.306초, 상세 프로파일 재생은 163.372초였다. 상세 실행 시간에는 더 큰 계측 부담이 포함된다.

호출 횟수: resolve 16회, verify 14회, children 2,672회. children 안의 generator 재개는 10,546,384회로, 2,672 × (문서 노드 3,946 + 종료 1)과 같다. 각 순회가 전체 256,848개 항목을 검사하는 코드와 결합하면 총 686,297,856회의 문서 ID 조건 검사로 계산된다. 이 6.86억 회는 코드·호출 수·실제 행 수에서 계산한 값이며 직접 하드웨어 카운터로 센 값은 아니다.

children의 표본 시간은 약 88.273초다. 연결 선택지 offer_choices는 9회·50.102초였다. 연결 선택지 생성에도 같은 구조 순회가 들어가므로 두 시간을 합산하면 안 된다.'''),
('사례별 오류 분석', f'''종료 경로는 다음과 같았다.
1. 3번째 응답: 질문의 세 요구 모두 ANSWERABLE. 행동은 FOLLOW_CONNECTION.
2. 4번째 응답: 조사 감독이 CONTINUE_TARGETED.
3. 5번째 응답: FINISH, 추가 원문이 필요 없다고 설명.
4. 6번째 응답: 조사 감독이 REDIRECT. 제371조와 준용 범위를 추가 조사하도록 확장.
5. 7번째 응답: 다시 FINISH.
6. 8번째 응답: 최종 ASSESS.

첫 FINISH 뒤 감독 6번과 선택 7번의 실제 모델 통신에 {s['stop_control']['extra_model_seconds_between_finish_and_assessment']:.3f}초가 들어갔다. 추가된 제371조 설명의 근거는 유효하지만, 종료 요청 뒤 조사 범위가 넓어진 사실은 별도 지연 원인이다.

investigation_supervisor.py:77의 trigger는 FINISH도 TERMINATION_SCOPE_REVIEW로 보낸다. 앞선 중단 수정은 request_repair.no_progress_recovery의 진전 없는 재시도 경로에 적용됐고, 이 감독 경로는 별개다. 최종 검토표 OFF와 조사 감독 enforce도 별도 설정이다. 예산 상한은 작동했지만 필요한 답을 확보한 뒤 바로 끝내는 조건은 충분히 좁혀지지 않았다.'''),
('비용·지연·회수 규모', '''관측 SQLite execute/fetch 시간은 원문 DB 3.100초, 요청 journal 2.416초, 합계 5.516초였다. 이 수치는 행 복원·UDF·일부 관측기 비용을 포함한다. 직접 base 메서드로 실행되는 일부 경로에는 개별 타이머가 없어 순수 DB 전체 시간을 완전히 분리한 값은 아니다.

- FTS5 MATCH: 2회, 0.374초, 반환 8행.
- source_block의 document_id/block_id 점조회: 2,281회, 0.047초.
- source의 ID별 JSON 조회: 1,345회, 0.013초.

query_scope.search_sources는 document_id를 확인하려고 source JSON 메타데이터를 개별 로드하는 경로가 있다. 기록된 호출 스택은 SQL 모양별 최초 관측 스택이며 1,345회 전체를 그 호출자 하나에 배정한 것은 아니다.

새 프로세스에서 ask 시작부터 fulltext 준비 완료까지 19.204초였다. 초기 준비 중 서로 다른 소비자가 전체 source_unit 256,848행을 두 번 읽었고 source 메타데이터 39,992행, term_surface 210,431행도 읽었다. 재사용되는 프로세스의 매 질문마다 동일한 초기 비용이 든다는 뜻은 아니다. SQL 시간과 이 초기 구간도 중첩되므로 합산하지 않는다.'''),
('해석', '''수정 우선순위는 다음과 같다.
1. Nodes.children이 이미 준비된 문서·부모별 children 색인을 사용하게 한다. 동일한 선택 순서·seen metadata·해시·중복/순환·권한 검증을 유지하는 범위부터 고친다.
2. 같은 요청에서 원문 세대·메타데이터 fingerprint·권한·선택 해시가 같은 성공 검증을 재사용해 14회의 재해석을 줄인다. 검증 자체를 삭제하지 않는다.
3. 문서 필터를 SourceScope 또는 문서별 ID 조회에 유지한다. JSON 1,345회 개별 로드와 원문 블록 반복 조회를 묶음 조회·상한 있는 재사용으로 줄인다.
4. FINISH 뒤 조사 감독의 계속 지시를 원래 질문의 명시적 부족 항목, 충돌, 미확보 원문, 예상 답변 변화에 연결한다.
5. SQLite 최초 준비의 중복 메타데이터 로딩을 정리한다. GENOS/Gold 전체 원문을 로컬 SQLite로 복원하는 방식으로 바꾸지 않는다.

단일 조문 좌표의 직접 조회도 후속 대상이다. 다만 기존 metadata_hash가 포함하는 검사 범위가 바뀔 수 있어 호환성 확인이 필요하다. 위 수정의 절감 시간을 아직 측정하거나 보장하지 않는다.'''),
('한계와 일반화 가능 범위', '''이번 88초를 Oracle Gold의 지연으로 옮겨 말할 수 없다. 새 Oracle 호출은 없다.

Gold의 Oracle Units.children_for는 root가 아닌 부모에 owner_id 조건을 걸어 조회한다. 따라서 SQLite의 전체 메모리 순회와 경로가 다르다. 그러나 root(None)는 문서 전체 목록을 읽은 뒤 Python에서 root를 골라내고, 상위 resolve/verify 반복은 공통이다. query_scope는 Oracle SourceScope도 열거하고 개별 메타데이터를 읽을 수 있다.

현재 경로는 resolve당 부모 167개를 조회하고 요청 캐시는 128항목/16MiB 상한이다. 캐시 퇴출과 재조회 가능성은 코드상 위험이며 실제 Gold 왕복 수나 시간으로 확인한 것은 아니다.

cProfile에서 generator의 부모/자식 누적 시간이 정상 포함 관계와 맞지 않았다. 해당 시간 수치는 귀속 판단에서 제외하고 호출 수만 사용했다. 시간 판단은 독립 스택 표본과 명시적 벽시계 타이머를 사용한다. 단일 알려진 성공 경로이고 관측기 부담이 있으므로 일반 지연 분포나 전체 법률 답변 품질을 인증한 결과는 아니다.'''),
('운영 결정·롤백 조건', '''원인 분석을 완료했다. 제품 코드·MAIN136·Gold binding·원문·Oracle·DDL·외부 배포에는 변경이 없다. 실제 답변이 잘 나온 저장 경로를 진단한 결과이며 속도 개선 완료가 아니다.

후속 구현은 구조 색인 연결과 반복 검증부터 수정하고, 동일 응답 재생에서 보호 입력·원문·최종 결과를 대조한 뒤 실제 모델을 포함한 완료 시간으로 확인해야 한다. 진단 실행의 원본 기록과 runtime 파일은 파일별 SHA를 검증한 압축본으로 보존한다.'''),
('재현 명령', '''공식 ADR1310 예약 → 조건 동결과 부모 후보 517파일 snapshot → 관측기 합성 점검 → profile_run.py ontology-369 profile → 완전 일치 확인 → --deep-profile 실행 → analyze_profile.py → Gold 정적 경로 및 읽기 전용 행 수 확인 → 진단 기록 → 해시·상태·최종 검증.

실행 스크립트는 06_TOOLS/EXPERIMENTS/adr_1310, 원본 계측 결과는 본 ADR artifacts/profile 및 artifacts/deep에 있다. 새로운 비교 실행은 새 ADR에 기록한다.''')]
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0]+'\n---\n'
p.write_text(front+'\n# MAIN136 지연 원인 프로파일\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
r=ROOT/'09_ARTIFACTS/AUDITS/20261103-main136-latency-profile/느린이유_함수_SQL_중단로직_분석.txt'
r.write_text('\n\n'.join(f'{i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
# Correct the generated report source's rounding for reproducibility only.
p=ROOT/'06_TOOLS/EXPERIMENTS/adr_1310/finalize_diagnosis.py'
p.write_text(p.read_text().replace('24.539초','24.537초'))
files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(ART.rglob('*')) if p.is_file() and '.observer-versions' not in p.parts and p!=ART/'manifest.json']
put(ART/'manifest.json',{'files':files,'external_calls':0,'product_changes':0})
print('Reports polished; artifact manifest:',len(files))
