"""개발계 증분 준비 점검 SQL R1 — 읽기 전용(SELECT만). 소유자만 바꿔 같은 문장을 로컬에서 검증한다."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
P = 'RFRN_POST_IFMN_CTNT'
NAV = '$.metadata."navigation/manifest.json".value'
FT = '$.metadata."fulltext/manifest.json".value'


def _existing(key):
    """11-12 전달한 CHECK_TABLES_SIDDS_R1.txt의 권한 문장을 그대로 쓴다."""
    lines = (HERE.parent / 'pipeline_gold_owner_20261112_r1/CHECK_TABLES_SIDDS_R1.txt').read_text(encoding='utf-8').splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(f'-- [{key}]'))
    return lines[i + 1]


def statements(o):
    g = o + '.IDD_B003_LGL_'
    return [
        ('P01', '채널 — 지금 서빙이 보는 채널(main 또는 g19_…)과 세대 번호. 이 채널들은 손대지 않는다',
         f"SELECT RFRN_CHNL_NAME, RFRN_POST_HASH_VALU, CHAN_NO FROM {g}SRCH_CHNL ORDER BY RFRN_CHNL_NAME"),
        ('P02', '세대(조회 게시본)별 형식 — 합치기 조건: GEN_SCHEMA term-source-generation-v2, NAV_SCHEMA term-navigation-index-v7, SCOPE_CONTRACT N',
         f"SELECT RFRN_POST_HASH_VALU, JSON_VALUE({P},'$.projection') AS PROJECTION, "
         f"JSON_VALUE({P},'$.source_manifest.generation_id') AS GENERATION_ID, "
         f"JSON_VALUE({P},'$.source_manifest.schema_version') AS GEN_SCHEMA, "
         f"JSON_VALUE({P},'$.source_manifest.counts.document') AS DOCS, "
         f"CASE WHEN JSON_EXISTS({P},'$.source_manifest.append_lineage') THEN 'Y' ELSE 'N' END AS APPENDED, "
         f"CASE WHEN JSON_EXISTS({P},'$.search_selection.schema_version') THEN 'Y' ELSE 'N' END AS SEARCH_SELECTION, "
         f"JSON_VALUE({P},'{NAV}.schema_version') AS NAV_SCHEMA, "
         f"CASE WHEN JSON_EXISTS({P},'{NAV}.scope_contract') THEN 'Y' ELSE 'N' END AS SCOPE_CONTRACT, "
         f"JSON_VALUE({P},'{NAV}.legal_sha256') AS GLOSSARY_SHA, "
         f"JSON_VALUE({P},'{FT}.granularity') AS FT_GRANULARITY, "
         f"JSON_VALUE({P},'{FT}.tokenizer.name') AS TOKENIZER, "
         f"JSON_VALUE({P},'{FT}.tokenizer.version') AS TOKENIZER_VERSION, "
         f"DBMS_LOB.GETLENGTH({P}) AS MANIFEST_CHARS "
         f"FROM {g}SRCH_POST ORDER BY RFRN_POST_HASH_VALU"),
        ('P03', '세대별 검색 행 수 — 행이 많으면 수 분 걸림',
         f"SELECT RFRN_POST_HASH_VALU, COUNT(*) AS ROWS_N FROM {g}SRCH_ROW GROUP BY RFRN_POST_HASH_VALU ORDER BY RFRN_POST_HASH_VALU"),
        ('P04', '원문 세대별 문서 수',
         f"SELECT DTLS_HASH_VALU, COUNT(*) AS DOCS FROM {g}DOC_VER GROUP BY DTLS_HASH_VALU ORDER BY DTLS_HASH_VALU"),
        ('P05', '원문 게시본 — 언제 들어온 세대인지',
         f"SELECT BODY_POST_HASH_VALU, DTLS_HASH_VALU, RGSN_ASTM FROM {g}SRC_POST ORDER BY RGSN_ASTM"),
        ('P06', '벡터 — 세대마다 연결된 벡터 게시본과 벡터 수',
         f"SELECT h.RFRN_POST_HASH_VALU, h.VCTR_POST_ID, h.CHAN_NO, "
         f"(SELECT COUNT(*) FROM {g}VCTR_ITEM i WHERE i.VCTR_POST_ID=h.VCTR_POST_ID) AS VECTORS "
         f"FROM {g}VCTR_HEAD h ORDER BY h.RFRN_POST_HASH_VALU"),
        ('P07', '쓰고 있는 공간(MB) — 권한이 없어 ORA-00942가 나면 P07~P09는 DBA에게 요청',
         f"SELECT TABLESPACE_NAME, ROUND(SUM(BYTES)/1048576) AS USED_MB FROM DBA_SEGMENTS WHERE OWNER='{o}' GROUP BY TABLESPACE_NAME"),
        ('P08', '남은 공간(MB)',
         "SELECT TABLESPACE_NAME, ROUND(SUM(BYTES)/1048576) AS FREE_MB FROM DBA_FREE_SPACE GROUP BY TABLESPACE_NAME ORDER BY TABLESPACE_NAME"),
        ('P09', f'{o} 공간 한도(MAX_BYTES -1이면 무제한)',
         f"SELECT TABLESPACE_NAME, ROUND(BYTES/1048576) AS USED_MB, MAX_BYTES FROM DBA_TS_QUOTAS WHERE USERNAME='{o}'"),
        ('P10', '이 계정(PIDD2APP)이 Gold 13표·Agent 중간표에 직접 받은 권한 — 새 세대 적재에 SELECT·INSERT, 채널 교체에 UPDATE, 옛 세대 정리에 DELETE 필요',
         _existing('Q06').replace("'SIDDS'", f"'{o}'")),
        ('P11', '이 계정의 ANY 권한 (있으면 P10에 없어도 됨, ANALYZE ANY는 통계 갱신용)', _existing('Q07')),
    ]


def render(owner):
    lines = [f'-- 개발계 증분 준비 점검 R1 (2026-11-13) — 읽기 전용, 행·표를 바꾸지 않음. 소유자 {owner}.',
             '-- Dataiku SQL 노트북에서 [번호] 한 개씩 별도 Query로 실행 (문장 끝 세미콜론 없음, 버튼은 RUN).', '']
    for key, title, sql in statements(owner):
        lines += [f'-- [{key}] {title}', sql, '']
    return '\n'.join(lines)


if __name__ == '__main__':
    (HERE / 'DEV_INCREMENT_PREP_CHECK_R1.txt').write_text(render('SIDDS'), encoding='utf-8')
    print('written')
