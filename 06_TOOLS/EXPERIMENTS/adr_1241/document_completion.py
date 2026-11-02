from pathlib import Path
import json,hashlib,datetime
R=Path('/home/jin/8-AGENT');U=R/'09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair';G=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
p=G/'README.txt';s=p.read_text();s=s.replace('Gold 연결기 — 로컬 MAIN124 통합 완료','Gold 연결기 — 로컬 MAIN125 Oracle 범위 포트 수정',1).replace('- 엔진: judgment-gold-20261030-r1 / MAIN124','- 엔진: oracle-scope-20261030-r1 / MAIN125',1)
a=s.index('검증 결과와 한계');s=s[:a]+'''검증 결과와 한계
ADR1240 관련114검사 통과/기존8 MAIN124동일·새0. 선택서비스68조건×3설정=204/HEALTH3·모의HTTP3 통과.
실제 Gold 원문·용어·저장벡터3행/native100후보 SQL73, 온톨로지3게시12앵커9경로 SQL157 통과.
SQLite/Oracle scope_keys 포트로 범위 조회를 연결했다. 실제 Oracle 좁은 범위4원문·빈범위0SQL·권한밖거절 확인.
ADR1241 실제 재검증은 호스트 스왑 증가128MiB 초과로4번째 모델 요청 중 중단했다. 정상응답3/진행중결과미확인1·최종답변0.
새임베딩1/벡터100후보/온톨로지369묶음ACQUIRED·원문7대조는 확인했으나 최종입력·답변까지의 전체 E2E는 미완료다.
이번 모델은 문서전체 범위를 골라 좁은 범위 수정함수를 재호출하지 않았다. 해당 수정의 직접 검증은 기술계약과 실제 Oracle 구성요소다.
감독 UNKNOWN은 최종·보완으로 진행하지 않도록 구현되어 있으나 이번 자원감시 종료는 감독 UNKNOWN의 실모델검증이 아니다.
반복 문서페이지 조회 지연은 남는다. 종류 제한 SQL 후보는 속도 이득이 없어 미채택했고 기존 연결기3파일을 유지했다.
필요원문 없는 RESOLVED 반복제출은 NEED_TARGET_INCOMPLETE 등으로 계속 거절한다.
법률 의미·벡터품질·온톨로지 인과효과·현장 Oracle/GENOS 미인증. DB내용·DDL 변경0.

롤백·이력
직전 MAIN124 정식 릴리스와 이전 Gold binding을 보존했다.
09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/gold-rollback.json
09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/gold-before/binding.json
MAIN124로 공식 롤백할 때 Gold binding도 함께 복구한다. 이번에는 connect.py/engine_common.py/physical_mapping.py를 바꾸지 않았다.
ACTIVE_MAPPING과 ontology_settings, 기존 runtime_patches를 보존했다. runtime_patches는 현재 실행하지 않는다.
기존 호스트 프로세스를 자동 재시작하지 않았다. 새 전용 프로세스에서 선택 엔진을 읽는다.
현장 GENOS 배포·Git commit/push·메일 없음.

상세 근거
09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/수정과_실제재검증_결과.txt
04_EXPERIMENTS/ADR/ADR-1240-oracle-fulltext-scope-repair/README.md
04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation/README.md
이전 MAIN124 통합과 실제 실패는 ADR1238·1239, Gold ON 실패는 ADR1233·1235에 보존했다.
''';p.write_text(s)
p=G/'MAPPING_GUIDE.txt';s=p.read_text().replace('2026-10-30 MAIN124 통합:','2026-10-30 MAIN125 Oracle 범위 수정:',1).replace('현재 엔진은 MAIN124 judgment-gold-20261030-r1','현재 엔진은 MAIN125 oracle-scope-20261030-r1');p.write_text(s)
p=G/'ONTOLOGY_ON_GUIDE.txt';s=p.read_text();p.write_text('2026-10-30 최신: MAIN125 oracle-scope-20261030-r1과 같은 엔진을 사용한다. Oracle 범위 포트 수정·Gold ON/DB 유지. 실제1241은 벡터100후보·온톨로지 확보 후 호스트 스왑 증가로 중단, 최종답변 미완료. 현재 사용·롤백은 README.txt 및 09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/gold-rollback.json을 따른다. 아래 MAIN124/MAIN120 설명은 이전 통합·실험 이력이다.\n\n'+s)
p=R/'AGENTS.md';s=p.read_text();marker='<!-- ORACLE_SCOPE_MAIN125_1240_1241 -->';assert marker not in s
note='''<!-- ORACLE_SCOPE_MAIN125_1240_1241 -->
**2026-10-30 — Oracle 본문검색 범위 수정 MAIN125·실제 재검증 자원중단:** [수정·재검증 TXT](09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/수정과_실제재검증_결과.txt) · [ADR1240](04_EXPERIMENTS/ADR/ADR-1240-oracle-fulltext-scope-repair/README.md) · [ADR1241](04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation/README.md). **MAIN125/oracle-scope-20261030-r1·489파일·제품3+pin31=34변경**, SQLite/Oracle `scope_keys` 포트로 직접execute 누락 수정·ACL/판본/hash·좌표 유지. **114통과/기존8 MAIN124동일·새0, 후보61·선택204/HEALTH3·모의HTTP3**, 실제 Gold 원문/저장벡터100후보SQL73·온톨로지3/12/9 SQL157·좁은범위4원문/SQL2 통과. Gold같은MAIN·연결기3파일불변·R18/ON·DB유지; 종류제한SQL 후보는속도이득없어미채택. **실제1241 전송경계4/정상3/진행중1미확인, HOST_SWAP_GROWTH>128MiB exit125·최종0·CM009미실행**. 약250.900초는파일시각차(정상timer아님), 정확자원최댓값미저장. 새임베딩1/벡터100후보→원문1·온톨로지369ACQUIRED·원문7/입력8·wire4 불일치0, SQL로그2576완료/경계141.511초·페이지115회114.200초·보고$0.00730248(중단요청미보고). **이번모델은문서전체범위라수정한좁은범위함수재호출아님**, 직접수정검증은1240실제Oracle 구성요소. 최종온톨로지/벡터전달·감독UNKNOWN실효·법률품질미검증. 강제종료누락자료를합성하지않고post-stop읽기전용분석, journal SENT보존·재실행0. 1064동결전후동일·MAIN124/완료실패보존·DB내용/DDL·GENOS/Git/메일0. 반복조회지연과자원중단계측보강남음.
<!-- /ORACLE_SCOPE_MAIN125_1240_1241 -->

'''
head,rest=s.split('\n',1);p.write_text(head+'\n\n'+note+rest.lstrip('\n'))
S=Path('/mnt/c/Users/Jin/.codex/skills/legal-rag-db-optimization/references');p=S/'incidents.md';title='## 2026-10-30 MAIN125 Oracle scope_keys 수정·실모델 자원중단 (ADR1240/1241)';assert title not in p.read_text()
with p.open('a') as stream:stream.write('\n\n'+title+'''

- ADR1239 직접 SQLite execute 누락을 제품3파일의 SQLite/Oracle scope_keys 포트로 수정하고 MAIN125 oracle-scope-20261030-r1에 통합했다.489파일·제품3+pin31. 원문/ACL/판본/hash/좌표검증 유지.114기술통과·기존8동일/새0, 선택204검사; 실제 Gold 범위4원문/SQL2, 저장벡터100후보SQL73, 온톨로지3게시12앵커9경로SQL157 통과.
- 기존 Gold 연결기3파일은 불변. 게시kind 제한 후보는 owner28행1.019635→1.049969초/page100행1.024931→1.017032초로 이득없어 미채택. SQLite개선이나 코드 모양만으로 Oracle속도향상을 주장하지 않는다. 반복 페이지조회 지연은 남는다.
- 실제1241 전송경계4/stop3/진행중1, 호스트스왑증가128MiB 초과로exit125. 진행중결과미확인이고 native blank/timeout UNKNOWN으로 분류하지 않는다. 호스트전체지표를 이번프로세스 단독원인으로 단정하지 않는다. 원문7/입력8/전송4 불일치0·벡터임베딩1/100후보/확보1·온톨로지369 ACQUIRED, 최종0. SQL로그2576완료·141.511초/페이지115회114.200초. 약250.900초는 파일시각차이며 정확자원값은 in-memory sample 유실로 미보고. 강제exit 시finally telemetry가 보존되지 않는 실행기 보강 필요.
- 모델은 이번에 문서전체 범위를 선택해 query_scope.fulltext가 좁은 범위 포트호출 전에 반환했다. 따라서 RECALL을 넘었다는 사실을 같은좁은경로 실모델통과로 확대하지 않는다. 수정포트직접검증은1240실제Oracle 구성요소. 감독UNKNOWN/최종온톨로지·벡터전체/법률품질 미검증. CM009미실행,재시도0. DB/GENOS/Git/메일0. 기존1239는 수정전 이력.
- 원본:09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/수정과_실제재검증_결과.txt, activation.json, live-result.json; ADR1240/1241 README와 artifacts/run-001;1241 live/gold-369/post-stop는 보존자료 사후분석이며 정상종료결과 대체가 아니다.
''')
p=S/'source-map.json';m=json.loads(p.read_text());files=['09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/수정과_실제재검증_결과.txt','09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/activation.json','09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/live-result.json','04_EXPERIMENTS/ADR/ADR-1240-oracle-fulltext-scope-repair/README.md','04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation/README.md'];m['oracle_scope_main125']={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'Port fix selected; technical pass, actual run resource interrupted; original Gold connector preserved; no full model answer','sources':[{'path':x,'sha256':hashlib.sha256((R/x).read_bytes()).hexdigest()} for x in files]};p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
print('Updated current Gold guides, AGENTS history and DB optimization memory')
