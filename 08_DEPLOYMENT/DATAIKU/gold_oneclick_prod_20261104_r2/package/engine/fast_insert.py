"""Insert-only batch SQL. Oracle enforces types, lengths, NOT NULL and PK.

No existence lookup, post-insert count, LOB compare or verification pass. The PK
lookup is exclusively for reconciling an interrupted, unacknowledged batch.
"""
from gold_io import Contract as BaseContract, Stop, canonical


class Contract(BaseContract):
    def batch(self, key, rows, *, verify_only=False):
        if verify_only: raise Stop('R6_FULL_VERIFICATION_REMOVED')
        if not rows: raise Stop('EMPTY_INSERT_BATCH')
        t = self.tables[key]
        names = [n for n, c in t['columns'].items() if not c['default']]
        payload, specs, expressions = [], [], {}
        for i, n in enumerate(names):
            typ = t['columns'][n]['type']; alias = 'c'+str(i)
            specs.append(alias+' '+('VARCHAR2(1)' if typ.startswith('CHAR(') else typ)+" PATH '$."+alias+"' ERROR ON ERROR")
            if typ == 'CLOB':
                specs.append(alias+"e NUMBER PATH '$."+alias+"e' ERROR ON ERROR")
                expressions[n] = '(CASE WHEN s.'+alias+'e=1 THEN EMPTY_CLOB() ELSE s.'+alias+' END)'
            else: expressions[n] = 's.'+alias
        for row in rows:
            value = {}
            for i, n in enumerate(names):
                alias = 'c'+str(i);value[alias] = row.get(n)
                if t['columns'][n]['type'] == 'CLOB': value[alias+'e'] = int(row.get(n) == '')
            payload.append(value)
        source = "JSON_TABLE(:payload,'$[*]' ERROR ON ERROR COLUMNS("+','.join(specs)+')) s'
        sql = ('BEGIN INSERT INTO '+self.table(key)+' ('+','.join(self.col(key,n) for n in names)+') SELECT '+
               ','.join(expressions[n] for n in names)+' FROM '+source+'; COMMIT; '
               'EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;')
        return sql, [('payload', canonical(payload), 'CLOB')]

    def pending_count(self, db, key, rows):
        # This runs only after interruption. Count keys, never read/compare LOBs.
        t = self.tables[key]; names = t['primary_key']
        specs = ['c'+str(i)+' '+t['columns'][n]['type']+" PATH '$.c"+str(i)+"' ERROR ON ERROR" for i,n in enumerate(names)]
        keys = [{('c'+str(i)):row[n] for i,n in enumerate(names)} for row in rows]
        if len({canonical(row) for row in keys}) != len(rows):
            raise Stop('PENDING_DUPLICATE_KEYS_REVIEW_REQUIRED')
        sql = ('SELECT COUNT(*) FROM JSON_TABLE(:payload,\'$[*]\' ERROR ON ERROR COLUMNS('+','.join(specs)+')) s JOIN '+
               self.table(key)+' t ON ('+' AND '.join('t.'+self.col(key,n)+'=s.c'+str(i) for i,n in enumerate(names))+')')
        from jdbc_transport import expression, utf8_chunks
        payload = canonical(keys)
        clob = ' || '.join('TO_CLOB('+expression(piece)+')' for piece in utf8_chunks(payload))
        sql = sql.replace('COUNT(*) FROM', 'COUNT(*) AS N FROM', 1).replace(':payload', '('+clob+')')
        result = db.query(sql)
        if len(result)!=1 or type(result[0]['N']) not in (int, float):
            raise Stop('PENDING_KEY_COUNT_UNCONFIRMED')
        return int(result[0]['N'])
