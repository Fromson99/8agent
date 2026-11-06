"""Import the already approved five-table snapshot through Dataiku SQLExecutor2.

One bundle is one Oracle transaction. Existing identical rows are reconciled;
changed/withdrawn publications fail closed. No DDL or source writes.
"""
import io
import json
import re
import uuid
from it35_common import *
from it35_mapping import GoldMapping, CONTRACT, ONTOLOGY, identifier
from it35_jdbc import render, block

class Database:
    def __init__(self,executor):self.executor=executor;self.calls=0
    def query(self,sql,binds=(),limit=4096):
        self.calls+=1
        frame=self.executor.query_to_df(render(sql,binds),infer_from_schema=True,parse_dates=False)
        frame=frame.astype(object).where(frame.notna(),None)
        if len(frame)>limit:raise ValueError('Oracle result bound')
        return [tuple(v.item() if hasattr(v,'item') else v for v in row) for row in frame.itertuples(index=False,name=None)]

def mappings(profile,source_owner,target_owner,agent_owner):
    if profile not in ('B003','G19'):raise ValueError('Mapping must be B003 or G19')
    filename='mapping_b003.json' if profile=='B003' else 'mapping_g19.json'
    source=GoldMapping.load(HERE/filename,owner=identifier(source_owner))
    target=GoldMapping.load(HERE/filename,owner=identifier(target_owner))
    tables={k:identifier(agent_owner)+'.'+t for k,t in TABLES.items()}
    cols,_=snapshot();physical={k:{c:c for c in v} for k,v in cols.items()}
    for k,(logical,names) in ONTOLOGY.items():
        tables[k]=target.physical_table(logical)
        physical[k]={name:target.column(logical,field) for name,field in zip(names.split(),CONTRACT[logical].split())}
    return source,tables,physical

def resolve_generation(db,mapping,requested):
    if requested:return requested
    versions={}
    for s in read_json(PAYLOAD/'sources.json'):
        a=s['anchor'];versions[a['document_id']]=a['version']
    selected=None
    for did,version in versions.items():
        col=lambda c:mapping.column('DOC_VER',c)
        rows=db.query('SELECT '+col('MNFST_HASH_VALU')+' FROM '+mapping.physical_table('DOC_VER')+
            ' WHERE '+col('DOC_ID')+'=:did AND '+col('DOC_HASH_VALU')+'=:ver FETCH FIRST 1025 ROWS ONLY',
            [('did',did,'VARCHAR2'),('ver',version,'VARCHAR2')],1024)
        found={r[0] for r in rows};selected=found if selected is None else selected&found
    if len(selected or ())!=1:
        raise ValueError('Set DATASET_VERSION explicitly: no unique generation contains all five reviewed source versions')
    return next(iter(selected))

def source_check(db,mapping,generation):
    def read(a):
        d=lambda c:mapping.column('DOC_VER',c);b=lambda c:mapping.column('DOC_BLK',c)
        binds=[('gen',generation,'VARCHAR2'),('did',a['document_id'],'VARCHAR2')]
        docs=db.query('SELECT '+d('DOC_HASH_VALU')+' FROM '+mapping.physical_table('DOC_VER')+
            ' WHERE '+d('MNFST_HASH_VALU')+'=:gen AND '+d('DOC_ID')+'=:did',binds,1)
        blocks=db.query('SELECT '+b('BODY_SLC_ID')+','+b('BODY_CTNT')+' FROM '+mapping.physical_table('DOC_BLK')+
            ' WHERE '+b('MNFST_HASH_VALU')+'=:gen AND '+b('DOC_ID')+'=:did AND '+b('STRC_UNIT_ID')+
            '=:unit ORDER BY TO_NUMBER('+b('BODY_SLC_ID')+') FETCH FIRST 4097 ROWS ONLY',
            binds+[('unit',a['unit_id'],'VARCHAR2')])
        return (docs[0][0] if docs else None),blocks
    return verify_sources(read)

def bundle_rows(rows,bid):
    pub=[r for r in rows['publication'] if r['BNDL_ID']==bid]
    if len(pub)!=1:raise ValueError('Snapshot publication count')
    pid=pub[0]['PUB_ID']
    return {k:[r for r in values if r.get('BNDL_ID')==bid or (k=='anchor' and r['PUB_ID']==pid)]
            for k,values in rows.items()}

def filter_for(key,rows,columns):
    field='PUB_ID' if key=='anchor' else 'BNDL_ID'
    return columns[field]+'=:bid',[('bid',rows[0][field],'VARCHAR2')]

def check_existing(db,tables,columns,cols,part):
    actual={}
    for key in TABLES:
        where,binds=filter_for(key,part[key],columns[key])
        actual[key]=db.query('SELECT '+','.join(columns[key][c] for c in cols[key])+' FROM '+tables[key]+
                             ' WHERE '+where,binds,1024)
    if not any(actual.values()):return False
    for key in TABLES:
        expected=[tuple(row[c] for c in cols[key]) for row in part[key]]
        # Oracle JSON columns may arrive as decoded objects (DB-API) or CLOB
        # strings (JDBC). The workflow receipt hashes canonical JSON content.
        def normalize(row):
            return tuple(json.dumps(json.loads(v) if isinstance(v,str) else v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                         if c in ('EVT_JSON_CN','PKG_JSON_CN') else v for c,v in zip(cols[key],row))
        actual[key]=[normalize(row) for row in actual[key]]
        expected=[normalize(row) for row in expected]
        if sorted(actual[key],key=repr)!=sorted(expected,key=repr):
            detail={'table':key,'actual_rows':len(actual[key]),'expected_rows':len(expected)}
            if len(actual[key])==len(expected):
                detail['different_columns']=sorted({col for a,b in zip(sorted(actual[key],key=repr),sorted(expected,key=repr))
                    for col,x,y in zip(cols[key],a,b) if x!=y})
            raise ValueError('Existing changed/withdrawn/partial bundle; preserve it: '+part['head'][0]['BNDL_ID']+' '+json.dumps(detail))
    return True

def bundle_sql(tables,columns,cols,part):
    binds=[]
    def param(value,field):
        name='p'+str(len(binds));kind='CLOB' if field in ('EVT_JSON_CN','PKG_JSON_CN') else 'NUMBER' if isinstance(value,int) else 'VARCHAR2'
        binds.append((name,value,kind));return ':'+name
    head=part['head'][0];bid=param(head['BNDL_ID'],'BNDL_ID')
    lines=['DECLARE n NUMBER; h VARCHAR2(100); s NUMBER; BEGIN',
        'BEGIN SELECT '+columns['head']['PUB_ID']+','+columns['head']['CHG_SEQ_NO']+' INTO h,s FROM '+tables['head']+
        ' WHERE '+columns['head']['BNDL_ID']+'='+bid+' FOR UPDATE; n:=1; EXCEPTION WHEN NO_DATA_FOUND THEN n:=0; END;',
        'IF n=1 THEN']
    # Under the head lock, re-check every field, count and receipt before reuse.
    reused=[];fresh=[];inserts=[]
    for key in ('work','event','publication','anchor','head'):
        col=columns[key];field='PUB_ID' if key=='anchor' else 'BNDL_ID'
        where=col[field]+'='+param(part[key][0][field],field)
        count='SELECT COUNT(*) INTO n FROM '+tables[key]+' WHERE '+where+';'
        reused += [count,"IF n<>"+str(len(part[key]))+" THEN RAISE_APPLICATION_ERROR(-20071,'IT35_CHANGED_COUNT'); END IF;"]
        fresh += [count,"IF n<>0 THEN RAISE_APPLICATION_ERROR(-20072,'IT35_PARTIAL_OR_CONCURRENT'); END IF;"]
        for row in part[key]:
            vals={c:param(row[c],c) for c in cols[key]}
            equal=[]
            for c in cols[key]:
                if row[c] is None:equal.append(col[c]+' IS NULL')
                elif c in ('EVT_JSON_CN','PKG_JSON_CN'):equal.append('DBMS_LOB.COMPARE('+col[c]+','+vals[c]+')=0')
                else:equal.append(col[c]+'='+vals[c])
            reused += ['SELECT COUNT(*) INTO n FROM '+tables[key]+' WHERE '+' AND '.join(equal)+';',
                "IF n<>1 THEN RAISE_APPLICATION_ERROR(-20073,'IT35_CHANGED_OR_WITHDRAWN'); END IF;"]
            inserts += ['INSERT INTO '+tables[key]+' ('+','.join(col[c] for c in cols[key])+') VALUES ('+
                        ','.join(vals[c] for c in cols[key])+');']
    lines+=reused+['ELSE']+fresh+inserts+['END IF; COMMIT; EXCEPTION WHEN OTHERS THEN ROLLBACK; RAISE; END;']
    return '\n'.join(lines),binds

def run(executor,folder,*,profile='B003',source_owner='SIDDS',target_owner='SIDDA',agent_owner='SIDDA',dataset_version='',apply=True):
    verify_package();cols,rows=snapshot();db=Database(executor)
    source,tables,columns=mappings(profile,source_owner,target_owner,agent_owner)
    for key in TABLES:
        db.query('SELECT '+','.join(columns[key][c] for c in cols[key])+' FROM '+tables[key]+' WHERE 1=0')
    generation=resolve_generation(db,source,dataset_version)
    count=source_check(db,source,generation)
    parts=[bundle_rows(rows,r['BNDL_ID']) for r in rows['head']]
    existing=[check_existing(db,tables,columns,cols,p) for p in parts]
    result={'status':'PREFLIGHT_PASS','source_generation':generation,'source_units':count,'profile':profile,
        'tables':tables,'existing_bundles':sum(existing),'bundles':24,'paths':46,'source_writes':0,'ddl':0,
        'model_calls':0,'automatic_retries':0,'completed':[]}
    if not apply:return result
    # Keep the content-addressed work objects usable by the existing DataikuFolderStore.
    known={p.lstrip('/') for p in folder.list_paths_in_partition()}
    for path in sorted((PAYLOAD/'work/objects').glob('*.json')):
        key='objects/'+path.name;raw=path.read_bytes()
        if key in known:
            with folder.get_download_stream(key) as f:
                if f.read()!=raw:raise ValueError('Existing managed work object changed')
        else:folder.upload_stream(key,io.BytesIO(raw))
        with folder.get_download_stream(key) as f:
            if f.read()!=raw:raise ValueError('Managed work object readback failed')
    receipt_path='_integration_ontology_r2/'+uuid.uuid4().hex+'/receipt.json'
    def save():folder.upload_stream(receipt_path,io.BytesIO(json_bytes(result)))
    result.update(status='RUNNING',receipt_path=receipt_path);save()
    for index,(part,reused) in enumerate(zip(parts,existing),1):
        bid=part['head'][0]['BNDL_ID']
        try:
            if not reused:
                sql,binds=bundle_sql(tables,columns,cols,part)
                block(db,sql,binds,transaction_managed=True)
            if not check_existing(db,tables,columns,cols,part):raise ValueError('Missing readback')
            result['completed'].append({'bundle_id':bid,'reused':reused})
            save();print('ONTOLOGY '+str(index)+'/24 '+('REUSED' if reused else 'INSERTED'),flush=True)
        except BaseException as exc:
            result.update(status='STOPPED_CHECK_RECEIPT_BEFORE_EXPLICIT_RESUME',failed_bundle=bid,error_type=type(exc).__name__)
            save();raise
    # Source metadata/text and all active heads are checked again before completion.
    try:
        source_check(db,source,generation)
        for part in parts:
            if not check_existing(db,tables,columns,cols,part):raise ValueError('Final readback missing')
    except BaseException as exc:
        result.update(status='FINAL_VERIFICATION_FAILED',error_type=type(exc).__name__);save();raise
    result.update(status='ORACLE_IMPORT_COMPLETE',sql_requests=db.calls);save()
    return result
