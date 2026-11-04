from common import *
import shutil,datetime
OUT=ART/'main';RELEASE='oracle-development-vector-20261104-r1';rp=ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json'
for n in ('main-entry','gold-entry'):assert read(OUT/(n+'.json'))['passed']
assert read(ART/'prepared-api/result.json')['failed']==0
f=read(DES/'candidate-integrated.json');release=read(rp)
assert all(sha(ROOT/n)==sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
logs=ART/'retained-logs';logs.mkdir(exist_ok=True)
for p in Path('/tmp').glob('adr1317-*.log'):
 dest=logs/p.name
 if not dest.exists():shutil.copyfile(p,dest)
put(OUT/'gold-vector/result.json',{'status':'OBSERVER_FAILED_AFTER_RETRIEVAL','embedding_attempts':1,'retrieval_returned':True,
 'candidate_rows':100,'first_source_coordinate_verified':True,'complete_top5_verification':False,'sql_started':8,
 'error':'Recorder accessed page row[value]; page returns logical value directly','log':str((logs/'adr1317-gold-vector.log').relative_to(ROOT))})
put(OUT/'gold-vector-r2/result.json',{'status':'RESOURCE_STOP','embedding_attempts':1,'retrieval_returned':'not recorded',
 'reason':read(OUT/'gold-vector-r2/resource-stop.json')['reason'],'no_retry_after_resource_stop':True,'complete':False})
oracle=read(ART/'prepared-api/runtime/test_actual_main_oracle_source0/actual-oracle.json')
summary={'status':'COMPLETE_WITH_FIELD_UNVERIFIED','main':138,'release':RELEASE,'serving_files':525,'candidate_files':540,'changed_vs_main137':37,
 'product_files':6,'pin_files':31,'prepared_contracts':32,'prepared_actual_Oracle_sql_calls':len(oracle['sql']),
 'prepared_actual_Oracle_checks':oracle['checks'],'Oracle_version':oracle['oracle_version'],
 'regression_passed':68,'regression_failed':1,'fixture_binding_failure_followup_boot_passed':9,
 'native_sql_Oracle_passed':39,'main_entry_checks':16,'Gold_binding_checks':9,'tests_overlap':True,
 'runtime_source_sqlite_files':0,'runtime_sqlglot_imports':0,'request_memory_sqlite_calls':2,
 'prepared_actual_embedding_fixture_calls':1,'real_GENOS_embedding_calls':0,'LLM_calls':0,
 'additional_existing_Gold_vector_attempts':[read(OUT/'gold-vector/result.json'),read(OUT/'gold-vector-r2/result.json')],
 'temporary_Oracle_schemas_created_and_dropped':6,'existing_Oracle_data_mutations':0,
 'PeCab_pyarrow_changes':0,'field_deployed':False,'field_full_service_verified':False,'quality_certified':False,
 'same_candidate_working_MAIN':True,'handoff':read(OUT/'handoff.json')}
put(ART/'final-checks.json',summary);put(RUN/'result.json',summary)
m=read(ADR/'실험/manifest.json');put(ART/'candidate-experiment-before-cutover.json',m)
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'user_directed_cutover',
 'reason':'User requested development MAIN using all Oracle data. Frozen candidate revisions retained; actual local Oracle and prepared API checks preceded official MAIN138 apply. Field execution and real GENOS model are unverified.',
 'production_paths_modified_before_decision':True,'runtime_import_allowed':True,'production_registry_registered':True,'main_wiring_unchanged':False,'candidates':[],
 'release':{'manifest_path':str(rp.relative_to(ROOT)),'sha256':sha(rp),'release_id':RELEASE}}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'integrated':summary},usage={'LLM_calls':0,'GENOS_embeddings':0,'local_BGE_attempts':2},
 latency={},error_taxonomy=[{'type':'product_tempfile_Oracle_logical_path','count':1,'fixed':True},
 {'type':'test_code_root_workflow_binding','count':1,'fixed_observer':True},
 {'type':'Gold_vector_observer_row_shape','count':1,'retrieval_completed_but_probe_incomplete':True},
 {'type':'resource_global_swap_growth','count':1,'retry_after_stop':False}])
put(ADR/'실험/manifest.json',m)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
bodies=[
 'MAIN138 oracle-development-vector-20261104-r1 로컬 반영. 서빙525·작업/후보540파일 동일, MAIN137대비37변경(제품6+pin31). 개발계 설정은 DP=oracle 및 development_g19_1. 현장 전체 완료는 아니며 GENOS 반입 ZIP/설정/점검도구를 준비했다.',
 '기존 표준 Oracle Factory는 G19 원문·검색·실행기록 매핑을 사용하지만 initial_vector는 옛 PBLS/SEG/ACT 테이블을 사용했다. Dataiku 적재 프로필과 GENOS 질의 임베딩 설정 연결도 없었다. 실제 서비스 검사 중 RAG_SEARCH가 Oracle 논리 runtime을 tempfile 폴더로 사용해500 발생.',
 '사전 criteria에서 현재 MAIN/원문·권한·판본·기한 보존, 실제 Oracle 원문·검색·벡터·상태와 파일DB fallback 차단을 정했다. 사용자 정정으로 PeCab/pyarrow 수정은 구현·실행 전 제외했으며 이전 criteria도 보존했다. 서빙 sqlglot 없이 준비 SQL 사용을 유지한다.',
 'ADR 선점 후539파일 격리, 새 vector 모듈 등록해540파일 rev001. 실제 Oracle에서 tempfile 오류 발견 후 document_agent 수정·rev002. 임시split-owner2개씩17테이블, 컬럼 순서변경. 합성2문서/3원문을 게시하고 원문파일을 격리한 뒤 실제 service.py와 동일 resources를 사용. 공식prepare 후 같은검사 재실행·apply.',
 'Oracle23.26.3.0.0 loopback 임시스키마만 사용·모두삭제. ORDS HTTP envelope는 직접 DBAPI로 대체하여 실제 SQL을 실행했다. 임베딩은 고정3차원 응답; 실제 GENOS 임베딩/답변모델0. 실제 service와 전체 후보 SHA 고정·engine30/dependency497 및 준비639계획 확인.',
 '최종 준비릴리스32계약 통과(벡터22+실제Oracle서비스1+boot9). 실제Oracle서비스 내부92SQL 및 10기능확인:17테이블/기동/원문/검색/벡터포트/거리/원문좌표/ACL/재사용/기록재조회. nativeSQL 실제Oracle39통과. 회귀68통과/1fixture실패는 코드루트 일치시키고boot9통과. 실제선택MAIN16·Goldbinding9통과. 중복검사 합산금지.',
 '제품 tempfile 실패는 미사용 매핑파일 생성을 제거해 해결. fixture는 workspace service와 candidate workflow 혼합으로 실패했고 같은ROOT로 정정. 추가 기존Gold검사는100후보/1로컬BGE인코딩 반환 후 기록기 value필드 오류; 후속은SQL7시작 뒤global swap164MB증가로 보호중단. 이 둘은 전체 성공으로 집계하지 않으며 보호중단 후 재시도하지 않았다.',
 '성능 비교 실험이 아니며 속도향상 수치 없음. 새외부LLM0/GENOS임베딩0, 기존 로컬BGE2시도(1조회반환+1결과미기록보호중단). 개발계 검증의 벡터SQL은 합성데이터이고 실제 모델 의미검색 품질을 입증하지 않는다.',
 'G19 VCTR_HEAD/POST/ITEM을 물리컬럼 투영으로 읽고 source/query/dataset/documents/profile/READY를 결속. 동일프로필 SHA와 실제 serving명 명시, GENOS endpoint/tenant/차원·유한값 검사, 문서ACL·source필터·기한·100후보상한·요청내재사용 유지. 검색후보는 근거가 아니며 원문검증 유지.',
 '실제 개발계 ORDS HTTP·임베딩서버·답변모델·코드서빙 revision 미접근. 온톨로지 작성/게시 전체는 이번 미검증이며 DP=oracle에서 SQLite ontology fallback은 기존거부. 로컬일반모드 기본값은 보존하고 개발계는 명시 DP=oracle 필수. 기존Gold추가probe 미완료를 별도보존.',
 '사용자 MAIN 개발계정상/모든데이터Oracle 요청에 따라 USER_DIRECTED_CUTOVER quality_certified=false. 기존원문/Gold매핑/게시/제공자/PeCab 그대로, Gold엔진만 같은MAIN 연결. 새release rollback/ACTIVE_RELEASE.json=MAIN137, main/gold-before.json=기존binding. 외부배포/Git push/메일0.',
 'freeze.py → check.py vector/oracle/regression/boot/native → prepare_release.py → check.py --arm prepared → activate.py → main_entry.py/gold_entry.py → package.py. 별도 gold_vector.py 실패/중단기록도 보존. 현장 실행명령은 main138_oracle_vector_20261104_r1/개발계_확인방법.txt.']
p=ADR/'README.md';front=p.read_text().split('\n---\n',1)[0].replace('main_wiring: unchanged','main_wiring: user-directed-cutover')+'\n---\n'
p.write_text(front+'\n# 개발계 Oracle 벡터 연결과 MAIN138\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{x}' for i,(t,x) in enumerate(zip(titles,bodies),1))+'\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261104-oracle-development-main138';report.mkdir(exist_ok=True)
(report/'수정_검증_개발계확인.txt').write_text('개발계 Oracle 연결과 MAIN138 반영 — 2026-11-04\n\n'+'\n\n'.join(bodies)+'\n')
for n in ('final-checks.json','working-integration.json'):shutil.copyfile(ART/n,report/n)
for n in ('activation.json','handoff.json'):shutil.copyfile(OUT/n,report/n)
print('Audit/report created; final validation and runtime archival remain')
