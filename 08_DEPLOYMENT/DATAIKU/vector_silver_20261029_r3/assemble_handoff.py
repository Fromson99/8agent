from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET,zipfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261029-vector-silver-minimal'
AUDIT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
suite=ET.parse(HERE/'TEST_RESULTS_final.xml').getroot()[0]
assert suite.get('failures')=='0' and suite.get('errors')=='0' and suite.get('skipped')=='0'
delivery=json.loads((HERE/'DELIVERY_VALIDATION.json').read_text());assert delivery['strict_success']
receipt=json.loads((HERE/'BUILD_RECEIPT.json').read_text())
value={'strict_success':True,'tests':int(suite.get('tests')),'test_seconds':float(suite.get('time')),
 'native_local_oracle':True,'native_tables':2,'native_columns':6,'vector_row_columns':4,'publication_columns':2,
 'silver_tables':10,'silver_columns':47,'agent_tables':1,'agent_columns':5,
 'actual_dataiku_jdbc':False,'dataiku_public_sdk_mock_http':True,'recipe_entry_with_native_oracle':True,
 'genos_querysql_consumer_native_oracle':True,'literal_install_cell':True,'python_files_compiled':delivery['python_files_compiled'],
 'base_release':receipt['base_release'],'main_activation_changed':False,'working_product_changed':False,
 'actual_genos_deployment':False,'external_or_internal_model_calls':0,'actual_repo_commit_push':False,'mail_sent':False,
 'code_zip_sha256':receipt['code_zip_sha256'],'genos_patch_sha256':sha(HERE/'GENOS_COMPACT_PATCH_20261029_R3.zip'),
 'checks':['native VECTOR insert/cosine/ACL/root grouping','same schema create twice and strict metadata/index checks',
  'batch size and full transaction rollback','failed partial build resume and no re-embedding READY data',
  'lease ownership, active unique index, compare-and-swap A-B-A protection','separate Oracle session NOWAIT lock conflict',
  'Dataiku entrypoint check/build/resume plus GENOS QuerySQL/Retriever','literal Dataiku installation/public SDK',
  'literal GENOS patch from MAIN117 and previous R2; unrelated file protection and hash drift refusal'],
 'preserved_initial_results':[
  {'file':'TEST_RESULTS_initial.xml','passed':15,'failed':7,'reason':'nullable JSON lease/revision required explicit NULL ON EMPTY'},
  {'file':'TEST_RESULTS_second.xml','passed':21,'failed':1,'reason':'legacy projection parser rejected native Oracle JSON RETURNING syntax'},
  {'file':'TEST_RESULTS_third.xml','passed':24,'failed':0},
  {'file':'TEST_RESULTS_index_check.xml','passed':19,'failed':7,'reason':'strict index checker needed Oracle canonical TYPE(LAX) normalization'}],
 'limits':['column count reduction is not a latency or storage reduction measurement','field deployment/embedding/ORDS untested',
  'prior vector tables preserved, no automatic data migration','Gold naming/JSON/VECTOR registration and DBA creation unapproved']}
(HERE/'VALIDATION.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
files=['00_CHECK_TARGET.sql','01_CREATE_VECTOR_SILVER.sql','02_CHECK_VECTOR.sql',
 'VECTOR_SILVER_CODE_20261029_R3.zip','DATAIKU_INSTALL.txt','DATAIKU_RUN.txt',
 'GENOS_COMPACT_PATCH_20261029_R3.zip','GENOS_COMPACT_APPLY.txt','GUIDE.txt','requirements.txt',
 'TABLE_COLUMNS_GOLD_DRAFT.xlsx','TABLES.csv','COLUMNS.csv','BASE_BINDING.json',
 'BUILD_RECEIPT.json','DELIVERY_VALIDATION.json','VALIDATION.json','TEST_RESULTS_final.xml']
manifest={p:sha(HERE/p) for p in files}
(HERE/'HANDOFF_SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
archive=HERE/'VECTOR_SILVER_HANDOFF_20261029_R3.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for name in files+['HANDOFF_SHA256.json']:z.write(HERE/name,name)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in manifest.items())
value['handoff_zip_sha256']=sha(archive);value['handoff_zip_bytes']=archive.stat().st_size
(AUDIT/'VALIDATION.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
(AUDIT/'결과.txt').write_text(f'''사용자 요청: 벡터 DB 추가 테이블의 컬럼을 최대한 줄인 SQL·Flow·조회 연결 전달.
결과: 3테이블/14컬럼 → 2테이블/6컬럼 (벡터 4, 게시 관리 2).
문서/원문 ID 중복 삭제, 게시 명세·작업 잠금·완료·활성 순번을 JSON으로 통합.
원문/권한/모델 바인딩·부분 노출 방지·실패 재개·동시 교체 보호 유지.
로컬 실제 Oracle, Flow 진입점, GENOS QuerySQL 소비자, 실제 전달 설치기 {value['tests']}검사 통과.
별도 literal Dataiku 설치 셀/공개 SDK 및 {delivery['python_files_compiled']}Python 컴파일 통과.
초기 JSON 빈값/기존 SQL parser/색인 메타 정규화 실패는 원본 XML 보존 후 수정.
성능/저장량 감소 실험이 아니며, 현장 Oracle/ORDS/GENOS/모델은 미실행.
기존 14/18컬럼 테이블과 데이터는 보존, 기존 벡터 자동 이관은 미구현.
작업 제품/선택 MAIN 변경·실제 Git commit/push·메일 발송 없음.
전달 ZIP: {archive.relative_to(ROOT)}
SHA256: {value['handoff_zip_sha256']}
검증 세부: 동일 폴더 VALIDATION.json 및 전달 폴더 TEST_RESULTS_*.xml.
''',encoding='utf-8')
print(json.dumps({'zip':str(archive),'bytes':archive.stat().st_size,'tests':value['tests'],'tables':2,'columns':6}))
