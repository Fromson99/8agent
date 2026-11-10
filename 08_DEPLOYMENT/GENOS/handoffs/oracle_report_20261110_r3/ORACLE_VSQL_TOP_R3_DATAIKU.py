# Oracle 실행 통계(V$SQLSTATS) 상위 SQL — Dataiku Python 노트북용 (R3 사진 5)
#
# 사용: Dataiku에서 Python 노트북을 열고 이 파일 내용 전체를 한 셀에 붙여 넣어 실행.
#       아래 CONNECTION만 SQL 노트북에서 쓰는 Oracle 연결 이름으로 맞춘다.
#       느린 질문을 보낸 뒤 HOURS 시간 안에 실행해야 그 질문의 SQL이 남아 있다.
# 하는 일: SELECT만 보낸다(쓰기·변경 없음). 질문·답변·원문은 읽지 않고 SQL 첫 110자만 보여 준다.
# FAM 열 = GENOS 보고서(GENOS_ORACLE_REPORT_R3)의 SQL 해시(sha256 앞 12자). 4,000바이트 넘는 SQL 등은 '-'.

import dataiku

CONNECTION = 'AIDP'   # SQL 노트북에서 쓰는 Oracle 연결 이름
HOURS = 6             # 최근 몇 시간 안에 실행된 SQL을 볼지
TOP = 25              # 시간 많이 쓴 순 상위 몇 개를 보여 줄지

# 11-10 10:10 financial 요청 보고서(사진 1~4)에서 GENOS 쪽이 잰 평균. DB 쪽 평균과 비교한다.
WATCH = [
    ('d4b9ec9910e8', '원장 커밋+본문', 142),
    ('6f4d2267d3d6', '원장 본문 읽기', 57),
    ('c9260c333bac', '원장 상태 읽기', None),
    ('da6bb6937e51', '원장 잠금 획득', None),
    ('4a11ac4db480', 'DB 시각(원장 잠금)', None),
    ('dd56ac0e18de', '원장 용량 합계', None),
]

FAM = ("CASE WHEN DBMS_LOB.GETLENGTH(q.sql_fulltext) <= 1300 "
       "OR (DBMS_LOB.GETLENGTH(q.sql_fulltext) <= 4000 AND NOT REGEXP_LIKE(q.sql_fulltext, '[^' || CHR(1) || '-' || CHR(127) || ']')) "
       "THEN LOWER(SUBSTR(RAWTOHEX(STANDARD_HASH(DBMS_LOB.SUBSTR(q.sql_fulltext, 4000, 1), 'SHA256')), 1, 12)) END")
FULL_SCAN = ("(SELECT SUBSTR(LISTAGG(DISTINCT p.object_name, ',') WITHIN GROUP (ORDER BY p.object_name), 1, 60) "
             "FROM v$sql_plan p WHERE p.sql_id = q.sql_id AND p.plan_hash_value = q.plan_hash_value "
             "AND ((p.operation = 'TABLE ACCESS' AND p.options LIKE 'FULL%') OR (p.operation = 'INDEX' AND p.options = 'FAST FULL SCAN')))")


def build_sql(with_plan, with_fam):
    # 상위 TOP 밖의 주목 해시도 보이도록 200개까지 받아 파이썬에서 고른다. 끝에 ; 를 붙이지 않는다.
    return ("SELECT "
            + (FAM if with_fam else 'CAST(NULL AS VARCHAR2(12))') + " AS fam, q.sql_id, q.executions AS execs, "
            "ROUND(q.elapsed_time / 1e6, 1) AS total_s, "
            "ROUND(q.elapsed_time / GREATEST(q.executions, 1) / 1e3) AS avg_ms, "
            "ROUND(q.cpu_time / GREATEST(q.elapsed_time, 1) * 100) AS cpu_pct, "
            "ROUND(q.buffer_gets / GREATEST(q.executions, 1)) AS gets_per_exec, "
            "ROUND(q.disk_reads / GREATEST(q.executions, 1)) AS disk_per_exec, "
            "ROUND(q.rows_processed / GREATEST(q.executions, 1)) AS rows_per_exec, "
            + (FULL_SCAN if with_plan else 'CAST(NULL AS VARCHAR2(60))') + " AS full_scan, "
            "TO_CHAR(q.last_active_time, 'MM-DD HH24:MI') AS last_active, "
            "SUBSTR(REPLACE(REPLACE(q.sql_text, CHR(10), ' '), CHR(13), ' '), 1, 110) AS sql_start "
            "FROM v$sqlstats q "
            f"WHERE q.last_active_time >= SYSDATE - {int(HOURS)} / 24 AND q.executions > 0 "
            "AND UPPER(q.sql_text) LIKE '%LGL\\_%' ESCAPE '\\' AND UPPER(q.sql_text) NOT LIKE '%V$SQL%' "
            "ORDER BY q.elapsed_time DESC FETCH FIRST 200 ROWS ONLY")


def run():
    executor = dataiku.SQLExecutor2(connection=CONNECTION)
    errors = []
    # 권한이나 DB 기능 차이로 실패하면 열을 하나씩 빼고 다시 시도한다(모두 SELECT).
    for with_plan, with_fam, note in ((True, True, ''), (False, True, '실행 계획(V$SQL_PLAN) 열 생략'),
                                      (False, False, '실행 계획·FAM 열 생략')):
        try:
            df = executor.query_to_df(build_sql(with_plan, with_fam))
            df.columns = [str(c).lower() for c in df.columns]
            return df, note, errors
        except Exception as exc:
            errors.append(str(exc).splitlines()[0][:160] if str(exc) else type(exc).__name__)
    return None, '', errors


def num(value):
    try:
        return '-' if value is None or value != value else f'{int(round(float(value))):,}'
    except (TypeError, ValueError):
        return str(value)


def text(value, width):
    return ('-' if value is None or value != value else str(value))[:width]


def show(df, note):
    print(f'Oracle V$SQLSTATS 상위 SQL (R3 사진 5) · 연결 {CONNECTION} · 최근 {HOURS}시간 · LGL_ 표를 쓰는 SQL {len(df)}개')
    if note:
        print('  참고: ' + note)
    print(' 순 FAM          실행수   합계초  평균ms CPU%  읽은블록/회 행/회 전체훑기     마지막')
    for i, r in enumerate(df.head(TOP).itertuples(index=False), 1):
        print(f'{i:>3} {text(r.fam, 12):<12} {num(r.execs):>7} {text(r.total_s, 8):>8} {num(r.avg_ms):>7} {num(r.cpu_pct):>4} '
              f'{num(r.gets_per_exec):>11} {num(r.rows_per_exec):>5} {text(r.full_scan, 12):<12} {text(r.last_active, 11)}')
        print(f'      {text(r.sql_start, 92)}')
    print()
    print('주목 해시: DB 안 평균(이 표) vs GENOS 보고서 평균 — 차이가 크면 시간은 DB 밖(ORDS 전송·대기)에서 쓰인 것')
    for fam, label, field_ms in WATCH:
        rows = df[df['fam'] == fam]
        if rows.empty:
            print(f'  {fam} {label}: 최근 {HOURS}시간 상위 200개 안에 없음')
            continue
        execs = rows['execs'].sum(); total = rows['total_s'].sum()
        avg = total * 1000 / max(execs, 1)
        line = f'  {fam} {label}: 실행 {num(execs)}회 · DB 합계 {total:.1f}초 · DB 평균 {avg:.0f}ms'
        if field_ms:
            line += f' · 보고서 평균 {field_ms}ms → DB 밖 약 {max(field_ms - avg, 0):.0f}ms/회'
        print(line + f' (문장 {len(rows)}종)')


df, note, errors = run()
if df is None:
    print('조회 실패: ' + ' / '.join(errors))
    print('ORA-00942·ORA-01031이면 이 연결 계정에 V$SQLSTATS 조회 권한이 없는 것입니다.')
    print('DBA에게 요청: GRANT SELECT ON V_$SQLSTATS TO <계정>; GRANT SELECT ON V_$SQL_PLAN TO <계정>;'
          ' (또는 SELECT_CATALOG_ROLE)')
else:
    show(df, note)
    df   # 노트북에서 표로도 보기
