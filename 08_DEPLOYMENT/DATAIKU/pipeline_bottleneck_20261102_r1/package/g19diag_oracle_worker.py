"""One bounded child: metadata/read probes and isolated INSERT+verify+ROLLBACK.

Never calls Contract.batch's committing SQL unchanged. A successful rollback
probe deliberately returns ORA-20084 with an unguessable timing marker.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
from g19diag_common import canonical, error, identifier, literal, read, write


def rollback_probe_sql(sql, nonce):
    # Accept only the exact generated transaction grammar, before data rendering.
    head = 'DECLARE n NUMBER; BEGIN '
    separator = '; SELECT COUNT(*) INTO n FROM '
    if not re.fullmatch('[a-f0-9]{32}', nonce) or not sql.startswith(head) or sql.count(separator) != 1 or sql.count('COMMIT;') != 1:
        raise ValueError('PROBE_SQL_SHAPE_UNSUPPORTED')
    if any(x in sql.upper() for x in ('EXECUTE IMMEDIATE', 'AUTONOMOUS_TRANSACTION', 'CREATE ', 'ALTER ', 'DELETE ', 'TRUNCATE ')):
        raise ValueError('PROBE_SQL_FORBIDDEN')
    sql = sql.replace(head, 'DECLARE n NUMBER; d0 NUMBER; d1 NUMBER; d2 NUMBER; d3 NUMBER; BEGIN d0:=DBMS_UTILITY.GET_TIME; ', 1)
    sql = sql.replace(separator, '; d1:=DBMS_UTILITY.GET_TIME; SELECT COUNT(*) INTO n FROM ', 1)
    marker = "RAISE_APPLICATION_ERROR(-20084,'G19_PROBE_OK_"+nonce+" i='||TO_CHAR(MOD(d1-d0+4294967296,4294967296),'FM9999999990')||' v='||TO_CHAR(MOD(d2-d1+4294967296,4294967296),'FM9999999990')||' r='||TO_CHAR(MOD(d3-d2+4294967296,4294967296),'FM9999999990'));"
    sql = sql.replace('COMMIT;', 'd2:=DBMS_UTILITY.GET_TIME; ROLLBACK; d3:=DBMS_UTILITY.GET_TIME; '+marker)
    if re.search(r'\bCOMMIT\b', sql): raise ValueError('PROBE_COMMIT_FORBIDDEN')
    return sql


def marker_times(exc, nonce):
    found = re.search(r'ORA-20084:\s*G19_PROBE_OK_'+re.escape(nonce)+r' i=(\d+) v=(\d+) r=(\d+)', str(exc))
    return dict(zip(('insert_db_seconds', 'verify_db_seconds', 'rollback_db_seconds'), (int(v)/100 for v in found.groups()))) if found else None


def cloned_rows(samples, key, contract, release, count):
    partition = contract.tables[key]['primary_key'][0]
    last = contract.tables[key]['primary_key'][-1]
    rows = []
    for n in range(count):
        row = dict(samples[n % len(samples)])
        row[partition] = release
        # Source coordinate maxima are 50 bytes; a 32-byte digest fits all probe PKs.
        row[last] = hashlib.sha256((release+':'+str(n)).encode()).hexdigest()[:32]
        rows.append(row)
    return rows


def run(config, output):
    ctx = config['context']; package = Path(ctx['package'])
    result = {'status': 'RUNNING', 'queries': [], 'insert_probes': [], 'active_query': None,
              'scope': 'isolated rollback probes, prefix sample bodies tiled; no full-run throughput forecast'}
    def save(): write(output, result)
    def active(name):
        result['active_query'] = {'name': name, 'started_epoch': time.time()}; save()
    import dataiku
    executor = dataiku.SQLExecutor2(connection='AIDP')
    def query(name, sql, limit=250, optional=False):
        active(name); start = time.perf_counter()
        try:
            frame = executor.query_to_df(sql, infer_from_schema=True, parse_dates=False)
            frame = frame.astype(object).where(frame.notna(), None)
            if len(frame) > limit: raise ValueError('QUERY_RESULT_LIMIT')
            rows = []
            for row in frame.to_dict(orient='records'):
                rows.append({str(k).upper(): v.item() if hasattr(v, 'item') else v for k, v in row.items()})
            result['queries'].append({'name': name, 'status': 'OK', 'seconds': time.perf_counter()-start, 'rows': len(rows)})
            return rows
        except Exception as exc:
            result['queries'].append({'name': name, 'status': 'FAILED', 'seconds': time.perf_counter()-start, 'error': error(exc)})
            if not optional: raise
            return None
        finally:
            result['active_query'] = None; save()
    try:
        with (Path(ctx['state_dir'])/'job.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = read(Path(ctx['state_dir'])/'state.json')
            if state['binding'] != ctx['state']['binding']: raise ValueError('JOB_CHANGED')
            sys.path.insert(0, str(package))
            import run as loader
            import jdbc_transport
            if loader.verify_code() != state['binding']['code']: raise ValueError('LOADER_CODE_CHANGED')
            contract = loader.Contract(package/'contract.json')
            identity = query('DB identity', "SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
            if identity != state['binding']['database']: raise ValueError('DB_IDENTITY_CHANGED')
            for n in range(3): query('roundtrip '+str(n+1), 'SELECT 1 AS OK FROM DUAL')
            conditions = ' OR '.join('(OWNER='+literal(t['owner'])+' AND TABLE_NAME='+literal(t['name'])+')' for t in contract.tables.values())
            result['table_stats'] = query('table stats (may be stale)', 'SELECT OWNER,TABLE_NAME,NUM_ROWS,AVG_ROW_LEN,BLOCKS,TO_CHAR(LAST_ANALYZED,\'YYYY-MM-DD HH24:MI:SS\') AS LAST_ANALYZED FROM ALL_TABLES WHERE '+conditions, optional=True)
            result['index_stats'] = query('index stats', 'SELECT OWNER,TABLE_NAME,INDEX_NAME,STATUS,UNIQUENESS,INDEX_TYPE,NUM_ROWS,LEAF_BLOCKS,BLEVEL FROM ALL_INDEXES WHERE '+conditions.replace('OWNER=', 'TABLE_OWNER='), optional=True)
            result['lob_metadata'] = query('LOB metadata', 'SELECT OWNER,TABLE_NAME,COLUMN_NAME,SECUREFILE,IN_ROW,CACHE,LOGGING,CHUNK FROM ALL_LOBS WHERE '+conditions, optional=True)
            result['sql_lifetime_stats'] = query('V$SQL cumulative, current login only', "SELECT * FROM (SELECT SQL_ID,EXECUTIONS,ELAPSED_TIME/1000000 AS ELAPSED_S,CPU_TIME/1000000 AS CPU_S,USER_IO_WAIT_TIME/1000000 AS IO_WAIT_S,BUFFER_GETS,DISK_READS,ROWS_PROCESSED FROM V$SQL WHERE PARSING_SCHEMA_NAME=SYS_CONTEXT('USERENV','SESSION_USER') AND (SQL_TEXT LIKE '%LGL_G19_%' OR SQL_TEXT LIKE '%LGL_AGT_%') ORDER BY ELAPSED_TIME DESC) WHERE ROWNUM<=8", limit=8, optional=True)
            if not config.get('insert_probes'):
                result['status'] = 'READONLY_COMPLETE'; save(); return
            # Preserve normal column/type/PK/trigger checks, but no create/probe/reset method.
            class ReadDB:
                def query(self, sql, limit=200): return query('target preflight', sql, limit)
            database = ReadDB()
            if loader.object_binding(database, contract) != state['binding']['objects']:
                raise ValueError('DB_OBJECTS_CHANGED')
            targets = [('DOC_VER', None), ('DOC_UNIT', None), ('DOC_BLK', None)]
            kinds = sorted(ctx['descriptor']['tables'].items(), key=lambda kv: -kv[1]['rows'])
            # Small indexed probes only; uninserted kinds return empty without full COUNT.
            targets += [('SRCH_ROW', kind) for kind, spec in kinds[:5]]
            first = query('one loaded search kind', 'SELECT '+contract.col('SRCH_ROW', 'RFRN_DTA_TYPE_VALU')+' AS KIND FROM '+contract.table('SRCH_ROW')+' WHERE '+contract.col('SRCH_ROW', 'RFRN_POST_HASH_VALU')+'='+literal(state['binding']['query_release'])+' AND ROWNUM<=1', limit=1)
            if first and ('SRCH_ROW', first[0]['KIND']) not in targets:
                targets.append(('SRCH_ROW', first[0]['KIND']))
            preflighted = set(); started_all = time.monotonic()
            for key, kind in targets:
                if time.monotonic()-started_all > 120:
                    result['insert_probes'].append({'table': key, 'kind': kind, 'status': 'BUDGET_UNMEASURED'}); continue
                if key not in preflighted:
                    contract.preflight(database, key); preflighted.add(key)
                t = contract.tables[key]; partition = t['primary_key'][0]
                original_release = state['binding']['query_release'] if key == 'SRCH_ROW' else state['binding']['files']['manifest.json']
                names = [n for n,c in t['columns'].items() if not c['default']]
                columns = ','.join(contract.col(key, n)+' AS '+identifier(n) for n in names)
                where = contract.col(key, partition)+'='+literal(original_release)
                if kind: where += ' AND '+contract.col(key, 'RFRN_DTA_TYPE_VALU')+'='+literal(kind)
                rows = query('bounded payload prefix '+key, 'SELECT '+columns+' FROM '+contract.table(key)+' WHERE '+where+' AND ROWNUM<=32', limit=32)
                # Raw sample values remain only in this child's memory, never in the report.
                if not rows:
                    result['insert_probes'].append({'table': key, 'kind': kind, 'status': 'NO_LOADED_SAMPLE'}); save(); continue
                for row in rows:
                    for n,v in row.items():
                        if hasattr(v, 'read'): row[n] = v.read()
                if any(len(canonical(row).encode()) > 1024**2 for row in rows):
                    result['insert_probes'].append({'table': key, 'kind': kind, 'status': 'SAMPLE_TOO_LARGE'}); save(); continue
                for requested in (100, 500, 2000):
                    if time.monotonic()-started_all > 120: break
                    nonce = uuid.uuid4().hex; release = hashlib.sha256(('diagnostic:'+nonce).encode()).hexdigest()
                    record = {'table': key, 'kind': kind, 'requested_rows': requested, 'probe_release': release,
                              'sample_rows': len(rows), 'status': 'PREPARING', 'scope': 'sample bodies tiled; isolated keys; rollback; not committed throughput'}
                    result['insert_probes'].append(record); save()
                    if query('probe namespace empty', 'SELECT COUNT(*) AS N FROM '+contract.table(key)+' WHERE '+contract.col(key, partition)+'='+literal(release)) != [{'N':0}]:
                        raise ValueError('PROBE_NAMESPACE_EXISTS')
                    count = requested; prep = time.perf_counter()
                    while True:
                        values = cloned_rows(rows, key, contract, release, count)
                        sql, binds = contract.batch(key, values)
                        payload_bytes = len(binds[0][1].encode())
                        if payload_bytes <= 2*1024**2: break
                        if count == 1: raise ValueError('PROBE_PAYLOAD_LIMIT')
                        count = max(1, min(count-1, int(count*2*1024**2/payload_bytes*.95)))
                    record.update(rows=count, payload_bytes=payload_bytes, prepare_seconds=time.perf_counter()-prep)
                    sql = rollback_probe_sql(sql, nonce)
                    prep = time.perf_counter(); rendered = jdbc_transport.render(sql, binds, write=True)
                    record.update(render_seconds=time.perf_counter()-prep, sql_bytes=len(rendered.encode()), status='IN_FLIGHT')
                    active('INSERT rollback '+key+' '+str(count)); start = time.perf_counter()
                    try:
                        executor.query_to_df('SELECT 1 AS OK FROM DUAL', pre_queries=[rendered], post_queries=['ROLLBACK'])
                    except Exception as exc:
                        measured = marker_times(exc, nonce)
                        if measured is None:
                            record.update(status='FAILED_OR_OUTCOME_UNKNOWN', error=error(exc)); raise
                        record.update(measured)
                    else:
                        raise ValueError('PROBE_TIMING_RECEIPT_MISSING')
                    finally:
                        record['request_seconds'] = time.perf_counter()-start
                        result['active_query'] = None; save()
                    remaining = query('probe rollback empty', 'SELECT COUNT(*) AS N FROM '+contract.table(key)+' WHERE '+contract.col(key, partition)+'='+literal(release))
                    if remaining != [{'N':0}]:
                        record['status'] = 'ROLLBACK_NOT_CONFIRMED'; raise ValueError('PROBE_ROWS_REMAIN_NO_AUTO_DELETE')
                    record.update(status='ROLLED_BACK_VERIFIED', rollback_remaining_rows=0,
                                  request_outside_measured_db_seconds=max(0, record['request_seconds']-sum(measured.values())))
                    save()
            result['status'] = 'COMPLETE'
    except Exception as exc:
        result['status'] = 'STOPPED'; result['error'] = error(exc)
    finally:
        result['active_query'] = None; save()


if __name__ == '__main__':
    run(read(sys.argv[1]), Path(sys.argv[2]))
