from common import *
import ast,importlib.util,shutil,zipfile
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');f=read(DES/'freeze.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==128 and active['release_id']==RELEASE and read(OUT/'main-entry.json')['passed']
assert release['files']==f['files'] and all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
for n in f['product_changes']:
 if n.endswith('.py'):ast.parse((ROOT/n).read_text())
p=ROOT/'06_TOOLS/maintenance/agent_record_oracle_r2.py';sp=importlib.util.spec_from_file_location('final_capacity',p);admin=importlib.util.module_from_spec(sp);sp.loader.exec_module(admin)
db=admin.connection()
with db.cursor() as c:
 c.execute("SELECT COALESCE(SUM(BYTES),0) FROM DBA_SEGMENTS WHERE OWNER='SIDDA'");used=c.fetchone()[0]
 c.execute("SELECT MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME='SIDDA' AND TABLESPACE_NAME='USERS'");quota=c.fetchone()[0]
db.close();disk=shutil.disk_usage(ROOT)
capacity={'sidda_used_bytes':used,'sidda_quota_bytes':quota,'sidda_used_percent':round(100*used/quota,3),
 'disk_used_percent':round(100*disk.used/disk.total,3),'maximum_allowed_percent':90,
 'within_limit':used/quota<=.9 and disk.used/disk.total<=.9,'field_nfs_capacity_measured':False}
assert capacity['within_limit'];put(OUT/'capacity-after.json',capacity)
guide='''Oracle 구조화 기록 / NFS 상세 로그 — 최종 MAIN128, 2026-10-30

저장 책임
  DP 미설정 또는 DP=nfs: 기존 NFS/SQLite 경로 유지.
  DP=oracle: 원문·검색은 기존 Oracle 게시 버전 사용.
  Oracle Agent: 사용자 질문/사실·정정, 원문 판본·좌표·확보/전달 영수증, 구조화 모델 제안,
  채택 판단/관계/근거, 미해결 사항, 최종 답변, 대화/조사 상태·예산·재개·CAS/소유권을 유지.
  NFS: 전체 프롬프트·전송 요청/스키마, 원시 응답/SSE·디버그/traceback,
  상세 JSON 보고서·trace·일반 로그·보고 요약 파일.
  Oracle에는 상세 원문 대신 NFS 위치·내용 해시·크기·capture 상태 참조를 보관한다.

형식
  Oracle 구조화 기록의 기존 SQLROW/JSON 본문 형식과 요청 메모리 SQLite 호환 실행은 유지한다.
  모든 업무 필드를 새 개별 Oracle 컬럼으로 정규화한 구조는 아니다.
  model_attempt의 request는 진단 참조, response는 최소 구조화 응답과 원시 NFS 참조다.
  response_hash는 저장된 구조화 응답의 해시이고, 원본 응답 해시는 NFS 참조에서 확인한다.
  workflow 재개는 Oracle 구조화 응답만 읽으며 NFS 상세 로그에서 모델을 재전송하지 않는다.

설정
  기존 Oracle 연결/권한·원문/조회 게시와 DP=oracle 설정을 유지하고 프로세스를 재시작한다.
  GENOS_SHARED_LOG_DIR은 기존 실제 NFS/CIFS 상세 로그 디렉터리로 지정한다.
  원시 로그의 별도 위치가 필요할 때만 GENOS_DETAIL_LOG_DIR을 추가 지정한다.
  GENOS_SYSTEM_LOG_DIR은 기존 시스템 로그 경로를 유지한다.
  로그 루트가 Oracle runtime/state 루트 전체를 포함하거나 동일하면 거절한다.
  데이터 루트와 상세 로그 루트를 구분한다. 로그 루트가 데이터 루트 아래 별도 하위 폴더인 것은 지원한다.
  GENOS_RUNTIME_DIR/GENOS_STATE_DIR은 Oracle 모드에서 기존 논리 식별자다. 과거 경로/namespace를 유지한다.
  상세 root 미설정/용량초과/실패를 Oracle나 로컬 영구 파일로 우회하지 않는다.

상세 로그 상태
  원시 객체는 agent-raw-v1/.../<내용해시>.json.gz에 무손실 보관한다.
  제한된 메모리 큐로 NFS에 넘긴다. QUEUED는 내구 저장 성공을 의미하지 않는다.
  UNCONFIGURED/CAPTURE_CAPACITY 또는 worker 실패 로그/파일 부재를 보관 성공으로 해석하지 않는다.
  NFS 장애는 핵심 Oracle 판단/답변/재개를 바꾸거나 모델을 추가 전송하는 이유가 아니다.
  프로세스 종료/장애로 상세 기록 일부가 남지 않을 수 있으며 정본 상태와 별개다.
  상세 보고서 독자만 NFS 원시 객체를 펼치고 해시/크기를 확인한다.
  실제 mount를 검증하며 일반 로컬 디렉터리에 상세 로그를 대체 생성하지 않는다.

DB / 이관
  기존 SIDDA 신규3표21컬럼+기존STATE5=4표26컬럼을 그대로 사용. 추가 DDL/Gold 변경0.
  R3 SQL은 R2와 동일하다. 이미 생성한 표/인덱스를 다시 생성하거나 삭제하지 않는다.
  기존 NFS 기록의 명시 이관기는 model_attempt 원시 내용·진단을 NFS에 내구 저장하고,
  구조화 부분·진단 참조만 Oracle에 적재한다. 미사용 compact 로그 blob은 가져오지 않는다.
  원본 파일은 바꾸지 않는다. writer 정지·정확한 원래 절대 경로/namespace가 필요하다.
  원시 기록 이관에 필요한 NFS가 없으면 이관을 완료로 표시하지 않는다.
  기존 Oracle/NFS 과거 기록의 자동 삭제/전량 이전은 수행하지 않았다.

검증 / 상태
  MAIN128 / oracle-structured-20261030-r1, 작업·후보·선택495파일 정확 결속.
  제품11+pin31=42변경. 분리·압축blob누출·이관·NFS없는복원 등18, 서비스2 통과.
  실제 Oracle 원문/기록과 모의모델을 사용하여 NFS 정상/고장, 중복 요청 무추가호출 확인.
  로컬 파일 경로를 반환하는 합성 NFS 어댑터이며 현장 NFS mount 인증은 아니다.
  기존153통과/14실패 동일·새실패0. 실제root 진입과 선택 MAIN 기본 HEALTH도 별도 확인.
  실제 LLM/임베딩0. 실제 GENOS/현장 Oracle19/ORDS/NFS·대량 이관·부하 지연 미검증.
  로컬 사용률은 capacity-after.json 참조. 사용자 한도90% 이내, 현장 NFS 사용률은 미측정.
  속도 개선/전체 법률 품질/전체 저장소 통과를 주장하지 않는다.
  이전 MAIN127/126/125와 Gold 연결기/설정/매핑·원문/벡터/온톨로지 게시 내용 유지.
  Gold engine binding만 같은 MAIN128. Git push/메일/현장배포0.
'''
(OUT/'구조화_Oracle_상세로그_NFS_반영결과.txt').write_text(guide)
source=ROOT/'08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r2';package=ROOT/'08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r3'
shutil.copytree(source,package,ignore=shutil.ignore_patterns('CODE_STATUS.json','SHA256.json','ORACLE_메인_사용법.txt','R2_변경내역.txt'))
for p in package.rglob('*.sql'):assert p.read_bytes()==(source/p.relative_to(package)).read_bytes()
(package/'ORACLE_메인_사용법.txt').write_text(guide)
p=package/'DATAIKU_실행안내.txt';t=p.read_text().replace('지식·기록 전체 Oracle 경로를 사용하는 메인 코드','지식·구조화 기록은 Oracle, 상세 로그는 NFS로 분리하는 메인 코드').replace('GENOS_RUNTIME_DIR/STATE_DIR/SHARED_LOG_DIR 값은 Oracle 모드에서 논리 식별자가 됩니다.','GENOS_RUNTIME_DIR/STATE_DIR은 Oracle 논리 식별자, GENOS_SHARED_LOG_DIR은 실제 NFS 상세 로그 경로입니다.');p.write_text(t)
status={'selected_main':128,'release_id':RELEASE,'release_manifest':bind(ROOT/active['manifest_path']),
 'working_frozen_selected_exact':True,'serving_files':495,'default':'NFS/SQLite',
 'DP=oracle':{'source_storage':'oracle','structured_state_storage':'oracle','diagnostic_storage':'nfs',
 'persistent_sqlite':False,'core_requires_nfs':False,'detailed_log_requires_nfs':True,'raw_transport_body_in_new_oracle_rows':False,
 'structured_payload_format':'Existing SQLROW/JSON body, memory-only SQLite execution'},
 'new_ddl':0,'new_tables_required_from_original_r2':0,'existing_agent_tables':4,'existing_user_columns':26,
 'technical_tests_passed':173,'same_existing_failures':14,'new_failures':0,'capacity':capacity,
 'oracle_nfs_api':bind(ART/'checks-qualified-api.json'),'root_entry':bind(ART/'checks-root-entry-api-002.json'),
 'default_main_entry':bind(OUT/'main-entry.json'),'actual_nfs_history_migrated':False,'field_deployed':False,
 'field_nfs_verified':False,'external_model_calls':0,'performance_certified':False}
(package/'CODE_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
hashes={str(p.relative_to(package)):sha(p) for p in package.rglob('*') if p.is_file()}
(package/'SHA256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
archive=package.with_suffix('.zip')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(package.rglob('*')):
  if p.is_file():z.write(p,str(p.relative_to(package)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None and all(__import__('hashlib').sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
put(OUT/'final-status.json',{**status,'sql_package':bind(archive)})
print('Final MAIN128 split policy,495 exact and unchanged SQL R3 verified')
