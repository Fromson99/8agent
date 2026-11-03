"""Pure comparison plans and rollback-only SQL, retaining installed checks."""
import hashlib
import re
import statistics
from g19cmp_common import canonical

KINDS = ('entry_corpus_link', 'occurrence_keys', 'unit_fts_posting', 'unit')
POLICIES = {'baseline': (5000, 2*1024**2), 'large': (10000, 4*1024**2)}
MAX_PAYLOAD = 8*1024**2


def row_hash(rows):
    h = hashlib.sha256()
    for row in rows:
        h.update(canonical(row).encode()); h.update(b'\n')
    return h.hexdigest()


def partitions(weights, max_rows, max_bytes):
    start, size = 0, 0
    spans = []
    for i, weight in enumerate(weights):
        if type(weight) is not int or weight <= 0: raise ValueError('INVALID_PROJECTION_WEIGHT')
        if i > start and (i-start >= max_rows or size+weight > max_bytes):
            spans.append((start,i)); start, size = i, 0
        size += weight
    if len(weights) > start: spans.append((start,len(weights)))
    return spans


def pair_order(pair, kind_index, left, right):
    return (left,right) if (pair+kind_index)%2 == 0 else (right,left)


def expanded_contract(base_class, path):
    class DiagnosticContract(base_class):
        def validate(self, key, rows):
            if not rows or len(rows)>10000: raise ValueError('DIAGNOSTIC_ROW_LIMIT')
            seen = set()
            for start in range(0,len(rows),5000):
                super().validate(key,rows[start:start+5000])
            for row in rows:
                pk = tuple(row[n] for n in self.tables[key]['primary_key'])
                if pk in seen: raise ValueError('DIAGNOSTIC_DUPLICATE_PK_ACROSS_CHUNKS')
                seen.add(pk)
            return rows
    return DiagnosticContract(path)


def checked_sql(sql, verify_only=False):
    expected = 0 if verify_only else 1
    if (not sql.startswith('DECLARE n NUMBER; BEGIN ')
            or sql.count('COMMIT;')!=expected
            or sql.count('SELECT COUNT(*) INTO n FROM ')!=1
            or "RAISE_APPLICATION_ERROR(-20042,'GOLD_ROW_CONFLICT_OR_MISSING')" not in sql
            or not sql.endswith('EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')):
        raise ValueError('INSTALLED_SQL_GRAMMAR_UNSUPPORTED')
    if re.search(r'\b(EXECUTE\s+IMMEDIATE|AUTONOMOUS_TRANSACTION|CREATE|ALTER|DELETE|TRUNCATE|UPDATE)\b',sql,re.I):
        raise ValueError('UNEXPECTED_SQL_OPERATION')
    return sql


def response_sql(sql, nonce, mode):
    checked_sql(sql)
    if not re.fullmatch('[a-f0-9]{32}',nonce) or mode not in ('normal','exception'):
        raise ValueError('RESPONSE_PROBE_ARGUMENT')
    sql=sql.replace('DECLARE n NUMBER; BEGIN ',
        'DECLARE n NUMBER; d0 NUMBER; d1 NUMBER; d2 NUMBER; d3 NUMBER; BEGIN d0:=DBMS_UTILITY.GET_TIME; ',1)
    sql=sql.replace('; SELECT COUNT(*) INTO n FROM ',
        '; d1:=DBMS_UTILITY.GET_TIME; SELECT COUNT(*) INTO n FROM ',1)
    marker="RAISE_APPLICATION_ERROR(-20084,'G19CMP_OK_"+nonce+" i='||TO_CHAR(MOD(d1-d0+4294967296,4294967296),'FM9999999990')||' v='||TO_CHAR(MOD(d2-d1+4294967296,4294967296),'FM9999999990')||' r='||TO_CHAR(MOD(d3-d2+4294967296,4294967296),'FM9999999990')||' p='||TO_CHAR(MOD(d0-g19_transport_t0+4294967296,4294967296),'FM9999999990'));"
    condition = '1' if mode=='exception' else '0'
    sql=sql.replace('COMMIT;', 'd2:=DBMS_UTILITY.GET_TIME; ROLLBACK; d3:=DBMS_UTILITY.GET_TIME; IF '+condition+' = 1 THEN '+marker+' END IF;')
    if re.search(r'\bCOMMIT\b',sql): raise ValueError('COMMIT_FORBIDDEN')
    return sql


def payload_clock(rendered):
    if not rendered.startswith('DECLARE\n') or '\nBEGIN\n' not in rendered:
        raise ValueError('INSTALLED_TRANSPORT_GRAMMAR_UNSUPPORTED')
    return rendered.replace('DECLARE\n','DECLARE\ng19_transport_t0 NUMBER;\n',1).replace(
        '\nBEGIN\n','\nBEGIN\ng19_transport_t0:=DBMS_UTILITY.GET_TIME;\n',1)


def receipt(exc, nonce):
    codes=set(re.findall(r'ORA-\d{5}',str(exc)))
    if codes-{'ORA-20084','ORA-06512'}: return None
    m=re.search(r'ORA-20084:\s*G19CMP_OK_'+re.escape(nonce)+r' i=(\d+) v=(\d+) r=(\d+) p=(\d+)',str(exc))
    return dict(zip(('insert_db_s','verify_db_s','rollback_db_s','payload_db_s'),(int(x)/100 for x in m.groups()))) if m else None


def isolated_rows(rows, contract, release):
    partition=contract.tables['SRCH_ROW']['primary_key'][0]
    # Only the isolated release changes. Original row IDs, kind, scalar/CLOB values stay exact.
    return [dict(row, **{partition:release}) for row in rows]


def noncommitting(sql, binds, suffix, verify_only=False):
    checked_sql(sql,verify_only)
    value=sql if verify_only else sql.replace('COMMIT;','NULL;')
    for name,_,_ in binds: value=re.sub(':'+re.escape(name)+r'\b',':'+name+suffix,value)
    if re.search(r'\bCOMMIT\b',value): raise ValueError('COMMIT_FORBIDDEN')
    return value,[(n+suffix,v,t) for n,v,t in binds]


def integrity_sql(contract, rows, mode):
    if len(rows)<4: raise ValueError('FOUR_SOURCE_ROWS_REQUIRED')
    seeded=rows[:3]
    first, bind1=noncommitting(*contract.batch('SRCH_ROW',seeded),'_a')
    if mode=='same_rows':
        second,bind2=noncommitting(*contract.batch('SRCH_ROW',seeded),'_b')
        return 'BEGIN '+first+' '+second+' ROLLBACK; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;',bind1+bind2
    if mode=='conflict':
        column=next(n for n,c in contract.tables['SRCH_ROW']['columns'].items() if c['type']=='CLOB' and not c['default'])
        altered=[dict(r) for r in seeded]
        altered[0][column]=(altered[0].get(column) or '')+'\nG19_COMPARISON_CONFLICT'
        second,bind2=noncommitting(*contract.batch('SRCH_ROW',altered),'_b')
    elif mode=='missing':
        second,bind2=noncommitting(*contract.batch('SRCH_ROW',rows[:4],verify_only=True),'_b',verify_only=True)
    else: raise ValueError('INTEGRITY_MODE')
    sql=('DECLARE caught NUMBER:=0; BEGIN '+first+' BEGIN '+second+
         ' EXCEPTION WHEN OTHERS THEN IF SQLCODE=-20042 THEN caught:=1; ELSE RAISE; END IF; END; '
         "IF caught<>1 THEN ROLLBACK; RAISE_APPLICATION_ERROR(-20086,'EXPECTED_CONFLICT_OR_MISSING_NOT_REJECTED'); END IF; "
         'ROLLBACK; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
    return sql,bind1+bind2


def summaries(trials):
    result=[]
    for phase,left,right in (('response','normal','exception'),('batch','baseline','large')):
        kinds=sorted({t['kind'] for t in trials if t.get('phase')==phase})
        for kind in kinds:
            ratios=[]; pairs=[]
            for repetition in range(3):
                group=[t for t in trials if t.get('phase')==phase and t['kind']==kind and t['pair']==repetition]
                a=[t for t in group if t['arm']==left and t['status']=='ROLLED_BACK_VERIFIED']
                b=[t for t in group if t['arm']==right and t['status']=='ROLLED_BACK_VERIFIED']
                if len(a)!=1 or len(b)!=1: continue
                a,b=a[0],b[0]
                if a['source_sha256']!=b['source_sha256'] or a['rows']!=b['rows']: raise ValueError('PAIRED_SOURCE_MISMATCH')
                ratio=b['request_s']/a['request_s'] if a['request_s']>0 else None
                if ratio is not None: ratios.append(ratio)
                pairs.append({'pair':repetition,'rows':a['rows'],left+'_request_s':a['request_s'],right+'_request_s':b['request_s'],
                    left+'_end_to_end_s':a['elapsed_s'],right+'_end_to_end_s':b['elapsed_s'],
                    left+'_requests':len(a['batches']),right+'_requests':len(b['batches']),'right_over_left':ratio})
            result.append({'phase':phase,'kind':kind,'pairs':pairs,'complete_pairs':len(pairs),
                'median_right_over_left':statistics.median(ratios) if len(pairs)==3 and len(ratios)==3 else None,
                'status':'THREE_PAIRED_SAMPLES' if len(pairs)==3 else 'INCOMPLETE_NOT_ZERO',
                'scope':'descriptive paired probe; no full-job speedup/p95/automatic adoption'})
    return result
