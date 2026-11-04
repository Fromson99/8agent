"""Execute prebuilt Oracle reads over request-pinned projections.

Shared consumers retain their SQLite query contract. Only prepared Oracle
plans may execute here; no dialect parser or runtime transpilation is used.
"""
from __future__ import annotations

import json
import re


from .oracle_dp_io import DPError, units
from .oracle_query_catalog import ROW, json_body


class Row:
    def __init__(self,names,values):
        self.names,self.values=tuple(names),tuple(values)
    def __getitem__(self,key):
        return self.values[self.names.index(key)] if isinstance(key,str) else self.values[key]
    def __iter__(self):
        return iter(self.values)
    def __len__(self):
        return len(self.values)
    def keys(self):
        return self.names


class Cursor:
    def __init__(self,names,rows):
        self.description=[(name,None,None,None,None,None,None) for name in names]
        self.names,self.rows=names,iter(rows)
    def __iter__(self):
        return self
    def __next__(self):
        return Row(self.names,next(self.rows))
    def fetchone(self):
        return next(self,None)
    def fetchmany(self,size=100):
        if type(size) is not int or not 0<=size<=10000:
            raise DPError('QUERY_PAGE: invalid fetch size')
        rows=[]
        for _ in range(size):
            row=self.fetchone()
            if row is None: break
            rows.append(row)
        return rows
    def fetchall(self):
        return list(self)
    def close(self):
        close=getattr(self.rows,'close',None)
        if close: close()


def _identifier(value):
    if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',value):
        raise DPError('QUERY_SQL_IDENTIFIER: undeclared identifier syntax')
    return value




class Connection:
    def __init__(self,request,asset):
        self.request,self.sql=request,request.sql
        self.asset=asset
        self.tables={v['table']:(kind,v) for kind,v in request.records.manifest['tables'].items()
                     if v.get('asset')==asset and 'columns' in v}
        if not self.tables:
            raise DPError('QUERY_SQL_SCHEMA: no projected relational schema for '+asset)
        self.row_factory=None
        self.closed=False

    def close(self):
        self.closed=True

    def set_progress_handler(self,callback,steps):
        # Oracle owns execution; check caller cancellation between bounded
        # requests in addition to the shared ORDS deadline/call budget.
        self.progress_handler=callback

    def _progress(self):
        callback=getattr(self,'progress_handler',None)
        if callback is not None and callback():
            raise DPError('QUERY_CANCELLED: caller deadline/cancellation reached')

    def __enter__(self):
        return self

    def __exit__(self,*exc):
        self.close()

    def _view(self,name,number):
        kind,table=self.tables[name]
        definitions=[]
        for column,spec in table['columns'].items():
            _identifier(column)
            typ=('NUMBER' if spec['type'] in ('integer','real') else
                 'CLOB' if spec['max_bytes']>4000 else 'VARCHAR2(4000)')
            definitions.append('"'+column+'" '+typ+" PATH '$."+column+"' ERROR ON ERROR")
        suffix=str(number)
        binds=[('a8_release'+suffix,self.request.release_id,'VARCHAR2'),('a8_kind'+suffix,kind,'VARCHAR2'),
               ('a8_scope'+suffix,json_body(sorted(self.request.sources.allowed)),'CLOB')]
        text=('SELECT jt.*,r.ROW_ID AS "a8_row_id" FROM '+ROW+' r,JSON_TABLE(r.VALUE_JSON,\'$\' COLUMNS('+','.join(definitions)+')) jt '
              f'WHERE r.RELEASE_ID=:a8_release{suffix} AND r.KIND=:a8_kind{suffix} '
              '(AND_SCOPE)')
        text=text.replace('(AND_SCOPE)',f"AND (r.DOCUMENT_ID IS NULL OR r.DOCUMENT_ID IN (SELECT s.did FROM JSON_TABLE(:a8_scope{suffix},'$[*]' COLUMNS(did VARCHAR2(512) PATH '$')) s))")
        flags=["CASE WHEN JSON_EXISTS(r.VALUE_JSON,'$?(@."+c+" == \"\")') THEN 1 ELSE 0 END AS \"a8_empty_"+c+'"'
               for c,spec in table['columns'].items() if spec.get('has_empty')]
        if flags: text=text.replace('SELECT jt.*,','SELECT jt.*,'+','.join(flags)+',',1)
        return text,binds

    def _catalogue(self,statement,parameters):
        # sqlite_master/table_info are metadata requests. Interpret only the
        # small declared schema locally; no source/index rows enter SQLite.
        import sqlite3
        cache_key=(statement,tuple(parameters))
        cached=getattr(self,'_schema_results',{}).get(cache_key)
        if cached is not None:return Cursor(list(cached[0]),list(cached[1]))
        if not statement.lstrip().upper().startswith(('SELECT ','PRAGMA TABLE_INFO(')):
            raise DPError('QUERY_SQL_READ_ONLY: schema metadata is read-only')
        with sqlite3.connect(':memory:') as db:
            db.execute('PRAGMA temp_store=MEMORY')
            for name,(_,spec) in self.tables.items():
                columns=','.join('"'+_identifier(c)+'" '+('INTEGER' if v['type']=='integer' else 'REAL' if v['type']=='real' else 'TEXT')
                                 for c,v in spec['columns'].items())
                db.execute('CREATE TABLE "'+_identifier(name)+'"('+columns+')')
            cursor=db.execute(statement,parameters)
            names=[d[0] for d in cursor.description];rows=cursor.fetchall()
            if not hasattr(self,'_schema_results'):self._schema_results={}
            if len(self._schema_results)<64:self._schema_results[cache_key]=(tuple(names),tuple(rows))
            return Cursor(names,rows)

    def execute(self,statement,parameters=()):
        self._progress()
        if self.closed:
            raise DPError('QUERY_SQL_CLOSED: request connection is closed')
        if re.fullmatch(r'\s*PRAGMA\s+query_only\s*=\s*(ON|1)\s*',statement,re.I):
            return Cursor([],[])
        if re.fullmatch(r'\s*PRAGMA\s+table_info\(.+\)\s*',statement,re.I) or 'sqlite_master' in statement:
            return self._catalogue(statement,parameters)
        from .oracle_query_cache import for_request, key as result_key
        query_cache=for_request(self.request)
        query_key=result_key('relational',asset=self.asset,statement=statement,parameters=list(parameters),tables=self.tables)
        cache_hit,cached=query_cache.get(query_key)
        if cache_hit:return Cursor(cached[0],cached[1])
        self._needs_literal = bool(re.search(r'\blegal_normalized\s*\(', statement, re.I))
        from .oracle_query_native import prepare
        outputs,packed,binds,empty_indexes=prepare(self,statement,parameters)
        def decoded():
            saved=[];size=0
            for row in self._pages(packed,binds):
                for i,flag in zip(empty_indexes,row[len(outputs):]):
                    if flag==1: row[i]=''
                value=row[:len(outputs)]
                if saved is not None:
                    size+=len(json.dumps(value,ensure_ascii=False).encode())
                    if size<=4*1024*1024:saved.append(value)
                    else:saved=None
                yield value
            if saved is not None:query_cache.put(query_key,[outputs,saved])
        return Cursor(outputs,decoded())

    def _pages(self,packed,binds):
        offset,total_bytes=0,0
        while True:
            self._progress()
            page=packed+f' OFFSET {offset} ROWS FETCH NEXT 100 ROWS ONLY'
            rows=self.sql.query('SELECT p.body,DBMS_LOB.GETLENGTH(p.body) AS n FROM ('+page+') p',binds,limit=100)
            for index,row in enumerate(rows):
                body=row['BODY']
                if not isinstance(body,str) or units(body)!=row['N']:
                    body='';at=1
                    while units(body)<row['N']:
                        single=packed+f' OFFSET {offset+index} ROWS FETCH NEXT 1 ROWS ONLY'
                        part=self.sql.query('SELECT DBMS_LOB.SUBSTR(p.body,1000,:a8_lob_pos) AS piece,DBMS_LOB.GETLENGTH(p.body) AS n FROM ('+single+') p',
                            [*binds,('a8_lob_pos',at,'NUMBER')],limit=1)
                        if len(part)!=1 or part[0]['N']!=row['N'] or not part[0]['PIECE']:
                            raise DPError('QUERY_SQL_CLOB: result changed/truncated during read')
                        body+=part[0]['PIECE'];at=units(body)+1
                    if units(body)!=row['N']:
                        raise DPError('QUERY_SQL_CLOB: inconsistent result length')
                total_bytes+=len(body.encode())
                if total_bytes>64*1024*1024 or offset+index>=10000:
                    raise DPError('QUERY_SQL_RESULT_BUDGET: use bounded consumer pages')
                yield json.loads(body)
            if len(rows)<100:
                return
            offset+=len(rows)
