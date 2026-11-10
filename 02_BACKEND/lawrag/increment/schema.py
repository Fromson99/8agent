"""증분 처리 테이블 정의 — 개발계·운영계 같은 이름, 소유자(owner)만 설정값.

이름은 운영 Gold 규약(IDD_B003_LGL_ + 표준단어 약어, 30바이트 이내)을 따른다.
기존 Gold 13표에 이미 쓰인 단어(RGLT·DOC·VER·HASH_VALU·DTLS·STRC_UNIT·RGSN_ASTM·
ADDN_IFMN_CTNT·TAGT·RFRN·NAME·ID·NO·YN)를 재사용했고, 나머지 약어는 메타마이너
표준단어 확인·신청 대상 후보다 (NEW_WORDS).

Gold와의 연결은 키만 둔다 (런타임 조인 없음)
- RGLT_VER.RGLT_DOC_ID   → IDD_B003_LGL_DOC_VER.RGLT_DOC_ID (판본마다 바뀌는 본문 sha 앞 16자리)
- RGLT_VER.DTLS_HASH_VALU → IDD_B003_LGL_DOC_VER.DTLS_HASH_VALU (그 판본이 게시된 Gold 세대)
- ARTC_VER.STRC_UNIT_ID  → IDD_B003_LGL_DOC_UNIT.STRC_UNIT_ID
활성화 때만 같은 트랜잭션에서 IDD_B003_LGL_SRCH_CHNL 포인터를 CAS로 바꿀 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass

PREFIX = "IDD_B003_LGL_"

# 도메인 → (Oracle 타입, SQLite 타입)
DOMAINS = {
    "ID": ("VARCHAR2(100 BYTE)", "TEXT"),
    "CODE": ("VARCHAR2(30 BYTE)", "TEXT"),
    "DT": ("VARCHAR2(8 BYTE)", "TEXT"),
    "YN": ("CHAR(1 BYTE)", "TEXT"),
    "NAME": ("VARCHAR2(2250 BYTE)", "TEXT"),
    "TITLE": ("VARCHAR2(2000 BYTE)", "TEXT"),
    "HASH": ("VARCHAR2(100 BYTE)", "TEXT"),
    "TEXT": ("VARCHAR2(4000 BYTE)", "TEXT"),
    "CLOB": ("CLOB", "TEXT"),
    "NUM": ("NUMBER(10,0)", "INTEGER"),
    "RATE": ("NUMBER(5,4)", "REAL"),
    "TS": ("TIMESTAMP(6) WITH TIME ZONE", "TEXT"),
}


@dataclass(frozen=True)
class Column:
    name: str
    domain: str
    required: bool
    logical: str
    note: str = ""


@dataclass(frozen=True)
class Table:
    key: str
    logical: str
    purpose: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    indexes: tuple[tuple[str, ...], ...] = ()

    @property
    def name(self) -> str:
        return PREFIX + self.key


def C(name, domain, required, logical, note=""):
    return Column(name, domain, required, logical, note)


TS_COLS = (C("RGSN_ASTM", "TS", True, "등록일시"), C("CHG_ASTM", "TS", True, "변경일시"))

TABLES: tuple[Table, ...] = (
    Table("RGLT_DOC", "규정문서기본", "문서 불변 ID 레지스트리. 이름이 바뀌어도 코드는 유지한다.", (
        C("RGLT_DOC_CD", "ID", True, "규정문서코드", "LAW:<법령ID> / ADMRUL:<행정규칙ID> / INTERNAL:<내규코드>"),
        C("SRC_SE_CD", "CODE", True, "원천구분코드", "LAW / ADMRUL / INTERNAL"),
        C("OFCL_ID", "ID", False, "공식ID", "법령ID·행정규칙ID"),
        C("RGLT_DOC_NAME", "NAME", True, "규정문서명", "현행 공식 명칭 (Gold DOC_VER와 같은 컬럼명)"),
        C("ALIAS_CTNT", "CLOB", False, "별칭내용", "이전 명칭·별칭 JSON 배열"),
        C("ACTV_VER_ID", "ID", False, "활성판본ID", "가장 최근 활성화된 판본"),
        *TS_COLS), ("RGLT_DOC_CD",)),
    Table("RGLT_VER", "규정판본내역", "문서 판본(공포·발령 단위)과 시행 구간, Gold 연결 키.", (
        C("RGLT_VER_ID", "ID", True, "규정판본ID"),
        C("RGLT_DOC_CD", "ID", True, "규정문서코드"),
        C("LOAD_WORK_ID", "ID", True, "적재작업ID"),
        C("BASE_VER_ID", "ID", False, "기준판본ID", "비교 기준이었던 직전 판본"),
        C("SRC_HASH_VALU", "HASH", True, "원천해시값", "원문 파일 sha256"),
        C("RGLT_DOC_ID", "ID", False, "규정문서ID", "Gold DOC_VER.RGLT_DOC_ID (본문 sha 앞 16자리)"),
        C("DTLS_HASH_VALU", "HASH", False, "명세해시값", "이 판본이 게시된 Gold 세대"),
        C("PRMG_DT", "DT", False, "공포일자", "법령 공포일자·행정규칙 발령일자"),
        C("PRMG_NO", "ID", False, "공포번호", "법령 공포번호·행정규칙 발령번호"),
        C("ENFC_STRT_DT", "DT", True, "시행시작일자"),
        C("ENFC_END_DT", "DT", False, "시행종료일자", "다음 판본 시행일 - 1일"),
        C("VER_STTS_CD", "CODE", True, "판본상태코드", "CANDIDATE / ACTIVE / SUPERSEDED / REJECTED / ROLLED_BACK"),
        C("VER_ADDN_IFMN_CTNT", "CLOB", False, "판본부가정보내용", "명칭·제개정구분·부칙 시행일 판독 JSON"),
        C("RGSN_ASTM", "TS", True, "등록일시"),
        C("ACTV_ASTM", "TS", False, "활성일시"),
        C("SPSD_ASTM", "TS", False, "대체일시", "다음 판본으로 대체된 기록 시점"),
    ), ("RGLT_VER_ID",), (("RGLT_DOC_CD", "VER_STTS_CD"),)),
    Table("ARTC_VER", "조문판본내역", "조문 단위 판본. 바뀐 조문만 새 행, 옛 행은 시행 구간만 닫는다.", (
        C("ARTC_VER_ID", "ID", True, "조문판본ID"),
        C("RGLT_DOC_CD", "ID", True, "규정문서코드"),
        C("RGLT_VER_ID", "ID", True, "규정판본ID", "이 행을 만든 판본"),
        C("ARTC_KEY_VALU", "ID", True, "조문키값", "165의3 / 1-1 / 별표1 / 전문 / 부칙:21065"),
        C("LNG_ID", "ID", True, "계보ID", "번호가 바뀌어도 유지"),
        C("ARTC_SEQ", "NUM", False, "조문순번"),
        C("ARTC_SE_CD", "CODE", True, "조문구분코드", "ARTICLE / PREAMBLE / ANNEX / ADDENDUM"),
        C("ARTC_TITLE_NAME", "TITLE", False, "조문제목명"),
        C("ARTC_CTNT", "CLOB", False, "조문내용"),
        C("CTNT_HASH_VALU", "HASH", True, "내용해시값", "공백 제거·NFKC 후 sha256"),
        C("CMPR_HASH_VALU", "HASH", True, "비교해시값", "자기 번호 제거·인용 번호 가림"),
        C("ATCH_HASH_VALU", "HASH", False, "첨부해시값", "별표서식 첨부 파일 sha256"),
        C("ENFC_STRT_DT", "DT", True, "시행시작일자"),
        C("ENFC_END_DT", "DT", False, "시행종료일자"),
        C("CHG_TYPE_CD", "CODE", True, "변경유형코드", "ADD / AMEND / MOVE / MOVE_AMEND / REF_ONLY"),
        C("STRC_UNIT_ID", "ID", False, "구조단위ID", "Gold DOC_UNIT 연결 (게시 후)"),
        C("OPEN_YN", "YN", True, "공개여부", "N=색인 준비 중(숨김), Y=활성"),
        C("ARTC_ADDN_IFMN_CTNT", "CLOB", False, "조문부가정보내용", "법제처 조문변경여부·이동 태그 JSON"),
        C("RGSN_ASTM", "TS", True, "등록일시"),
        C("SPSD_ASTM", "TS", False, "대체일시"),
    ), ("ARTC_VER_ID",), (("RGLT_DOC_CD", "OPEN_YN", "ENFC_END_DT"), ("LNG_ID",), ("RGLT_VER_ID",))),
    Table("LOAD_WORK", "증분적재작업내역", "입력 1건(문서+원문 sha)의 처리 상태. 같은 입력 재실행은 같은 행.", (
        C("LOAD_WORK_ID", "ID", True, "적재작업ID", "문서코드+원천 sha 결정적 ID"),
        C("RGLT_DOC_CD", "ID", True, "규정문서코드"),
        C("SRC_SE_CD", "CODE", True, "원천구분코드"),
        C("SRC_HASH_VALU", "HASH", True, "원천해시값"),
        C("SRC_FILE_NAME", "TITLE", False, "원천파일명"),
        C("BASE_VER_ID", "ID", False, "기준판본ID"),
        C("NEW_VER_ID", "ID", False, "신규판본ID"),
        C("PRCS_STTS_CD", "CODE", True, "처리상태코드",
          "DETECTED→PARSED→DIFFED→PREVIEW→APPROVED→INDEXING→ACTIVATED(→ROLLED_BACK) / NO_CHANGE / REJECTED / BLOCKED / BLOCKED_PENDING / FAILED"),
        C("STTS_CHG_NO", "NUM", True, "상태변경번호", "상태 전이 CAS"),
        C("FAIL_STEP_NAME", "CODE", False, "실패단계명"),
        C("PRVW_HASH_VALU", "HASH", False, "미리보기해시값", "승인자가 본 대비표 해시"),
        C("GATE_RSLT_CTNT", "CLOB", False, "게이트결과내용", "건수·변경률·경고·멈춤 사유 JSON"),
        C("APRV_USER_ID", "ID", False, "승인사용자ID"),
        C("APRV_ASTM", "TS", False, "승인일시"),
        C("ERR_CTNT", "TEXT", False, "오류내용"),
        *TS_COLS), ("LOAD_WORK_ID",), (("PRCS_STTS_CD",), ("RGLT_DOC_CD",))),
    Table("LOAD_HIST", "적재상태이력", "상태 전이 감사 기록 (추가만).", (
        C("LOAD_WORK_ID", "ID", True, "적재작업ID"),
        C("HIST_SEQ", "NUM", True, "이력순번"),
        C("BFR_STTS_CD", "CODE", False, "이전상태코드"),
        C("AFTR_STTS_CD", "CODE", True, "이후상태코드"),
        C("HIST_CTNT", "CLOB", False, "이력내용", "사용자·사유·건수 JSON"),
        C("RGSN_ASTM", "TS", True, "등록일시"),
    ), ("LOAD_WORK_ID", "HIST_SEQ")),
    Table("ARTC_CMPR", "조문비교결과", "신구조문 대비표의 행. SAME은 건수만 게이트에 남긴다.", (
        C("LOAD_WORK_ID", "ID", True, "적재작업ID"),
        C("CMPR_SEQ", "NUM", True, "비교순번"),
        C("CHG_TYPE_CD", "CODE", True, "변경유형코드"),
        C("OLD_ARTC_VER_ID", "ID", False, "이전조문판본ID"),
        C("OLD_ARTC_KEY_VALU", "ID", False, "이전조문키값"),
        C("NEW_ARTC_KEY_VALU", "ID", False, "신규조문키값"),
        C("NEW_ARTC_VER_ID", "ID", False, "신규조문판본ID"),
        C("LNG_ID", "ID", True, "계보ID"),
        C("SMLR_RATE", "RATE", False, "유사비율"),
        C("JDGM_RSN_CTNT", "TEXT", False, "판정사유내용"),
        C("ENFC_STRT_DT", "DT", False, "시행시작일자"),
        C("RULE_RVW_YN", "CODE", True, "룰재검토여부", "Y / N / NA"),
        C("CMPR_ADDN_IFMN_CTNT", "CLOB", False, "비교부가정보내용", "새 조문 제목·내용·첨부 sha·공식 태그 JSON"),
        C("RGSN_ASTM", "TS", True, "등록일시"),
    ), ("LOAD_WORK_ID", "CMPR_SEQ")),
    Table("IDX_WORK", "색인작업내역", "숨김 색인 준비 상태. 전부 READY여야 활성화한다.", (
        C("LOAD_WORK_ID", "ID", True, "적재작업ID"),
        C("IDX_KIND_CD", "CODE", True, "색인종류코드", "REF / GOLD / VECTOR"),
        C("ARTC_KEY_VALU", "ID", True, "조문키값", "문서 단위 작업은 *"),
        C("IDX_STTS_CD", "CODE", True, "색인상태코드", "PENDING / READY / FAILED"),
        C("EXPC_CNT", "NUM", False, "예상건수"),
        C("RSLT_CNT", "NUM", False, "결과건수"),
        C("RSLT_REF_VALU", "TEXT", False, "결과참조값", "Gold 세대·게시 해시 등"),
        C("ERR_CTNT", "TEXT", False, "오류내용"),
        *TS_COLS), ("LOAD_WORK_ID", "IDX_KIND_CD", "ARTC_KEY_VALU")),
    Table("ARTC_RFRN", "조문참조관계", "조문판본의 인용. 대상은 계보ID로 잇기 때문에 번호가 밀려도 유지된다.", (
        C("ARTC_VER_ID", "ID", True, "조문판본ID", "인용한 조문판본"),
        C("RFRN_SEQ", "NUM", True, "참조순번"),
        C("RGLT_DOC_CD", "ID", True, "규정문서코드"),
        C("LNG_ID", "ID", True, "계보ID", "인용한 조문의 계보"),
        C("TAGT_RGLT_DOC_CD", "ID", False, "대상규정문서코드", "외부 법령은 명칭으로 찾은 경우만"),
        C("TAGT_ARTC_KEY_VALU", "ID", True, "대상조문키값"),
        C("TAGT_LNG_ID", "ID", False, "대상계보ID"),
        C("EXTR_YN", "YN", True, "외부여부"),
        C("RFRN_TEXT_CTNT", "TITLE", False, "참조원문내용"),
        C("RGSN_ASTM", "TS", True, "등록일시"),
    ), ("ARTC_VER_ID", "RFRN_SEQ"), (("TAGT_LNG_ID",), ("TAGT_RGLT_DOC_CD", "TAGT_ARTC_KEY_VALU"))),
    Table("RVW_TRGT", "재검토대상내역", "영향 전파 결과. 내용은 자동으로 바꾸지 않고 후보만 올린다.", (
        C("RVW_TRGT_ID", "ID", True, "재검토대상ID"),
        C("LOAD_WORK_ID", "ID", True, "적재작업ID"),
        C("RVW_KIND_CD", "CODE", True, "재검토종류코드", "RULE / CITING_ARTICLE / LINKED_DOC"),
        C("SRC_LNG_ID", "ID", False, "원천계보ID", "바뀐 조문 계보"),
        C("TAGT_RGLT_DOC_CD", "ID", False, "대상규정문서코드"),
        C("TAGT_LNG_ID", "ID", False, "대상계보ID"),
        C("TAGT_ARTC_KEY_VALU", "ID", False, "대상조문키값"),
        C("RVW_RSN_CTNT", "TEXT", False, "재검토사유내용"),
        C("RVW_STTS_CD", "CODE", True, "재검토상태코드", "OPEN / DONE / DISMISSED"),
        C("PRCS_USER_ID", "ID", False, "처리사용자ID"),
        C("RGSN_ASTM", "TS", True, "등록일시"),
        C("PRCS_ASTM", "TS", False, "처리일시"),
    ), ("RVW_TRGT_ID",), (("RVW_STTS_CD",), ("LOAD_WORK_ID",))),
    Table("DOC_LINK", "문서연결관계", "위임 연결망(lsDelegated·lsStmd)과 외규↔내규 대응. 1단계 영향 전파용.", (
        C("RGLT_DOC_CD", "ID", True, "규정문서코드", "출발 문서"),
        C("TAGT_RGLT_DOC_CD", "ID", True, "대상규정문서코드"),
        C("LINK_KIND_CD", "CODE", True, "연결종류코드", "DELEGATE / STMD / INTERNAL_MAP"),
        C("LINK_SRC_HASH_VALU", "HASH", False, "연결원천해시값", "체계도·위임 응답 sha — 같으면 재전사 생략"),
        C("LINK_ADDN_IFMN_CTNT", "CLOB", False, "연결부가정보내용"),
        *TS_COLS), ("RGLT_DOC_CD", "TAGT_RGLT_DOC_CD", "LINK_KIND_CD")),
)

TABLE = {t.key: t for t in TABLES}

# 기존 Gold 13표에 이미 쓰인 약어 — 그 밖의 약어는 표준단어 확인·신청 후보
GOLD_WORDS = {"IDD", "B003", "LGL", "RGLT", "DOC", "VER", "ID", "NAME", "HASH", "VALU", "DTLS",
              "STRC", "UNIT", "UPPR", "BODY", "SLC", "CTNT", "ADDN", "IFMN", "RGSN", "ASTM", "SRC",
              "POST", "SRCH", "ROW", "CHNL", "CHAN", "NO", "RFRN", "DTA", "TYPE", "TAGT", "BLNG",
              "IDNF", "ONTL", "HEAD", "ANC", "VCTR", "ITEM", "SCTN", "EMBD", "CNCP", "GROP", "WORK",
              "KNWL", "LCT", "YN", "APPN", "UN"}


def new_words() -> list[str]:
    words: set[str] = set()
    for table in TABLES:
        words.update(table.key.split("_"))
        for column in table.columns:
            words.update(column.name.split("_"))
    return sorted(w for w in words if w not in GOLD_WORDS)


def qualified(table: Table, owner: str | None) -> str:
    return f"{owner}.{table.name}" if owner else table.name


def ddl(dialect: str, owner: str | None = None) -> list[str]:
    """CREATE TABLE·INDEX 문. Oracle은 PK 이름을 PK_<표>, 인덱스는 X<n>_<표>로 붙인다."""
    index_of = 1 if dialect == "sqlite" else 0
    out: list[str] = []
    for table in TABLES:
        name = qualified(table, owner)
        lines = []
        for column in table.columns:
            kind = DOMAINS[column.domain][index_of]
            lines.append(f"  {column.name} {kind}{' NOT NULL' if column.required else ''}")
        pk = ", ".join(table.primary_key)
        if dialect == "oracle":
            lines.append(f"  CONSTRAINT PK_{table.name} PRIMARY KEY ({pk})")
        else:
            lines.append(f"  PRIMARY KEY ({pk})")
        out.append(f"CREATE TABLE {name} (\n" + ",\n".join(lines) + "\n)")
        for n, columns in enumerate(table.indexes, 1):
            index = f"X{n}_{table.name}"
            target = f"{owner}.{index}" if owner and dialect == "oracle" else index
            out.append(f"CREATE INDEX {target} ON {name} ({', '.join(columns)})")
    return out


def oracle_comments(owner: str | None = None) -> list[str]:
    out = []
    for table in TABLES:
        name = qualified(table, owner)
        text = f"{table.logical}: {table.purpose}".replace("'", "''")
        out.append(f"COMMENT ON TABLE {name} IS '{text}'")
        for column in table.columns:
            note = f"{column.logical}" + (f" — {column.note}" if column.note else "")
            out.append(f"COMMENT ON COLUMN {name}.{column.name} IS '{note.replace(chr(39), chr(39) * 2)}'")
    return out


def definition_rows() -> list[dict]:
    """테이블 정의서 행 (메타 등록·DBA 생성 신청 양식 입력용)."""
    rows = []
    for table in TABLES:
        for seq, column in enumerate(table.columns, 1):
            pk = table.primary_key.index(column.name) + 1 if column.name in table.primary_key else ""
            rows.append({
                "테이블물리명": table.name, "테이블논리명": table.logical, "테이블설명": table.purpose,
                "컬럼순번": seq, "컬럼물리명": column.name, "컬럼논리명": column.logical,
                "데이터타입": DOMAINS[column.domain][0], "NULL허용": "N" if column.required else "Y",
                "PK순번": pk, "설명": column.note,
                "신규약어": ",".join(w for w in column.name.split("_") if w not in GOLD_WORDS),
            })
    return rows


def index_rows() -> list[dict]:
    rows = []
    for table in TABLES:
        rows.append({"테이블물리명": table.name, "인덱스명": f"PK_{table.name}", "구분": "PK",
                     "컬럼": ", ".join(table.primary_key)})
        for n, columns in enumerate(table.indexes, 1):
            rows.append({"테이블물리명": table.name, "인덱스명": f"X{n}_{table.name}", "구분": "NON-UNIQUE",
                         "컬럼": ", ".join(columns)})
    return rows
