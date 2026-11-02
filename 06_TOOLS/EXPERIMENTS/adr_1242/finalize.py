from common import *
import ast,re,zipfile
f=read(DES/'freeze.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/active['manifest_path']);entry=read(OUT/'main-entry.json')
assert active['release_id']==RELEASE and active['generation']==126 and entry['passed']
assert release['files']==f['files'] and all(sha(ROOT/n)==h for n,h in f['files'].items())
assert all(sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
for n in f['files']:
 if n.endswith('.py') and n in f['product_changes']:ast.parse((ROOT/n).read_text())
package=ROOT/'08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r1'
sqls=list(package.rglob('*.sql'))
for p in sqls:
 t=p.read_text().strip();assert ';' not in t and not re.search(r'\b(DROP|TRUNCATE|ALTER|GRANT)\b',t,re.I),p
creates=[p for p in package.glob('*.sql') if p.read_text().startswith('CREATE TABLE')]
indexes=[p for p in package.glob('*.sql') if p.read_text().startswith('CREATE INDEX')]
assert len(creates)==3 and len(indexes)==7
status={'selected_main':126,'release_id':RELEASE,'release_manifest':bind(ROOT/active['manifest_path']),
 'serving_files':494,'working_and_selected_identical':True,
 'default':'NFS/SQLite','DP=oracle':{'source_storage':'oracle','state_storage':'oracle',
 'persistent_sqlite':False,'record_sql_execution':'request-local-memory-only SQLite',
 'nfs_required':False,'fallback_to_files':False},
 'new_tables':3,'new_user_columns':21,'existing_state_tables':1,'existing_state_user_columns':5,'gold_ddl_changes':0,
 'technical_tests_passed':167,'same_existing_failures':14,'new_failures':0,
 'actual_root_oracle_service':bind(ART/'checks-root-entry-api-002.json'),
 'actual_selected_default_entry':bind(OUT/'main-entry.json'),
 'actual_nfs_history_migrated':False,'field_genos_deployed':False,'external_model_calls':0,
 'oracle19_ords_field_verified':False,'performance_certified':False,
 'sql_files':len(sqls),'new_table_files':[p.name for p in creates],
 'guide':'ORACLE_메인_사용법.txt'}
(package/'CODE_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
hashes={str(p.relative_to(package)):sha(p) for p in package.rglob('*') if p.is_file() and p.name!='SHA256.json'}
(package/'SHA256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
archive=package.with_suffix('.zip')
if archive.exists():
 old=OUT/'sql-package-before-code-qualification.zip'
 if not old.exists():archive.replace(old)
 else:raise ValueError('preserve the previous SQL package before replacing')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(package.rglob('*')):
  if p.is_file():z.write(p,str(p.relative_to(package)))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert all(__import__('hashlib').sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
put(OUT/'final-status.json',{**status,'sql_package':bind(archive),'sql_package_files':len(hashes)+1,
 'root_source_files_compiled':True,'graph_existing_errors':16,'graph_new_adr_errors':0})
text='''Oracle 전체 기록 저장 메인 반영 결과 — 2026-10-30

MAIN126 / oracle-records-20261030-r1 선택 완료.
작업·동결 후보 rev-010·선택 릴리스 494파일의 바이트 해시가 모두 동일하다.
제품/워크플로우 명세60 + 엔진 pin31 = 91변경. 신규 모듈5개.
공식 prepare/apply --confirm-main과 활성 포인터, rollback 영수증을 보존했다.

기본값
  DP 미설정/DP=nfs: 기존 NFS·SQLite 경로.
  DP=oracle: 원문·탐색·검색과 대화·조사·실행/재개·판단·답변·게시/진행 기록을
  Oracle 영구 저장소에 연결한다. NFS/CIFS 마운트 검사나 파일 저장 fallback이 없다.
  기존 record SQL/트리거의 호환 실행에만 요청 메모리 SQLite를 사용한다.
  파일 SQLite 복제나 서빙 디스크/NFS 기록은 생성하지 않는다.

DB
  앞서 생성/검증한 SIDDA 신규 RUN9 + REC8 + BODY4 = 3표21컬럼을 사용한다.
  기존 LGL_EXEC_ST_A 5컬럼 포함 총4표26컬럼. 이번 코드 반영의 Gold DDL 변경0.
  실제 테스트는 고유 Agent namespace와 임시 원문 owner만 사용하고 정리했다.
  현장 Dataiku DB에서 실행할 CREATE TABLE/INDEX는 SQL ZIP에 한 문장씩 있다.
  실제 필드 ORDS 계정의 권한 및 기존 원문/조회 릴리스 게시를 먼저 확인해야 한다.

확인
  최종 Oracle 저장/이관/동시성/소유권/원본 복원12 통과.
  실제 원문 SQL + 모의 모델 + 실제 저장 SQL로 v3 대화/v4 조사 서비스2 통과.
  동일 요청 재전송에서 추가 모델 호출0, 답변 동일, 저장 원문/게시 상태 새 연결 조회 통과.
  실제 프로젝트 service/service.service 진입점에서도 같은2조건을 별도로 통과했다.
  기존 본체56통과/14기존실패 동일, 압축·위키·AD·출처97통과. 총167통과·새실패0.
  활성 MAIN126 기본 경로 HEALTH200와13결속/출처 표시 조건 통과.
  ADR 최종 검사 통과. graph 기존16오류 유지, ADR1242 새오류0.
  실제 LLM/새 임베딩0. 실제 법률 품질·현장 Oracle19/ORDS·부하 성능 인증 아님.

기록 이관
  원본 불변·typed 값/NULL/빈문자/BLOB/rowid/PK·중단 후 재개·중복 이관 검사를 통과했다.
  이관이 불완전하면 서빙/기록 열기를 거절한다. 원본을 덮거나 새 원문을 만들지 않는다.
  실제 현장 NFS 전량 이관은 수행하지 않았다. 제공 이관기는 writer 정지 후 별도로 실행한다.
  과거 결속 절대 경로와 namespace를 유지해야 한다. 경로를 바꾸면 다른 기록 공간이다.

지연과 운영 한계
  Oracle 기록 I/O 및 namespace 메모리 복원 비용은 추가된다. 대용량/다중 인스턴스/현장
  ORDS 지연은 별도 측정 대상이다. NFS보다 빠르다거나1초 응답이라는 주장은 하지 않는다.
  기본 memory admission256MiB; 초과를 잘라 성공 처리하지 않는다.
  기존 Dataiku/S3의 지식화 배치 진행·재개·전송 기록 책임은 유지한다.
  Oracle 쓰기 이후 NFS로 되돌릴 때 새 Oracle 기록의 자동 역복사는 없다.

보존과 범위
  이전 MAIN125, NFS 원본, 수정 전 작업 파일, 실패/부분 준비 로그를 보존했다.
  Gold 연결기는 그대로 두고 엔진 binding만 동일 MAIN126으로 결속했다.
  원문/벡터/온톨로지 게시 데이터·매핑/설정 유지. 현장 GENOS 리비전 배포·Git push·메일0.
  실제 반입·DDL·현장 이관 완료로 확대해서 설명하지 않는다.

주요 파일
  final-status.json / activation.json / main-entry.json / rollback.json
  04_EXPERIMENTS/ADR/ADR-1242-oracle-agent-records-main/README.md
  08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r1.zip
  SQL ZIP의 ORACLE_메인_사용법.txt 및 DATAIKU_실행안내.txt
'''
(OUT/'메인반영과_검증결과.txt').write_text(text)
print('Final MAIN126 status and Dataiku SQL package verified')
