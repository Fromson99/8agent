"""Dataiku AIDP: SELECT-only capacity check; never rerun the R3 probes."""
import csv
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import re
import time
import uuid

CONNECTION = 'AIDP'
REPORT_PATH = ''  # Optional exact R3 REPORT.json path; no newest-file auto-selection.
TARGETS = [('SIDDS', 'LGL_G19_DOC_VER_S_1'), ('SIDDS', 'LGL_G19_DOC_UNIT_S_1'), ('SIDDS', 'LGL_G19_DOC_BLK_S_1'), ('SIDDS', 'LGL_G19_SRC_POST_S_1'), ('SIDDS', 'LGL_G19_SRCH_POST_S_1'), ('SIDDS', 'LGL_G19_SRCH_ROW_S_1'), ('SIDDS', 'LGL_G19_SRCH_CHNL_S_1'), ('SIDDA', 'LGL_G19_ONTL_POST_A_1'), ('SIDDA', 'LGL_G19_ONTL_HEAD_A_1'), ('SIDDA', 'LGL_G19_ONTL_ANC_A_1'), ('SIDDS', 'LGL_G19_VCTR_POST_S_1'), ('SIDDS', 'LGL_G19_VCTR_ITEM_S_1'), ('SIDDS', 'LGL_G19_VCTR_HEAD_S_1'), ('SIDDA', 'LGL_AGT_RUN_A_1'), ('SIDDA', 'LGL_AGT_REC_A_1'), ('SIDDA', 'LGL_AGT_BODY_A_1'), ('SIDDA', 'LGL_EXEC_ST_A_1')]


def target_cte():
    return 'wanted AS (' + ' UNION ALL '.join(
        "SELECT '%s' AS OWNER,'%s' AS TABLE_NAME FROM DUAL" % (owner, name)
        for owner, name in TARGETS) + ')'


TARGET_CTE = target_cte()
TABLE_CTE = TARGET_CTE + ''', targets AS (
SELECT t.* FROM ALL_TABLES t JOIN wanted w
ON t.OWNER=w.OWNER AND t.TABLE_NAME=w.TABLE_NAME)'''
MAPPED_CTE = TABLE_CTE + ''', regular AS (
SELECT * FROM targets WHERE PARTITIONED='NO' AND IOT_TYPE IS NULL AND CLUSTER_NAME IS NULL),
mapped AS (
SELECT OWNER AS TABLE_OWNER,TABLE_NAME,OWNER AS SEGMENT_OWNER,TABLE_NAME AS SEGMENT_NAME FROM regular
UNION SELECT i.TABLE_OWNER,i.TABLE_NAME,i.OWNER,i.INDEX_NAME FROM ALL_INDEXES i JOIN regular t
ON i.TABLE_OWNER=t.OWNER AND i.TABLE_NAME=t.TABLE_NAME WHERE i.PARTITIONED='NO'
UNION SELECT l.OWNER,l.TABLE_NAME,l.OWNER,l.SEGMENT_NAME FROM ALL_LOBS l JOIN regular t
ON l.OWNER=t.OWNER AND l.TABLE_NAME=t.TABLE_NAME
UNION SELECT l.OWNER,l.TABLE_NAME,l.OWNER,l.INDEX_NAME FROM ALL_LOBS l JOIN regular t
ON l.OWNER=t.OWNER AND l.TABLE_NAME=t.TABLE_NAME)'''
TS_CTE = TABLE_CTE + ''', target_ts AS (
SELECT OWNER,TABLESPACE_NAME FROM targets WHERE TABLESPACE_NAME IS NOT NULL
UNION SELECT i.TABLE_OWNER,i.TABLESPACE_NAME FROM ALL_INDEXES i JOIN targets t
ON i.TABLE_OWNER=t.OWNER AND i.TABLE_NAME=t.TABLE_NAME WHERE i.TABLESPACE_NAME IS NOT NULL
UNION SELECT l.OWNER,l.TABLESPACE_NAME FROM ALL_LOBS l JOIN targets t
ON l.OWNER=t.OWNER AND l.TABLE_NAME=t.TABLE_NAME WHERE l.TABLESPACE_NAME IS NOT NULL)'''

SQL = {
    'identity': "SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS CURRENT_SCHEMA, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL",
    'tables': 'WITH ' + TARGET_CTE + ''' SELECT w.OWNER,w.TABLE_NAME,t.TABLESPACE_NAME,
t.NUM_ROWS AS STATS_ROWS,t.AVG_ROW_LEN,t.BLOCKS,t.PARTITIONED,t.IOT_TYPE,t.CLUSTER_NAME,
t.SEGMENT_CREATED,TO_CHAR(t.LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS STATS_AT,
CASE WHEN t.TABLE_NAME IS NULL THEN 'NOT_VISIBLE_OR_ABSENT' ELSE 'VISIBLE' END AS VISIBILITY
FROM wanted w LEFT JOIN ALL_TABLES t ON t.OWNER=w.OWNER AND t.TABLE_NAME=w.TABLE_NAME
ORDER BY w.OWNER,w.TABLE_NAME''',
    'segments': 'WITH ' + MAPPED_CTE + ''' SELECT m.TABLE_OWNER AS OWNER,m.TABLE_NAME,
s.TABLESPACE_NAME,s.SEGMENT_TYPE,SUM(s.BYTES) AS ALLOCATED_BYTES
FROM mapped m JOIN DBA_SEGMENTS s ON s.OWNER=m.SEGMENT_OWNER AND s.SEGMENT_NAME=m.SEGMENT_NAME
GROUP BY m.TABLE_OWNER,m.TABLE_NAME,s.TABLESPACE_NAME,s.SEGMENT_TYPE
ORDER BY m.TABLE_OWNER,m.TABLE_NAME,s.TABLESPACE_NAME,s.SEGMENT_TYPE''',
    'quota': 'WITH ' + TS_CTE + ''' SELECT x.OWNER,x.TABLESPACE_NAME,q.BYTES AS CHARGED_BYTES,
q.MAX_BYTES AS QUOTA_BYTES,CASE WHEN q.USERNAME IS NULL THEN 'NO_QUOTA_ROW_NOT_CONCLUSIVE'
WHEN q.MAX_BYTES=-1 THEN 'REGISTERED_UNLIMITED' ELSE 'REGISTERED_LIMIT' END AS QUOTA_STATE
FROM target_ts x LEFT JOIN DBA_TS_QUOTAS q ON q.USERNAME=x.OWNER AND q.TABLESPACE_NAME=x.TABLESPACE_NAME
ORDER BY x.OWNER,x.TABLESPACE_NAME''',
    'space': 'WITH ' + TS_CTE + ''', names AS (SELECT DISTINCT TABLESPACE_NAME FROM target_ts),
files AS (SELECT d.TABLESPACE_NAME,SUM(d.BYTES) AS FILE_BYTES,
SUM(CASE WHEN d.AUTOEXTENSIBLE='YES' THEN GREATEST(d.MAXBYTES-d.BYTES,0) ELSE 0 END) AS AUTO_GROW_BYTES,
SUM(CASE WHEN d.ONLINE_STATUS<>'ONLINE' THEN 1 ELSE 0 END) AS NOT_ONLINE_FILES
FROM DBA_DATA_FILES d JOIN names n ON n.TABLESPACE_NAME=d.TABLESPACE_NAME GROUP BY d.TABLESPACE_NAME),
free AS (SELECT f.TABLESPACE_NAME,SUM(f.BYTES) AS FREE_BYTES,MAX(f.BYTES) AS MAX_FREE_EXTENT_BYTES
FROM DBA_FREE_SPACE f JOIN names n ON n.TABLESPACE_NAME=f.TABLESPACE_NAME GROUP BY f.TABLESPACE_NAME)
SELECT n.TABLESPACE_NAME,d.FILE_BYTES,d.AUTO_GROW_BYTES,d.NOT_ONLINE_FILES,
f.FREE_BYTES,f.MAX_FREE_EXTENT_BYTES FROM names n LEFT JOIN files d ON d.TABLESPACE_NAME=n.TABLESPACE_NAME
LEFT JOIN free f ON f.TABLESPACE_NAME=n.TABLESPACE_NAME ORDER BY n.TABLESPACE_NAME''',
    'visible_free': 'WITH ' + TS_CTE + ''' SELECT f.TABLESPACE_NAME,SUM(f.BYTES) AS VISIBLE_FREE_BYTES,
MAX(f.BYTES) AS MAX_VISIBLE_EXTENT_BYTES FROM USER_FREE_SPACE f
JOIN (SELECT DISTINCT TABLESPACE_NAME FROM target_ts) n ON n.TABLESPACE_NAME=f.TABLESPACE_NAME
GROUP BY f.TABLESPACE_NAME ORDER BY f.TABLESPACE_NAME''',
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def source_reference(report):
    """Past source JSON sizes, explicitly partial and unrelated to physical allocation."""
    samples = {}
    for s in report.get('samples', []):
        key = (s.get('asset'), s.get('table'))
        samples.setdefault(key, []).append(s)
    rows = []
    for item in report.get('items', []):
        count = item.get('rows')
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError('INVALID_PLANNED_ROWS')
        values = samples.get((item.get('asset'), item.get('table')), [])
        s = values[0] if len(values) == 1 else {}
        mean = s.get('prefix_mean_json_bytes')
        usable = (bool(item.get('table')) and s.get('status') == 'OK'
                  and finite(mean) and s.get('sample_rows', 0) > 0
                  and s.get('binary_bytes_not_serialized') == 0)
        rows.append({'kind': item['kind'], 'planned_rows': count,
                     'sample_rows': s.get('sample_rows') if usable else None,
                     'source_json_mean_bytes': mean if usable else None,
                     'source_json_extrapolated_bytes': count * mean if usable else None,
                     'status': 'PREFIX_SOURCE_JSON_ONLY' if usable else 'UNMEASURED',
                     'candidate_only_not_excluded': bool(item.get('candidate'))})
    return {'kind_count': len(rows), 'planned_rows': sum(r['planned_rows'] for r in rows),
            'covered_rows': sum(r['planned_rows'] for r in rows if r['status'] != 'UNMEASURED'),
            'partial_source_json_bytes': sum(r['source_json_extrapolated_bytes'] or 0 for r in rows)
                if any(r['status'] != 'UNMEASURED' for r in rows) else None,
            'final_oracle_bytes': None, 'rows': rows,
            'binding': report.get('binding', {}), 'original_loader_status': report.get('loader_status')}


def table_sizes(tables, segments):
    result = []
    for t in tables:
        row = dict(t)
        hits = [s for s in segments or [] if (s['OWNER'], s['TABLE_NAME']) == (t['OWNER'], t['TABLE_NAME'])]
        if t['VISIBILITY'] != 'VISIBLE': state = 'NOT_VISIBLE_OR_ABSENT'
        elif t.get('PARTITIONED') != 'NO' or t.get('IOT_TYPE') or t.get('CLUSTER_NAME'): state = 'SPECIAL_LAYOUT_UNMEASURED'
        elif segments is None: state = 'NO_SEGMENT_QUERY_PRIVILEGE_OR_ERROR'
        elif not hits: state = 'NO_SEGMENT_INFO'
        else: state = 'MEASURED_ALLOCATION'
        row['SIZE_STATE'] = state
        row['ALLOCATED_BYTES'] = sum(s['ALLOCATED_BYTES'] for s in hits) if state == 'MEASURED_ALLOCATION' else None
        result.append(row)
    return result


def load_report(observer=None, path=''):
    if path:
        p = Path(path).expanduser().resolve(strict=True)
        if p.stat().st_size > 16*1024**2: raise ValueError('REPORT_SIZE_LIMIT')
        return json.loads(p.read_text(encoding='utf-8')), str(p)
    if observer is not None and isinstance(getattr(observer, 'REPORT', None), dict):
        return json.loads(json.dumps(observer.REPORT)), str(getattr(observer, 'OUTPUT', ''))
    return {}, 'NO_R3_REPORT_SELECTED'


def run(query, report, output):
    result = {'started_at': datetime.now(timezone.utc).isoformat(), 'queries': {},
              'source_reference': source_reference(report), 'targets': TARGETS,
              'final_oracle_bytes': None, 'notes': ['R3 source samples are historical nonrandom prefixes.',
                  'No final physical capacity forecast. No INSERT/DDL/COUNT or source scan.']}
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    def save():
        (output/'CAPACITY_REPORT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        for name, sql in SQL.items():
            if name == 'visible_free' and result['queries'].get('space', {}).get('status') == 'OK':
                continue
            print('용량 조회: ' + name + ' — SELECT만 실행', flush=True)
            started = time.monotonic()
            try:
                rows = query(sql)
                if len(rows) > 2000: raise ValueError('METADATA_ROW_LIMIT')
                result['queries'][name] = {'status': 'OK', 'rows': rows, 'seconds': time.monotonic()-started}
            except Exception as exc:
                result['queries'][name] = {'status': 'UNAVAILABLE', 'error_type': type(exc).__name__,
                    'oracle_codes': sorted(set(re.findall(r'(?:ORA|PLS)-\d{5}', str(exc)))),
                    'seconds': time.monotonic()-started}
            save()
            if name == 'identity' and result['queries'][name]['status'] != 'OK': break
    except KeyboardInterrupt:
        result['interrupted'] = True
        result['interruption_note'] = 'Client interrupted; remote SELECT cancellation not certified. No retry.'
    finally:
        q = result['queries']
        result['tables'] = table_sizes(q.get('tables', {}).get('rows', []), q.get('segments', {}).get('rows'))
        save()
        if result['tables']:
            with (output/'TABLE_CAPACITY.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(result['tables'][0]))
                writer.writeheader(); writer.writerows(result['tables'])
    return result


def gib(value):
    return '미확인' if value is None else ('등록 무제한' if value == -1 else f'{value/1024**3:,.3f}')


def show(result, output, page='요약'):
    q = result['queries']; source = result['source_reference']
    rows = []; note = ''
    if page == '테이블':
        rows = [['표', '할당 GiB', '측정 상태', '통계 행 수(과거)', '통계 시각']]
        rows += [[t['OWNER']+'.'+t['TABLE_NAME'], gib(t['ALLOCATED_BYTES']), t['SIZE_STATE'],
                  t.get('STATS_ROWS'), t.get('STATS_AT')] for t in result['tables']]
        note = '현재 _1 표만. 본체+인덱스+LOB 할당량. 통계 행 수는 현재 적재량이 아니며 용량으로 환산하지 않습니다.'
    elif page == '한도':
        rows = [['소유자', '테이블스페이스', '계정 할당 GiB', '등록 한도 GiB', '상태']]
        rows += [[r['OWNER'], r['TABLESPACE_NAME'], gib(r['CHARGED_BYTES']), gib(r['QUOTA_BYTES']), r['QUOTA_STATE']]
                 for r in q.get('quota', {}).get('rows', [])]
        note = '계정 할당은 해당 공간의 기존 표도 포함. quota 행 없음은 0/무제한의 증거가 아닙니다. UNLIMITED TABLESPACE 권한은 별도 확인.'
    elif page == '여유':
        rows = [['테이블스페이스', '파일 GiB', '미할당 GiB', '자동확장 설정 여유 GiB', '비온라인 파일']]
        rows += [[r['TABLESPACE_NAME'], gib(r['FILE_BYTES']), gib(r['FREE_BYTES']), gib(r['AUTO_GROW_BYTES']), r['NOT_ONLINE_FILES']]
                 for r in q.get('space', {}).get('rows', [])]
        if 'visible_free' in q:
            rows += [['권한 제한 보조 조회', '현재 계정에서 보이는 여유', '', '', '']]
            rows += [[r['TABLESPACE_NAME'], '', gib(r['VISIBLE_FREE_BYTES']), '', '부분 가시성']
                     for r in q['visible_free'].get('rows', [])]
        note = '공유 공간이며 독점 가용량이 아닙니다. 자동확장 설정은 실제 디스크 여유/성공 보장이 아닙니다. 미표시/NULL은 0으로 확정하지 않습니다.'
    elif page == '자료':
        rows = [['자료(상위 12)', '계획 행 수', '앞쪽 표본 행 수', '표본 평균 JSON bytes', '측정 상태']]
        rows += [[r['kind'], r['planned_rows'], r['sample_rows'], r['source_json_mean_bytes'], r['status']]
                 for r in source['rows'][:12]]
        note = 'R3의 과거 SQLite 앞쪽 표본. 전체 평균/Oracle 저장 형태가 아닙니다. 원문/벡터/인덱스/블록 여유 포함 최종 용량은 미산정. 제외 검토 행도 그대로 포함합니다.'
    else:
        rows = [['확인 항목', '결과']]
        rows += [['접속', str(q.get('identity', {}).get('rows', []))],
                 ['현재 _1 표', f"{sum(t['SIZE_STATE']=='MEASURED_ALLOCATION' for t in result['tables'])}/{len(TARGETS)}개 용량 확인"],
                 ['최종 전체 필요 용량', '미산정 — 현장 저장량과 종류별 대표 표본/벡터 예정량 필요'],
                 ['R3 검색 계획 / 표본이 있는 계획 행', f"{source['planned_rows']:,} / {source['covered_rows']:,}"],
                 ['원래 적재 상태(R3 기록)', source['original_loader_status'] or '미확인']]
        rows += [[name, value['status']+' '+','.join(value.get('oracle_codes', []))] for name, value in q.items()]
        note = 'SHOW_CAPACITY_PAGE("테이블"/"한도"/"여유"/"자료")로 저장 결과만 표시. 조회 실패는 용량 0이 아닙니다. 접속자와 SIDDS/SIDDA 소유자를 구분합니다.'
    unavailable = [name+': '+','.join(v.get('oracle_codes', [])) for name,v in q.items() if v['status'] != 'OK']
    esc = lambda v: html.escape('미확인' if v is None else str(v))
    content = '<div style="max-width:1050px;background:white;color:#243a50;padding:14px;border:1px solid #b9c8d6;font:14px Arial"><b>Oracle 용량 확인 · '+esc(page)+'</b><table style="width:100%;margin:10px 0;border-collapse:collapse">'
    content += ''.join('<tr>'+''.join('<td style="border-bottom:1px solid #ddd;padding:6px">'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)
    content += '</table><p>'+esc(note)+'</p><p>조회 불가: '+esc('; '.join(unavailable) or '없음')+'</p><p>전체 결과: '+esc(output)+'/CAPACITY_REPORT.json</p></div>'
    from IPython.display import HTML, clear_output, display
    clear_output(wait=True); display(HTML(content))


def notebook_main(observer=None):
    import dataiku
    prior, origin = load_report(observer, REPORT_PATH)
    executor = dataiku.SQLExecutor2(connection=CONNECTION)
    def query(sql):
        frame = executor.query_to_df(sql, infer_from_schema=True, parse_dates=False)
        frame = frame.astype(object).where(frame.notna(), None)
        return [{str(k).upper(): v.item() if hasattr(v, 'item') else v for k,v in row.items()}
                for row in frame.to_dict(orient='records')]
    output = Path.cwd()/'gold-capacity-reports'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    result = run(query, prior, output)
    result['r3_report_origin'] = origin
    (output/'CAPACITY_REPORT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    show(result, output)
    return result, output
