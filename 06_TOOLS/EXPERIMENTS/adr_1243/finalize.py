from common import *
import ast,re,shutil,zipfile
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');f=read(DES/'freeze.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==127 and active['release_id']==RELEASE and read(OUT/'main-entry.json')['passed']
assert release['files']==f['files'] and all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
for n in f['product_changes']:
 if n.endswith('.py'):ast.parse((ROOT/n).read_text())
source=ROOT/'08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r1'
package=ROOT/'08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r2'
shutil.copytree(source,package,ignore=shutil.ignore_patterns('CODE_STATUS.json','SHA256.json'))
sqls=list(package.rglob('*.sql'))
assert all(p.read_bytes()==(source/p.relative_to(package)).read_bytes() for p in sqls)
assert all(';' not in p.read_text() and not re.search(r'\b(DROP|TRUNCATE|ALTER|GRANT)\b',p.read_text(),re.I) for p in sqls)
assert sum(p.read_text().startswith('CREATE TABLE') for p in package.glob('*.sql'))==3
assert sum(p.read_text().startswith('CREATE INDEX') for p in package.glob('*.sql'))==7
status={'selected_main':127,'release_id':RELEASE,'release_manifest':bind(ROOT/active['manifest_path']),
 'working_frozen_selected_exact':True,'serving_files':494,'default':'NFS/SQLite',
 'DP=oracle':{'source_storage':'oracle','state_storage':'oracle','persistent_sqlite':False,'nfs_required':False,
 'record_sql_execution':'request-local-memory-only SQLite','GENOS_RUNTIME_DIR_required':False,
 'default_logical_runtime':'/__oracle_agent__/runtime','fallback_to_files':False},
 'new_tables':3,'new_user_columns':21,'existing_state_columns':5,'total_agent_tables':4,'total_agent_user_columns':26,
 'gold_ddl_changes':0,'ddl_identical_to_r1':True,'current_follow_up_tests_passed':16,'current_new_failures':0,
 'parent_implementation_tests_passed':167,'parent_existing_failures_not_fixed':14,
 'parent_result':bind(ROOT/'04_EXPERIMENTS/ADR/ADR-1242-oracle-agent-records-main/artifacts/run-001/result.json'),
 'actual_root_bare_oracle_service':bind(ART/'checks-root-entry-api-002.json'),'actual_selected_default_entry':bind(OUT/'main-entry.json'),
 'external_model_calls':0,'actual_nfs_history_migrated':False,'genos_field_deployed':False,'oracle19_ords_field_verified':False,
 'performance_certified':False,'guide':'ORACLE_메인_사용법.txt'}
(package/'CODE_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
(package/'R2_변경내역.txt').write_text('최종 MAIN127/oracle-default-20261030-r1. 신규표 SQL은 R1과 동일합니다.\nGENOS_RUNTIME_DIR 생략 시에도 서비스 AD/로그/복구/채팅과 Oracle Factory의 기본 경로를 통일했습니다.\n이 코드 변경을 이유로 기존 표를 다시 만들거나 삭제하지 않습니다.\n기존 Oracle 연결·조회 게시와 권한은 필요합니다. 현장 GENOS 배포·기록 전량 이관·부하 성능 인증은 별도입니다.\n')
hashes={str(p.relative_to(package)):sha(p) for p in package.rglob('*') if p.is_file()}
(package/'SHA256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
archive=package.with_suffix('.zip')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(package.rglob('*')):
  if p.is_file():z.write(p,str(p.relative_to(package)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None and all(__import__('hashlib').sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
graph=ROOT/'09_ARTIFACTS/AUDITS/20261030-oracle-default-runtime-main-graph.log'
errors=[l for l in graph.read_text().splitlines() if l.startswith('ERROR:')];assert len(errors)==16 and not any('1243' in l for l in errors)
put(OUT/'final-status.json',{**status,'sql_package':bind(archive),'graph_existing_errors':16,'new_graph_errors':0})
(OUT/'최종_메인반영과_사용방법.txt').write_text('''Oracle 전체 기록 저장 — 최종 MAIN127, 2026-10-30

선택 완료: oracle-default-20261030-r1 / MAIN127.
작업 코드·격리 후보·선택 릴리스494파일의 해시가 동일하다.
공식 prepare/apply와 이전 MAIN126/125·Gold binding·수정 전 파일을 보존했다.

DP 미설정/DP=nfs는 기존 NFS/SQLite 경로를 유지한다.
DP=oracle이면 기존 Oracle 원문·조회 게시 버전과 Agent 영구 저장소만 사용한다.
대화·조사·실행·판단·답변·재개·게시·확보 원문/진행·보고서의 저장 소비자를 연결했다.
파일 SQLite/NFS/CIFS 마운트/파일 fallback 없음. 기존 SQL/트리거의 호환 실행만 요청 메모리 SQLite다.
GENOS_RUNTIME_DIR을 생략해도 /__oracle_agent__/runtime으로 서비스·AD·보고서·복구·채팅 경로가 같다.
기존 명시 절대 경로는 Oracle 모드에서 논리 식별자로 유지된다. namespace/과거 경로를 함부로 바꾸지 않는다.

DB: 신규 SIDDA RUN9 + REC8 + BODY4 = 3표21컬럼, 기존 STATE5 포함4표26컬럼.
Gold 추가/DDL 변경0. 원문·벡터·온톨로지 게시 내용/매핑/설정 유지.
Gold 연결기 바이트는 유지하고 engine binding만 같은 MAIN127에 결속했다.

검증: 부모1242의167기술통과/기존14동일/새0. 이번 기본값 보완은 별도1243이다.
MAIN126의 bare-DP 실제 게이트웨이 경로 불일치 API2를 재현했다.
후보의 기존Oracle 저장12+기본Oracle/NFS경로2+runtime env 없는 실제원문/모의모델/실제기록 API2=16통과.
실제root service/service.service 진입2통과, 선택MAIN127 기본 NFS HEALTH200/13결속도 통과했다.
새 실모델/임베딩0. ADR최종 통과, graph기존16/새0. 서로 반복된 검사를 독립 표본으로 합산하지 않는다.

사용: 기존 Oracle 연결/인증·권한·원문/조회 게시를 준비하고 DP=oracle 설정 후 프로세스를 재시작한다.
Dataiku SQL 노트북용 agent_record_oracle_20261030_r2.zip에 CREATE TABLE3/INDEX7을 문장별로 제공한다.
R2 DDL은 R1과 동일하다. 이미 정상 생성한 표를 삭제하거나 다시 생성하지 않는다.
패키지 DATAIKU_실행안내.txt, ORACLE_메인_사용법.txt, CODE_STATUS.json 참조.

미수행: 현장 Dataiku DDL/GENOS 리비전 반입·기존 NFS 전량 이관·Oracle19/ORDS·실제LLM·부하 성능 검증.
실제 현장 이관은 writer 정지 후 제공 이관기로 수행한다. 원본 불변/중단 재개/중복 방지/불완전 시 서빙 거절.
원본 NFS를 유지하며 Oracle 신규 기록을 NFS로 자동 역복사하지 않는다. 기존 Dataiku/S3 배치 책임 유지.
메모리 복원 및 SQL 왕복 비용이 있어 가속·1초 응답을 보장하지 않는다.
Git push/메일/현장 배포0. 전체 법률 품질/전체 저장소 회귀 통과로 확대하지 않는다.
''')
print('Final MAIN127, exact494 files and Dataiku SQL R2 package verified')
