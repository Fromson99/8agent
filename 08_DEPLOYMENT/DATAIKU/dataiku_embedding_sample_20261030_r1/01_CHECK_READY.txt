# Dataiku LEGAL_RAG > Notebooks > Python: 이 파일 전체를 한 셀에 붙여 실행.
# 읽기 전용 준비 확인. 임베딩 호출, DB 쓰기, 전체 Flow 실행 없음.
import json
import re
import dataiku

CONNECTION = str(dataiku.get_custom_variables().get("LEGAL_ORACLE_CONNECTION", "AIDP"))
OWNER = "SIDDS"
# 승호님 integration 1fe63bf00의 기본값. 현재 프로젝트에 실제 등록됐는지는 아래에서 대조.
REFERENCE_MODEL_ID = (str(dataiku.get_custom_variables().get("ELS_EMBED_LLM_ID", "") or "").strip()
                      or "openai:genos-embedding:embedding-kure-v1")
if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", OWNER):
    raise ValueError("OWNER must be an Oracle identifier")
executor = dataiku.SQLExecutor2(connection=CONNECTION)

def query(sql):
    frame = executor.query_to_df(sql, infer_from_schema=True, parse_dates=False)
    frame.columns = [str(c).upper() for c in frame.columns]
    return frame

def failure(stage, exc):
    # 접속 비밀값이나 SQL 전문을 결과에 복제하지 않는다.
    codes = sorted(set(re.findall(r"ORA-\d{5}", str(exc))))
    print(stage, "FAILED", type(exc).__name__, ",".join(codes))

tables = {
    "LGL_DOC_BLK_S": "샘플 입력: 원문 본문",
    "LGL_DOC_VER_S": "원문 연결: 문서와 판본",
    "LGL_DOC_UNIT_S": "원문 연결: 조문과 구조",
    "LGL_VCTR_SET_S": "저장 시험: 벡터 게시본 관리",
    "LGL_VCTR_ITEM_S": "저장 시험: 실제 임베딩 벡터",
    "LGL_SRC_PBLS_S": "정식 적재: 완료 원문 게시본",
    "LGL_SRCH_PBLS_S": "정식 적재: 완료 조회 게시본",
    "LGL_SRCH_ROW_S": "정식 적재: 탐색·검색 행",
}
print("CONNECTION", CONNECTION, "OWNER", OWNER)
print("ROW_SAMPLE_COUNT는 최대 3이며 전체 행수가 아닙니다.")
readiness = []
for table, purpose in tables.items():
    row = {"table": OWNER + "." + table, "purpose": purpose}
    try:
        df = query(f"SELECT 1 AS PRESENT FROM {OWNER}.{table} WHERE ROWNUM <= 3")
        row.update(readable=True, row_sample_count=len(df))
    except Exception as exc:
        row.update(readable=False, row_sample_count=None,
                   error_type=type(exc).__name__,
                   oracle_codes=sorted(set(re.findall(r"ORA-\d{5}", str(exc)))))
    readiness.append(row)
print("TABLE_READINESS")
print(json.dumps(readiness, ensure_ascii=False, indent=2))
print("조회 실패는 테이블 부재 또는 권한/연결 문제일 수 있습니다.")

try:
    vector_columns = query(f"""
      SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,NULLABLE
      FROM ALL_TAB_COLUMNS WHERE OWNER='{OWNER}'
      AND TABLE_NAME IN ('LGL_VCTR_SET_S','LGL_VCTR_ITEM_S')
      ORDER BY TABLE_NAME,COLUMN_ID
    """)
    print("VECTOR_COLUMNS")
    print(vector_columns.to_string(index=False))
    vector_capability = query("""
      SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,0]',2,FLOAT32)) AS DIMENSIONS,
      VECTOR_DISTANCE(TO_VECTOR('[1,0]',2,FLOAT32),
                      TO_VECTOR('[1,0]',2,FLOAT32),COSINE) AS DISTANCE
      FROM DUAL
    """)
    print("VECTOR_FUNCTION_CHECK")
    print(vector_capability.to_string(index=False))
except Exception as exc:
    failure("VECTOR_FUNCTION_OR_METADATA_CHECK", exc)

# 부분 이관 데이터의 통신 시험 후보입니다. 완료 게시본/권한/전체 무결성 인증이 아닙니다.
# 문자열은 로컬 노트북 메모리에만 두며 모델로 보내지 않습니다.
sample = None
try:
    sample = query(f"""
      SELECT DATA_VER_ID,DOC_ID,UNIT_ID,BLK_ID,SRC_DATA_HASH_VAL,
             DBMS_LOB.SUBSTR(BLK_TXT_CN,800,1) AS SAMPLE_TEXT
      FROM {OWNER}.LGL_DOC_BLK_S
      WHERE BLK_TXT_CN IS NOT NULL AND DBMS_LOB.GETLENGTH(BLK_TXT_CN)>0
        AND ROWNUM <= 3
    """)
    sample = sample[sample["SAMPLE_TEXT"].map(lambda x: isinstance(x,str) and bool(x.strip()))]
    summary = sample.drop(columns=["SAMPLE_TEXT"]).copy()
    summary["SAMPLE_CHARS"] = sample["SAMPLE_TEXT"].map(len)
    print("SOURCE_SAMPLES", len(sample))
    print(summary.to_string(index=False))
    print("sample 변수에 최대 3건, 건당 앞 800자가 있습니다. 아직 모델 호출/저장 없음.")
except Exception as exc:
    failure("SOURCE_SAMPLE_CHECK", exc)

try:
    project = dataiku.api_client().get_default_project()
    models = project.list_llms(purpose="TEXT_EMBEDDING_EXTRACTION")
    model_ids = []
    print("DATAIKU_EMBEDDING_MODELS")
    for model in models:
        model_ids.append(model.id)
        print(model.id, "|", model.description)
    if not model_ids:
        print("이 프로젝트에서 보이는 LLM Mesh 임베딩 모델이 없습니다.")
    print("SEUNGHO_REFERENCE_MODEL_ID", REFERENCE_MODEL_ID)
    print("REFERENCE_MODEL_VISIBLE", REFERENCE_MODEL_ID in model_ids)
    print("목록 조회만 했습니다. 내부/외부 서비스 여부와 모델 버전은 등록 설정에서 확인하세요.")
except Exception as exc:
    failure("DATAIKU_MODEL_LIST", exc)
    print("목록 실패는 DSS 버전/권한/등록 방식 문제일 수 있습니다. 별도 API 모델은 여기에 없을 수 있습니다.")

print("CHECK_FINISHED: 실제 임베딩 생성·Oracle 저장·검색 시험은 아직 실행하지 않았습니다.")
