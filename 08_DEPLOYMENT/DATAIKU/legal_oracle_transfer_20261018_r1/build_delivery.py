"""Build a data-only handoff from the previously verified, sealed implementation."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD_TRANSFER = ROOT / '08_DEPLOYMENT/DATAIKU/legal_oracle_dp_20261016_r1'
OLD_DP = ROOT / '08_DEPLOYMENT/GENOS/handoffs/oracle_dp_20261016_r1'
PACKAGE = HERE / 'package'
ZIP = HERE / 'LEGAL_ORACLE_TRANSFER_20261018_R1.zip'
NAMES = {
    'tables': 'LEGAL_ORACLE_01_TABLES_20261018_R1.txt',
    'run': 'LEGAL_ORACLE_02_SOURCE_RUN_20261018_R1.txt',
    'verify': 'LEGAL_ORACLE_03_SOURCE_VERIFY_20261018_R1.txt',
    'assets': 'LEGAL_ORACLE_04_ASSETS_20261018_R1.txt',
    'checks': 'LEGAL_ORACLE_05_CHECK_SQL_20261018_R1.txt',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(name, text):
    path = PACKAGE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def prepare():
    PACKAGE.mkdir(exist_ok=True)
    origin_run = OLD_TRANSFER / 'LEGAL_ORACLE_FULL_TRANSFER_20261016_R1_CELL.txt'
    origin_assets = OLD_DP / 'GENOS_ORACLE_DP_20261016_R1_PUBLISH_CELL.txt'
    expected = {
        origin_run: '39380aa182eea5485744138a9e3b4a226b74777983537840f9d326444e0c60da',
        origin_assets: 'eabfaf49f9913f04bab3d9e28679b7392386629f4cf74b058b8862f42d51de66',
        OLD_DP / 'GENOS_ORACLE_DP_20261016_R1_CREATE_TABLES.txt': '2b3a4ae13e13375de62e7473063c14c9301144370bbd397e2961197d1a82ecd2',
    }
    for path, expected_sha in expected.items():
        assert sha(path.read_bytes()) == expected_sha, path
    run = origin_run.read_text()
    write(NAMES['run'], run)
    verify = run.replace('ACTION = "run"', 'ACTION = "verify"', 1).replace('RUN_SECONDS = 3600', 'RUN_SECONDS = 21600', 1)
    verify = ('# 03: 02 단계 SOURCE_COMPLETE 후 실행. 쓰기 없이 전체 행을 다시 대조합니다.\n'
              '# 대조는 기본 6시간 한도이며 중단 후 재실행하면 처음부터 대조합니다.\n'
              + verify[verify.index('ACTION ='):])
    write(NAMES['verify'], verify)
    write(NAMES['assets'], origin_assets.read_text())
    sql = (OLD_DP / 'GENOS_ORACLE_DP_20261016_R1_CREATE_TABLES.txt').read_text()
    write(NAMES['tables'], '-- 01: Dataiku AIDP의 SQL 노트북. CREATE 2개와 GRANT 2개를 각각 별도 Query로 실행합니다.\n'
          '-- 이미 있는 테이블은 재생성하지 않습니다. GRANT는 소유자/권한 담당자가 실행합니다.\n' + sql)
    write(NAMES['checks'], '''-- 05: Dataiku AIDP SQL 노트북. 아래 SELECT를 각각 별도 Query로 실행합니다.
-- 첫 쿼리는 현재 접속 계정을 확인합니다. SIDDA는 테이블 소유자입니다.
SELECT USER AS LOGIN_USER,
       SYS_CONTEXT('USERENV','DB_NAME') AS DB_NAME,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME
FROM DUAL;

-- 5개 테이블의 접근 가능한 목록. 목록만으로 INSERT 권한을 증명하지는 않습니다.
SELECT OWNER, TABLE_NAME
FROM ALL_TABLES
WHERE OWNER='SIDDA' AND TABLE_NAME IN (
 'LEGAL_SRC_DOCUMENT_A','LEGAL_SRC_SOURCE_UNIT_A','LEGAL_SRC_BLOCK_PAYLOAD_A',
 'LEGAL_RAG_ASSET_PART_A','LEGAL_RAG_RELEASE_A')
ORDER BY TABLE_NAME;

-- 데이터 버전별 원문 건수. 03 단계에서 출력된 DATASET_VERSION과 SOURCE_COUNTS를 대조합니다.
SELECT 'LEGAL_SRC_DOCUMENT_A' AS TABLE_NAME, DATASET_VERSION, COUNT(*) AS ROW_COUNT
FROM SIDDA.LEGAL_SRC_DOCUMENT_A GROUP BY DATASET_VERSION
UNION ALL
SELECT 'LEGAL_SRC_SOURCE_UNIT_A', DATASET_VERSION, COUNT(*)
FROM SIDDA.LEGAL_SRC_SOURCE_UNIT_A GROUP BY DATASET_VERSION
UNION ALL
SELECT 'LEGAL_SRC_BLOCK_PAYLOAD_A', DATASET_VERSION, COUNT(*)
FROM SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A GROUP BY DATASET_VERSION
ORDER BY DATASET_VERSION, TABLE_NAME;

-- 04 단계 COMPLETE 후 출력된 DP_RELEASE_ID와 같은 행이 있어야 합니다.
SELECT RELEASE_ID, DATASET_VERSION, CREATED_AT
FROM SIDDA.LEGAL_RAG_RELEASE_A ORDER BY CREATED_AT DESC;
''')
    write('GUIDE_UTF8.txt', '''법규 RAG 데이터 전체 이관 묶음 — 2026-10-18 R1

새로 필요한 테이블은 2개입니다. 기존 원문 3개와 합쳐 총 5개입니다.
이 메일의 01~05 파일을 순서대로 사용합니다. 이전 원문/게시 셀을 따로 찾아 섞을 필요 없습니다.
02와 04의 처리 코드는 앞서 검증한 2026-10-16 R1과 같습니다. 03은 별도 전체 대조용 셀입니다.

대상과 범위
- 기존: SIDDA.LEGAL_SRC_DOCUMENT_A / LEGAL_SRC_SOURCE_UNIT_A / LEGAL_SRC_BLOCK_PAYLOAD_A
- 추가: SIDDA.LEGAL_RAG_ASSET_PART_A / LEGAL_RAG_RELEASE_A
- Oracle 로그인 계정: 현장에서 확인한 BAIP04APP. ORDS alias b04를 사용한 성공한 R6 연결을 재사용합니다.
- SIDDA는 테이블 소유자입니다. 로그인 계정이나 ORDS alias를 SIDDA로 바꾸지 않습니다.
- 원본: /nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation/store.sqlite
- 원문 3테이블과 해당 generation에 선언된 navigation/fulltext/용어집/용어집 캐시를 이관합니다.
  원본 SQLite의 source_block은 block_payload를 복원하는 VIEW여서 별도 Oracle 테이블로 중복 복사하지 않습니다.
- 이 묶음의 '전체'는 위 선택한 RAG generation의 원문과 검색 자산입니다.
  NFS 전체 디렉터리, RAW PDF, 과거 generation, 대화/피드백/실행 로그 DB는 포함하지 않습니다.
  Oracle에서 그래프 노드/관계마다 직접 질의하는 최종 스키마와는 별도인 5테이블 저장 계약입니다.

1. Dataiku에서 추가 SQL 실행
LEGAL_ORACLE_01_TABLES_20261018_R1.txt를 엽니다.
기존 AIDP SQL 노트북에서 CREATE TABLE 2문장을 각각 별도 Query로 실행합니다.
성공 후 GRANT 2문장은 SIDDA 소유자 또는 권한 담당자가 실행합니다.
BAIP04APP에는 기존 원문 3개와 추가 2개 모두 SELECT, INSERT가 필요합니다.
기존 테이블/표본 데이터를 삭제하지 않습니다. 이미 같은 이름이 있으면 05 목록과 열 정의를 확인합니다.
Dataiku Dataset은 필요하면 AIDP / Schema SIDDA / 위 실제 Table 이름으로 등록합니다.
Dataset을 등록하는 것과 Oracle 테이블 생성은 별개입니다.

2. GENOS에서 원문 전체 이관
조회/표본 INSERT에 성공한 01_DATAIKU_ORDS_STEP_BY_STEP_R6.ipynb를 사용합니다.
그 노트북에서 연결이 살아 있는 같은 커널에 새 Code 셀을 만들고
LEGAL_ORACLE_02_SOURCE_RUN_20261018_R1.txt 전체를 붙여넣어 실행합니다.
인증된 desk를 사용하므로 client ID/secret은 이 파일에 넣지 않습니다. bash로 실행하지 않습니다.
첫 출력의 SOURCE_COUNTS, DATASET_VERSION, DP_MIGRATION_RECEIPT를 보관합니다.
status=SOURCE_COMPLETE이면 원문 3개가 이관됐습니다. PAUSED면 같은 셀을 다시 실행합니다.
이미 있는 표본/전체 행은 동일 기본키와 전체 값이 같을 때만 재사용합니다.
다른 값은 덮어쓰지 않고 실패 원인과 기록 경로를 남깁니다. 원본은 읽기 전용입니다.

3. 원문 전체 재조회·대조
02가 SOURCE_COMPLETE가 된 다음, 같은 커널의 새 Code 셀에
LEGAL_ORACLE_03_SOURCE_VERIFY_20261018_R1.txt 전체를 붙여넣고 실행합니다.
기본 6시간 한도이며 Oracle에 쓰지 않고 원문 모든 행/모든 열/CLOB/건수를 다시 대조합니다.
status=VERIFIED와 SOURCE_TRANSFER_VERIFIED=3/3을 확인한 뒤 04로 진행합니다.
VERIFY가 PAUSED면 처음부터 다시 대조합니다. 필요한 경우 셀 상단 RUN_SECONDS를 늘려 재실행합니다.
이 단계의 진행 위치는 이어지지 않으며 최초 작업의 7일 기한과 누적 호출 한도는 유지됩니다.
단순 COUNT 일치만으로 전체 내용 검증이 끝났다고 판단하지 않습니다.

4. 색인·용어집 자산 업로드
같은 커널의 새 Code 셀에 LEGAL_ORACLE_04_ASSETS_20261018_R1.txt 전체를 붙여넣고 실행합니다.
03의 LEGAL_FULL_TRANSFER_RESULT['receipt']를 자동 사용합니다.
커널을 재시작했다면 먼저 R6 연결을 확인하고, 이 셀의 TRANSFER_RECEIPT에
03에서 저장한 실제 VERIFIED 기록 경로를 직접 넣습니다. 임의 새 경로를 만들지 않습니다.
자산은 기존 파일 바이트를 압축·분할하여 저장하며 재색인/재임베딩하지 않습니다.
기본 1시간 한도 PAUSED면 같은 셀을 다시 실행해 저장된 분할 이후부터 이어갑니다.
status=COMPLETE와 DP_RELEASE_ID=<64자리 값>을 보관합니다.
모든 자산을 검증한 뒤 완료 버전을 마지막에 등록합니다. 실패/부분 업로드를 완료로 표시하지 않습니다.

5. Dataiku 확인
LEGAL_ORACLE_05_CHECK_SQL_20261018_R1.txt의 SELECT를 각각 실행합니다.
03의 버전/건수와 04의 DP_RELEASE_ID를 대조합니다.
Explore에 이전 0행 화면이 남아 있으면 샘플 새로고침(Save and Refresh Sample)을 실행합니다.
이번 묶음은 데이터 이관용입니다. 코드 적용·MAIN 선택·서빙 리비전 배포·DP 환경변수 전환은 실행하지 않습니다.
이관 완료와 'NFS 없이 Oracle에서 가져와 답변'하는 워크플로우 시험 완료는 별도로 확인해야 합니다.

중단·복구
- 02 이관은 검증 완료한 배치, 04 업로드는 검증 완료한 분할의 기록을 유지합니다.
- 통신 오류/권한 오류는 FAILED 기록을 확인한 뒤 동일 셀로 명시적으로 재개합니다.
  응답을 못 받았어도 먼저 저장 여부와 전체 내용을 확인하므로 동일 데이터를 무조건 다시 넣지 않습니다.
- 원본/접속 대상/설정 로그 경로는 중간에 바꾸지 않습니다. 02/04 각각 최초 7일·누적 SQL 100만 회 한도입니다.
  기한/한도 초과나 다른 값 충돌은 기록을 지우거나 한도를 초기화하지 말고 원인을 확인합니다.
- 개별 원문 값은 최대 64MiB입니다. 별도 vectors 항목이 있는 generation은 이 계약에서 미지원으로 중단합니다.
  원문을 자르거나 지원하지 않는 색인을 몰래 제외하지 않습니다.
- 인증값/본문을 진단 메일에 붙이지 말고 오류 종류·상태·receipt 경로를 남깁니다.

ZIP 사용
첨부 ZIP을 실제 업로드한 TRANSFER 폴더를 현재 작업 위치로 두고:
python3 -m zipfile -e ./LEGAL_ORACLE_TRANSFER_20261018_R1.zip ./LEGAL_ORACLE_TRANSFER_20261018_R1
풀린 폴더의 01~05 TXT를 위 순서대로 사용합니다. 별도 첨부 TXT도 같은 내용입니다.
~/DEV 설치나 Git push는 이 데이터 이관 묶음의 실행에 필요하지 않습니다.
sources/는 검토용 원본 Python입니다. 노트북 TXT에는 필요한 코드가 포함되어 있습니다.

검증 범위
로컬 실제 임시 SQLite와 모의 Oracle/ORDS로 첨부 셀의 실행·재조회·업로드와 실패/재개를 검사합니다.
결과는 VALIDATION.json에 기록합니다. 망분리 GENOS/Oracle에는 접속하지 않았습니다.
실제 Oracle SQL 엔진의 DDL/PLSQL 실행, 현장 전체 건수·속도·서빙 동작은 현장 실행 결과로 확인해야 합니다.
''')
    copied = {}
    for relative in ['02_BACKEND/semantic_runtime/oracle_dp_io.py',
                     '02_BACKEND/semantic_runtime/oracle_dp_assets.py',
                     '02_BACKEND/lawrag/pipeline/oracle_migration.py',
                     '02_BACKEND/lawrag/pipeline/oracle_publish.py']:
        src = OLD_DP / 'payload' / relative
        name = 'sources/' + Path(relative).name
        write(name, src.read_text())
        copied[name] = {'origin': str(src.relative_to(ROOT)), 'sha256': sha(src.read_bytes())}
    write('SOURCE_BINDING.json', json.dumps({
        'delivery': 'LEGAL_ORACLE_TRANSFER_20261018_R1',
        'scope': 'data-only; selected compact-v2 source plus declared serving assets',
        'runtime_patch_included': False, 'main_pointer_changed': False,
        'origin_cells': {str(p.relative_to(ROOT)): s for p, s in expected.items()},
        'readable_sources': copied,
        'changes': ['Split source verification into a separate cell with 21600-second budget.',
                    'Combine SQL and migration instructions; no migration engine changes.'],
        'namespace_note': 'Standalone cells rewrite imports to isolated module names; readable sources retain original imports.'
    }, ensure_ascii=False, indent=2) + '\n')


def seal():
    assert (PACKAGE / 'VALIDATION.json').is_file(), 'Run package tests before sealing'
    files = sorted(p for p in PACKAGE.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
    assert not any(p.suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs', '.pyc'} for p in files)
    write('SHA256SUMS.txt', ''.join(f'{sha(p.read_bytes())}  {p.relative_to(PACKAGE).as_posix()}\n' for p in files))
    with zipfile.ZipFile(ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in PACKAGE.rglob('*') if p.is_file()):
            archive.write(path, path.relative_to(PACKAGE).as_posix())
    with zipfile.ZipFile(ZIP) as archive:
        assert archive.testzip() is None
        assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in archive.namelist())
        assert all(archive.read(p.relative_to(PACKAGE).as_posix()) == p.read_bytes() for p in PACKAGE.rglob('*') if p.is_file())
    print(json.dumps({'zip': str(ZIP), 'bytes': ZIP.stat().st_size, 'sha256': sha(ZIP.read_bytes())}))


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['seal']:
        seal()
    else:
        prepare()
