"""데이터 플랫폼 오라클의 벡터 표(짧은 이름 `vdb_chunk`) 정의 — Dataiku ELS_QA 프로젝트의 정본.

실제 이름 · 스키마(dev 는 SIDDS.ELS_QA_VDB_CHUNK_S)는 환경별 매핑(`deploy/db_mapping.yaml`)이 정한다.

## 무엇인가

전처리기(`preprocessor/adapter.py` 의 compose_vectors)가 넘긴 조각을 Dataiku 가 임베딩해
이 표에 쌓고, 질의는 ORDS 로 이 표를 검색한다(`oracle_search.py`).

## 표 모양 — 왜 이렇게 두었나

열 이름은 사내 표준 용어(심의 통과 골드 컬럼 마스터)를 따른다. 내부망 임베딩 플러그인(AT03 의
embed-chunks → AT03_OKMS_EMBED)은 텍스트 · 키 · 내용 해시 · 벡터 열 이름과 입력 열 이름 바꾸기를
설정으로 받으므로 이 이름으로도 붙일 수 있다. 플러그인은 내용 해시가 바뀐 조각만 다시 임베딩한다(smart_sync).

| 열 | 왜 |
|---|---|
| CHNK_ID | 적재 묶음의 조각 ID(`<문서ID>:<순번>`). 상품 카드 조각은 `:card`. 플러그인의 key_column |
| DOC_ID · PRDT_CODE · DOC_TYPE | 질의가 상품으로 좁히고, 옛 판 조각을 문서 ID 로 거른다. DOC_ID 는 적재 표의 DOC_ID |
| CHNK_SEQ_NO · CHNK_TYPE · TTL_PATH_CTNT · SECTION_KIND · PAGE_NO | 문서 안 순번과 검색 결과에서 쓰는 속성 |
| EMBD_TXT_CTNT · DISPLAY_TXT_CTNT | 임베딩한 글자(플러그인의 text_column)와 화면에 보이는 글자 — 둘이 다를 수 있다 |
| CHNK_META_CTNT | 나머지 속성(bbox · 쪽 안 순번 등)을 통째로 |
| CHNK_CTNT_HASH | EMBD_TXT_CTNT 의 해시 — 바뀐 조각만 다시 임베딩할 때 본다(플러그인의 content_hash_column) |
| EMBD_MDL_NAME · EMBD_DMSN_CONT | 어느 모델로 만든 벡터인가 — 모델이 다르면 같은 1024차원이어도 섞으면 안 된다 |
| EMBD_DATE_TIME · ORIG_CTNT_HASH · EMBD_BTCH_EXE_ID | 플러그인이 임베딩할 때 남기는 기록 |
| EMBD_VCTR | VECTOR(1024, FLOAT32) — 지금 임베딩(KURE-v1 · bge-m3)이 1024차원 |

**오라클에서 조각은 이 표에만 있다** — 적재 표에는 조각 표가 없다. 그래서 `STORAGE_BACKEND=ords`
의 검증 도구도 조각을 여기서 읽는다. 적재 표와 FK 로 묶지 않는다. 벡터는 다른 프로젝트가 따로 쓰고 지울 수 있어야 해서다.
적재 묶음과의 어긋남은 전처리 레시피가 CHNK_ID · 내용 해시로, 임베딩 레시피가 문서 행의
조각 수(TXT_CHNK_CONT · TABLE_CHNK_CONT)로 막는다.

**VECTOR 타입은 오라클 23ai 이상에만 있다.** 그 아래 판이면 표 만들기가 ORA-00902(잘못된 타입)로
실패하고, 레시피가 그렇게 알린다. 벡터 인덱스(HNSW · IVF)는 메모리 설정 · 권한이 따로 걸려 있어
여기서 만들지 않는다.

이 파일은 패키지 import 없이 파일 경로로 읽히므로 다른 모듈을 import 하지 않는다.
"""
from __future__ import annotations

# 짧은 이름 — 매핑의 키. 실제 이름은 매핑에 있다.
VDB_CHUNK = "vdb_chunk"
TABLE_MARK = "{{%s}}"
EMBED_DIM = 1024
# 일시는 시간대 없이 한국 시간으로 고정한다(orcl_schema.KST_NOW 와 같은 식 — 서로 import 하지 않는다).
KST_NOW = "CAST(SYSTIMESTAMP AT TIME ZONE 'Asia/Seoul' AS TIMESTAMP(6))"

TABLES: dict[str, dict] = {
    VDB_CHUNK: {
        "description": "조각 임베딩 — 조각은 이 표에만 둔다(적재 표에는 없다)",
        "comment": "ELS 상품 문서 조각 임베딩내역 — 상품 문서를 조각(청크)으로 나누고, 각 조각의 본문과 의미를 "
                   "숫자 벡터로 바꾼 값을 보관한다. 질문과 의미가 가까운 조각을 찾는 검색에 쓴다.",
        "column_comments": {
            "CHNK_ID": "청크ID — 조각 하나를 구분하는 고유 식별자.",
            "DOC_ID": "문서ID — 조각이 속한 문서 버전의 식별자. 문서 표의 같은 값과 연결한다(물리적 참조 제약은 없음).",
            "PRDT_CODE": "상품코드 — 조각이 속한 상품의 상품코드. 검색할 때 상품으로 범위를 좁히는 데 쓴다.",
            "DOC_TYPE": "문서유형값 — 조각이 속한 문서의 종류.",
            "CHNK_SEQ_NO": "청크순번 — 문서 안에서 조각의 순서.",
            "CHNK_TYPE": "청크유형값 — 조각의 종류. text(본문), table(표), spec_card(상품 조건값 카드).",
            "TTL_PATH_CTNT": "제목경로내용 — 조각이 속한 절의 목차 경로.",
            "SECTION_KIND": "절구분값 — 조각이 속한 절의 구분(손익구조, 조기상환, 기초자산 등).",
            "PAGE_NO": "페이지번호 — 조각이 있는 문서 페이지 번호.",
            "EMBD_TXT_CTNT": "임베딩텍스트내용 — 임베딩(숫자 벡터 변환)에 사용한 조각 텍스트.",
            "DISPLAY_TXT_CTNT": "표시텍스트내용 — 화면에 보여주는 조각 텍스트. 임베딩에 쓴 텍스트와 다를 수 있다.",
            "CHNK_META_CTNT": "청크메타데이터내용 — 조각의 기타 속성(위치 좌표, 페이지 안 순서 등)을 JSON으로 저장한 값.",
            "CHNK_CTNT_HASH": "내용해시값 — 조각 텍스트의 해시값. 내용이 바뀐 조각만 다시 임베딩하는 데 쓴다.",
            "EMBD_MDL_NAME": "임베딩모델명 — 벡터를 만든 임베딩 모델의 이름.",
            "EMBD_DMSN_CONT": "임베딩차원수 — 벡터의 차원 수.",
            "EMBD_DATE_TIME": "임베딩일시 — 임베딩을 수행한 일시.",
            "ORIG_CTNT_HASH": "원천내용해시값 — 임베딩할 때 기록한 원천 텍스트의 해시값.",
            "EMBD_BTCH_EXE_ID": "임베딩배치실행ID — 임베딩을 수행한 배치 실행을 구분하는 식별자.",
            "EMBD_VCTR": "임베딩벡터값 — 조각 텍스트를 1024차원 숫자 벡터로 바꾼 값. 의미가 가까운 조각을 찾는 검색에 쓴다.",
            "CRTN_DATE_TIME": "생성일시 — 행이 생성된 일시.",
        },
        "columns": [
            ("CHNK_ID", "VARCHAR2(64) NOT NULL"),
            ("DOC_ID", "VARCHAR2(36) NOT NULL"),
            ("PRDT_CODE", "VARCHAR2(32) NOT NULL"),
            ("DOC_TYPE", "VARCHAR2(64 CHAR) NOT NULL"),
            ("CHNK_SEQ_NO", "NUMBER(10)"),
            ("CHNK_TYPE", "VARCHAR2(16) NOT NULL"),
            ("TTL_PATH_CTNT", "VARCHAR2(1024 CHAR)"),
            ("SECTION_KIND", "VARCHAR2(16)"),
            ("PAGE_NO", "NUMBER(10)"),
            ("EMBD_TXT_CTNT", "CLOB NOT NULL"),
            ("DISPLAY_TXT_CTNT", "CLOB"),
            ("CHNK_META_CTNT", "CLOB"),
            ("CHNK_CTNT_HASH", "VARCHAR2(64) NOT NULL"),
            ("EMBD_MDL_NAME", "VARCHAR2(128) NOT NULL"),
            ("EMBD_DMSN_CONT", "NUMBER(10)"),
            ("EMBD_DATE_TIME", "TIMESTAMP(6)"),
            ("ORIG_CTNT_HASH", "VARCHAR2(64)"),
            ("EMBD_BTCH_EXE_ID", "VARCHAR2(64)"),
            ("EMBD_VCTR", "VECTOR(%d, FLOAT32) NOT NULL" % EMBED_DIM),
            ("CRTN_DATE_TIME", "TIMESTAMP(6) DEFAULT %s NOT NULL" % KST_NOW),
        ],
        "constraints": [
            "CONSTRAINT PK_ELSQA_VDB PRIMARY KEY (CHNK_ID)",
            "CONSTRAINT CK_ELSQA_VDB_TYPE CHECK (CHNK_TYPE IN ('text', 'table', 'spec_card'))",
            "CONSTRAINT CK_ELSQA_VDB_PAGE CHECK (PAGE_NO IS NULL OR PAGE_NO > 0)",
            "CONSTRAINT CK_ELSQA_VDB_META CHECK (CHNK_META_CTNT IS JSON)",
        ],
        "indexes": [
            "CREATE INDEX IX_ELSQA_VDB_DOC ON {t} (PRDT_CODE, DOC_ID)",
        ],
    },
}


def marked(key: str) -> str:
    """표 자리표시 — `{{vdb_chunk}}`."""
    return TABLE_MARK % key


def table_ddl(table: str, name_of=marked) -> str:
    """CREATE TABLE 문. `name_of(짧은 이름)` 이 표 이름 자리를 채운다 — 기본은 자리표시(환경과 무관)."""
    spec = TABLES[table]
    lines = [f"{name:<16} {oracle_type}" for name, oracle_type in spec["columns"]]
    lines += list(spec["constraints"])
    body = ",\n    ".join(lines)
    return f"CREATE TABLE {name_of(table)} (\n    {body}\n)"


def index_ddl(table: str, name_of=marked) -> list[str]:
    return [i.format(t=name_of(table)) for i in TABLES[table]["indexes"]]


def _quote(text: str) -> str:
    return "'%s'" % text.replace("'", "''")


def comment_ddl(table: str, name_of=marked) -> list[str]:
    """표 · 열 설명(COMMENT ON) — 실제 이름이 30바이트로 줄어 있어 논리명 · 정의를 DB 에 같이 남긴다.

    같은 문장을 몇 번 돌려도 결과가 같아(덮어쓴다) 레시피가 매 실행마다 다시 건다.
    """
    spec = TABLES[table]
    name = name_of(table)
    out = ["COMMENT ON TABLE %s IS %s" % (name, _quote(spec["comment"]))]
    out += ["COMMENT ON COLUMN %s.%s IS %s" % (name, column, _quote(spec["column_comments"][column]))
            for column, _ in spec["columns"]]
    return out


def all_ddl(name_of=marked) -> list[str]:
    out: list[str] = []
    for table in TABLES:
        out.append(table_ddl(table, name_of))
        out += index_ddl(table, name_of)
    return out
