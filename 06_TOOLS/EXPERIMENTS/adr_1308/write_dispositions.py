from common import *
OUT.mkdir(exist_ok=True)
catalog=read(ROOT/'09_ARTIFACTS/AUDITS/20261103-gold-fts-optimization/optimization-catalog.json')
notes={
'O01':('APPLIED','검증 완료한 문서 구조·좌표·원문 메타를 요청 안에서 공유. 중단된 페이지는 저장하지 않음. 최초 전체 목록 비용과 4MiB 초과 목록은 남음.'),
'O02':('APPLIED','문서 범위를 Oracle SourceScope 그대로 전달. source ID 1340개를 범위 표현만을 위해 펼치는 경로 제거. 하위범위는 블록 메타로 제한. 과거 ORA01460 원인 전체 해결을 뜻하지 않음.'),
'O03':('APPLIED','키·점수·소속·정확한 중복제거/총계 후 해당 페이지 본문·카드만 읽음. article limit은 서로 다른 source 수 기준 유지.'),
'O04':('APPLIED','단일 토큰은 게시된 tf, 구문은 기존 위치 인접 JOIN. 동일 SQL 결과·점수 Oracle 15조건 확인.'),
'O05':('APPLIED','2048개 이하 Oracle 검색 메타를 group/hit 페이지에서 공유. 초과하면 정확한 DB 페이지 경로로 전환하며 결과를 자르지 않음.'),
'O06':('APPLIED','단일 토큰 전역 df는 COUNT DISTINCT owner, 권한 안 tf만 계산. 구문 df는 종전 전체 문서 계산 유지.'),
'O07':('APPLIED','FTS length source 조건을 물리 OWNER_ID에 적용. 실제 인덱스 선택/성능은 현장 plan 확인 필요.'),
'O08':('APPLIED','EQ·IN·안전한 OR·JSON ID집합을 물리 LOOKUP/OWNER/TARGET 조건으로 전달. NULL/빈값/복합 불확실 조건은 기존 정확 비교 유지.'),
'O09':('CONDITIONAL','과거 로컬 B03 packed UNION 분기는 유지. 현재 목적지 R6/R7 *_1은 unpacked 형식으로 해당 UNION 비용이 없음. 과거 동결 adapter를 고치거나 query release를 다시 게시하지 않음.'),
'O10':('FIELD_REQUIRED','NLSSORT cursor 순서를 보존. 일반 복합 인덱스 후보는 실제 정렬/TEMP 계획 확인 후 결정. 운영 DDL 미실행.'),
'O11':('APPLIED','SQLite MATCH 결과의 탐색 메타를 상한 내 재사용하고 본문은 페이지 선택 뒤 조회. rank,key 동점 정렬 보존; TEMP B-tree 제거를 주장하지 않음.'),
'O12':('PARTIAL','substring 원문 정확 비교는 유지하며 중복 노드 카드는 선택 페이지에만 생성. 임의 부분문자열에는 현재 토큰 FTS를 대신 쓸 수 없음; 새 ngram 색인 미도입.'),
'O13':('APPLIED','Oracle literal 분기 args/params 분리. 빈 결과·중복 블록·카드 페이지 검사 통과.'),
'O14':('PARTIAL','own/subtree 블록 ID 결과를 요청·ACL·단위·extent에 결속해 재사용. CAST 숫자 순서 유지. 새 숫자컬럼/일반 인덱스는 재게시와 현장 계획이 필요.'),
'O15':('APPLIED','legal_normalized 필요 여부에 따라 literal CLOB JOIN 생성. ID·길이·일반본문 조회에서 불필요 JOIN 제거.'),
'O16':('APPLIED','unit 블록 목록과 검증된 SQL 결과를 상한 내 재사용. 원문·소속·권한·변경검사 유지. 물리 SQL 예산을 가상 감소/증가시키지 않음.'),
'O17':('PARTIAL','정확키 pushdown·요청 내 목록 재사용·title 페이지 밖 카드 생성 제거. 한국어 포함검색 자체와 최초 스캔 의미는 유지.'),
'O18':('PARTIAL','정확 count 및 카드 SQL 결과와 같은 glossary 페이지를 재사용. source별 round-robin 유지. 서로 다른 token 페이지의 전체 랭킹 공유는 미구현.'),
'O19':('PARTIAL','완료한 동일 SQL+params+schema 결과와 query tokenization 재사용. OFFSET 상수는 호환 경로에 남아 있으므로 parse 비용 전부 제거를 주장하지 않음.'),
'O20':('EXISTING_PRESERVED','현재 Gold 벡터 경로의 문서/게시 범위 제한·동일 질의 캐시를 유지. exact distance를 ANN으로 바꾸면 결과/재현성 계약이 달라지므로 임의 교체하지 않음.'),
'O21':('EXISTING_PRESERVED','R6의 byte 상한(2MiB) 배치·전송 계측을 R7에서 유지. SQLExecutor2 공개 API에서 일반 native prepared-bind 실행을 확인하지 못해 없는 인터페이스를 추가하지 않음. JDBC literal/LOB 변환은 남음.'),
'O22':('PARTIAL','R7 일반 테이블 OFFSET·FTS length rowid·posting(doc,col,term) 생산자 커서 재개. posting 재개는 완료한 lengths 집계를 생략. 기존 R6 체크포인트 첫 재개, source/native 단계 prefix 재생은 유지. 모든 합성 행 경계 출력 동일.'),
'O23':('APPLIED','원문 확보 뒤 미해결 필요에 연결된 행동이 없으면 no-progress 추가 복구 탐색을 열지 않음. 기존 최대3회/상태·예산·예약·재개 보존. 새 원문을 확보한 정상 탐색의 no_progress 초기화는 유지.'),
'O24':('CONDITIONAL','실제 fallback 발생 기록이 없고 임의 aggregate 결과에는 source row identity가 없으므로 공통 LOB fallback의 정합성 검증을 유지. row identity 고정 없이 원문 점조회로 바꾸지 않음.'),
'O25':('FIELD_REQUIRED','운영 *_1 table/index 통계·index 열·plan 조회 SQL 준비. 기존 로컬 통계 STALE_STATS=NO, V$SQL 권한 없음 기록 유지. 현장 DBMS_STATS/DDL 미실행.'),
'O26':('EXISTING_PRESERVED','MAIN130 layout4 진행 이력 무손실 조각 공유 유지. commit/CAS·장부 내구성에 영향을 주는 기록 생략은 추가하지 않음. 저장 경로/모델 지연과 source SQL 지연 분리.'),
'O27':('APPLIED','ACL 선확인 뒤 허용 게시본 본문을 1배치 조회. 현재 게시/철회·문서권한 확인도 최대8참조 1조회로 묶고 매번 새 DB값 확인.')}
for r in catalog:r['implementation_status'],r['result']=notes[r['id']]
put(OUT/'optimization-disposition.json',catalog)
lines=['27개 진단 항목 반영·잔여 범위','상태는 코드 반영 범위이며 현장 속도 인증이 아니다.','']
for r in catalog:lines.extend([r['id']+' '+r['title']+' ['+r['implementation_status']+']',r['result'],''])
lines.extend(['Dataiku 공개 API 확인: https://developer.dataiku.com/latest/api-reference/python/sql.html','https://developer.dataiku.com/latest/concepts-and-examples/sql.html'])
(OUT/'27개_항목별_반영과_남은조건.txt').write_text('\n'.join(lines)+'\n')
contract=read(ROOT/'08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_fast_20261103_r6/package/contract.json')
names=[v['name'] for v in contract['tables'].values()]
quoted=','.join("'"+n+"'" for n in names)
sql=f'''-- Read-only field diagnostics. Bind OWNER to the actual registered schema.
-- No DBMS_STATS, EXPLAIN PLAN (writes PLAN_TABLE), DDL or full corpus COUNT.
SELECT OWNER,TABLE_NAME,NUM_ROWS,BLOCKS,AVG_ROW_LEN,LAST_ANALYZED,STALE_STATS
FROM ALL_TAB_STATISTICS WHERE OWNER=:OWNER AND TABLE_NAME IN ({quoted})
AND PARTITION_NAME IS NULL ORDER BY TABLE_NAME;
SELECT OWNER,INDEX_NAME,TABLE_NAME,INDEX_TYPE,STATUS,NUM_ROWS,DISTINCT_KEYS,CLUSTERING_FACTOR,LAST_ANALYZED
FROM ALL_INDEXES WHERE TABLE_OWNER=:OWNER AND TABLE_NAME IN ({quoted}) ORDER BY TABLE_NAME,INDEX_NAME;
SELECT INDEX_OWNER,INDEX_NAME,TABLE_NAME,COLUMN_POSITION,COLUMN_NAME
FROM ALL_IND_COLUMNS WHERE TABLE_OWNER=:OWNER AND TABLE_NAME IN ({quoted}) ORDER BY TABLE_NAME,INDEX_NAME,COLUMN_POSITION;
-- Optional, only with existing cursor-view privileges and the measured SQL_ID:
-- SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(:SQL_ID,:CHILD_NUMBER,'ALLSTATS LAST +PREDICATE +ALIAS'));
'''
(OUT/'Gold_운영_읽기전용_실행계획_통계점검.sql').write_text(sql)
print('All 27 items documented; field read-only diagnostics prepared')
