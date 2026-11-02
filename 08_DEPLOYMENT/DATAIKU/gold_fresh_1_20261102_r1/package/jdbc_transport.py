"""JDBC value encoding adapter. Fixed SQL and transaction boundaries stay unchanged.

Only ASCII hex is embedded for text values. UTF-8 is reconstructed in Oracle;
backslashes, quotes and SQL-looking source text never enter the SQL lexer.
"""
import hashlib
import gzip
import json
import re
import time

TOKEN=re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/|:([A-Za-z][A-Za-z0-9_]*)")
CHUNK_BYTES=1800


def utf8_chunks(value,limit=CHUNK_BYTES):
    raw=value.encode('utf-8');start=0
    while start<len(raw):
        end=min(start+limit,len(raw))
        while end<len(raw) and raw[end]&0xC0==0x80:end-=1
        yield raw[start:end];start=end


def expression(raw):
    return "UTL_I18N.RAW_TO_CHAR(HEXTORAW('"+raw.hex().upper()+"'),'AL32UTF8')"


def render(statement,binds,*,write=False):
    values={};declarations=[];initializers=[];cleanup=[]
    for index,(name,value,kind) in enumerate(binds):
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name) or name in values:
            raise ValueError('JDBC_BIND_DUPLICATE_OR_INVALID')
        if value is None:values[name]='NULL';continue
        if kind=='NUMBER':
            if type(value) is not int:raise ValueError('JDBC_INTEGER_REQUIRED')
            values[name]=str(value)
        elif kind in {'VARCHAR2','CLOB'}:
            if type(value) is not str or '\0' in value:raise ValueError('JDBC_TEXT_REQUIRED')
            chunks=list(utf8_chunks(value,1800 if kind=='VARCHAR2' else CHUNK_BYTES))
            if kind=='VARCHAR2':
                if len(value.encode())>4000:raise ValueError('JDBC_VARCHAR2_LIMIT')
                values[name]='('+' || '.join(expression(raw) for raw in chunks)+')' if chunks else 'NULL'
            else:
                if not write:raise ValueError('JDBC_CLOB_REQUIRES_BLOCK')
                var='g8_lob_'+str(index)
                values[name]=var;declarations.append(var+' CLOB;')
                initializers.append('DBMS_LOB.CREATETEMPORARY('+var+',TRUE);')
                if len(value.encode())>32768:
                    # Transfer large JSON as gzip bytes, then reconstruct the
                    # identical UTF-8 CLOB before executing the original SQL.
                    packed=gzip.compress(value.encode(),compresslevel=6,mtime=0)
                    blob='g8_zip_'+str(index);plain='g8_raw_'+str(index);prefix='g8_'+str(index)
                    declarations.extend([blob+' BLOB;',plain+' BLOB;',prefix+'_d INTEGER:=1;',
                                         prefix+'_s INTEGER:=1;',prefix+'_c INTEGER:=0;',prefix+'_w INTEGER;'])
                    initializers.append('DBMS_LOB.CREATETEMPORARY('+blob+',TRUE);')
                    for offset in range(0,len(packed),CHUNK_BYTES):
                        piece=packed[offset:offset+CHUNK_BYTES]
                        initializers.append('DBMS_LOB.WRITEAPPEND('+blob+','+str(len(piece))+",HEXTORAW('"+piece.hex().upper()+"'));")
                    initializers.append(plain+':=UTL_COMPRESS.LZ_UNCOMPRESS('+blob+');')
                    initializers.append('DBMS_LOB.CONVERTTOCLOB('+var+','+plain+',DBMS_LOB.LOBMAXSIZE,'+
                                        prefix+'_d,'+prefix+"_s,NLS_CHARSET_ID('AL32UTF8'),"+prefix+'_c,'+prefix+'_w);')
                    initializers.append('IF '+prefix+"_w<>0 THEN RAISE_APPLICATION_ERROR(-20063,'JDBC_UTF8_CONVERSION_WARNING'); END IF;")
                    for item in (blob,plain):cleanup.append('IF DBMS_LOB.ISTEMPORARY('+item+')=1 THEN DBMS_LOB.FREETEMPORARY('+item+'); END IF;')
                else:
                    for raw in chunks:
                        initializers.append('DBMS_LOB.APPEND('+var+',TO_CLOB('+expression(raw)+'));')
                cleanup.append('IF DBMS_LOB.ISTEMPORARY('+var+')=1 THEN DBMS_LOB.FREETEMPORARY('+var+'); END IF;')
        else:raise ValueError('JDBC_UNSUPPORTED_BIND_TYPE')
    used=set()
    def replace(match):
        name=match.group(1)
        if name is None:return match.group()
        if name not in values:raise ValueError('JDBC_BIND_MISSING:'+name)
        used.add(name);return values[name]
    compiled=TOKEN.sub(replace,statement)
    if used!=set(values):raise ValueError('JDBC_BIND_UNUSED')
    if declarations:
        free='\n'.join(cleanup)
        compiled='DECLARE\n'+'\n'.join(declarations)+'\nBEGIN\n'+'\n'.join(initializers)+'\n'+compiled+'\n'+free+'\nEXCEPTION WHEN OTHERS THEN\n'+free+'\nRAISE;\nEND;'
    return compiled


def block(db,sql,binds=(),rollback=False):
    rendered=render(sql,binds,write=True)
    db.calls+=1;started=time.monotonic()
    # Metadata only: neither SQL values nor source text enter error logs.
    metadata={'phase':'JDBC_BLOCK','sql_bytes':len(rendered.encode()),
              'sql_sha256':hashlib.sha256(rendered.encode()).hexdigest(),
              'value_encoding':'UTF8_HEX_GZIP','rollback':rollback,
              'binds':[{'name':n,'type':t,'bytes':len(v.encode()) if isinstance(v,str) else None}
                       for n,v,t in binds]}
    try:
        frame=db.executor.query_to_df('SELECT 1 AS OK FROM DUAL',pre_queries=[rendered],
                                     post_queries=['ROLLBACK' if rollback else 'COMMIT'])
        if len(frame)!=1 or int(frame.iloc[0]['OK'])!=1:
            raise RuntimeError('WRITE_RESPONSE_UNCONFIRMED')
        return time.monotonic()-started
    except BaseException:
        metadata['elapsed_seconds']=round(time.monotonic()-started,3)
        print(json.dumps(metadata),flush=True)
        raise


def install(loader):
    if getattr(loader.Database,'_g8_transport',False):return
    loader.Database.block=block
    loader.Database._g8_transport=True
