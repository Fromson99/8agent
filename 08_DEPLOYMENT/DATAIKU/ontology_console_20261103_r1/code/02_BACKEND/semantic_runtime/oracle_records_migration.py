"""Explicit, quiesced import of existing runtime records; never run on serving startup.

Read original files with ordinary pathlib/SQLite, write only Oracle Agent rows.
Preserve raw values, rowid/PK, original hashes, failures and compressed blobs.
An incomplete tree import blocks Oracle serving for that logical root.
"""
from __future__ import annotations

import argparse
from pathlib import Path as LocalPath
import hashlib
import json
import os
import sqlite3
import time

from .oracle_dp_io import DPError,canonical,digest
from .oracle_agent_records import sha
from .oracle_record_sqlite import encode,quoted
from . import oracle_runtime_paths as paths

SOURCE_DATABASES={'store.sqlite','navigation.sqlite','fulltext.sqlite','dictionary.sqlite','lookup.sqlite','graph.sqlite'}

def file_sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def inventory(root):
    result=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise DPError('AGENT_MIGRATION_SYMLINK: explicit regular source tree required')
        if not path.is_file():continue
        relative=str(path.relative_to(root))
        control=('.storage-admission' in path.relative_to(root).parts or path.name.endswith(('.lock','.lease','-wal','-shm','-journal')))
        corpus=path.name in SOURCE_DATABASES
        result.append({'path':relative,'bytes':path.stat().st_size,'sha256':file_sha(path),
                       'kind':'control-sidecar' if control else 'knowledge-cache-excluded' if corpus else 'database' if path.suffix=='.sqlite' else 'file'})
    return result

def schema_of(source):
    shadows={r[1] for r in source.execute('PRAGMA table_list') if r[2]=='shadow'}
    definitions=[list(r) for r in source.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name") if r[1] not in shadows]
    value={'definitions':definitions,'user_version':source.execute('PRAGMA user_version').fetchone()[0],
           'application_id':source.execute('PRAGMA application_id').fetchone()[0]}
    if source.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
        value['sequence']=[list(r) for r in source.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name')]
    return value

def structured_blob_keys(source,catalogue):
    """Keep only compact blobs referenced by structured rows, not raw attempts."""
    from .legal_agent.journal_storage import MAGIC
    needed=set()
    if not source.execute("SELECT 1 FROM sqlite_master WHERE name='journal_blob_v1'").fetchone():return None
    for typ,name,_,_ in catalogue['definitions']:
        if typ!='table' or name=='journal_blob_v1':continue
        cols=[r[1] for r in source.execute('PRAGMA table_xinfo('+quoted(name)+')') if not r[6]]
        for row in source.execute('SELECT '+','.join(map(quoted,cols))+' FROM '+quoted(name)):
            for col,value in zip(cols,row):
                if name=='model_attempt' and col in ('request_json','response_json','receipt_json'):continue
                if name=='event' and col=='payload_json':
                    from .legal_agent.journal_storage import restore
                    payload=json.loads(restore(source,value));diagnostic=payload.get('diagnostics') if isinstance(payload,dict) else None
                    if isinstance(diagnostic,dict) and any(k in diagnostic for k in ('traceback','error_message')):continue
                if isinstance(value,bytes) and value.startswith(MAGIC):needed.add(json.loads(value)['genos_journal_blob_v1'])
    pending=list(needed)
    while pending:
        key=pending.pop();row=source.execute('SELECT codec,data FROM journal_blob_v1 WHERE hash=?',(key,)).fetchone()
        if row is None:raise DPError('AGENT_MIGRATION_BLOB: original structured reference is missing')
        if row[0]=='parts-v1':
            import zlib
            for kind,value in json.loads(zlib.decompress(row[1])):
                if kind in ('hash','json-string') and value not in needed:needed.add(value);pending.append(value)
    return needed

def split_attempt(source,cols,values,target):
    from .legal_agent.journal_storage import restore
    from .detailed_log_storage import request_record,response_record,is_reference
    row=dict(zip(cols,values));ident=row['attempt_id']
    request=json.loads(restore(source,row['request_json']))
    if not is_reference(request):request=request_record(request,owner=str(target),ident=ident,durable=True)
    response=json.loads(restore(source,row['response_json'])) if row.get('response_json') is not None else None
    receipt=json.loads(restore(source,row['receipt_json'])) if row.get('receipt_json') is not None else None
    if not receipt or receipt.get('response_storage')!='structured-response-v1':
        response,ref=response_record(response,owner=str(target),ident=ident,durable=True)
        if receipt is not None:receipt={**receipt,'diagnostic_response':ref,'response_storage':'structured-response-v1'}
    row['request_json']=canonical(request)
    row['response_json']=canonical(response) if response is not None else None
    row['response_hash']=digest(response) if response is not None else None
    row['receipt_json']=canonical(receipt) if receipt is not None else None
    return [row[col] for col in cols]

def import_database(source_path,target,store,fingerprint):
    owner=paths.identity(target);key='a1:head:'+owner;old=store.state(key)
    if old and old['value'].get('migration',{}).get('fingerprint')!=fingerprint:
        raise DPError('AGENT_MIGRATION_TARGET: preserve an existing unrelated Oracle record namespace')
    if old and old['value']['migration']['status']=='COMPLETE':return {'already_imported':True,'rows':old['value']['migration']['rows']}
    with sqlite3.connect(source_path.resolve().as_uri()+'?mode=ro',uri=True) as source:
        source.execute('PRAGMA query_only=ON');source.execute('BEGIN')
        catalogue=schema_of(source);schema_raw=canonical(catalogue).encode();store.put_bodies([schema_raw])
        live_blobs=structured_blob_keys(source,catalogue)
        total=0;skip=old['value']['migration']['rows'] if old else 0;revision=old['revision'] if old else 0
        changes=[];raws=[]
        def flush(status):
            nonlocal revision,changes,raws
            store.put_bodies(raws)
            meta={'type':'sqlite','path':str(target),'schema':sha(schema_raw),'mtime':source_path.stat().st_mtime,'size':source_path.stat().st_size,
                  'migration':{'fingerprint':fingerprint,'status':status,'rows':total}}
            if revision==0:changes.append(paths.entry_change(target,kind='sqlite'))
            revision=store.commit(owner,revision,meta,changes)
            changes=[];raws=[]
        for typ,name,_,sql in catalogue['definitions']:
            if typ!='table':continue
            if name in ('document','source_unit','block_payload'):
                raise DPError('AGENT_MIGRATION_SOURCE_CORPUS: primary knowledge is not an Agent record database')
            fields=[r for r in source.execute('PRAGMA table_xinfo('+quoted(name)+')') if not r[6]]
            cols=[r[1] for r in fields]
            without=bool(__import__('re').search(r'WITHOUT\s+ROWID',sql,__import__('re').I))
            pk=[r[1] for r in sorted(fields,key=lambda r:r[5]) if r[5]]
            select=cols if without else ['rowid',*cols]
            order=pk if without else ['rowid']
            for values in source.execute('SELECT '+','.join(map(quoted,select))+' FROM '+quoted(name)+' ORDER BY '+','.join(map(quoted,order))):
                raw_values=list(values if without else values[1:])
                if name=='journal_blob_v1' and live_blobs is not None and raw_values[cols.index('hash')] not in live_blobs:
                    continue
                total+=1
                if total<=skip:continue
                if name=='model_attempt':raw_values=split_attempt(source,cols,raw_values,target)
                if name=='event' and 'payload_json' in cols:
                    from .legal_agent.journal_storage import restore
                    from .detailed_log_storage import event_record
                    value=json.loads(restore(source,raw_values[cols.index('payload_json')]))
                    projected=event_record(value,owner=str(target),ident=[values[0],'event'],durable=True)
                    if projected!=value:
                        raw_values[cols.index('payload_json')]=canonical(projected)
                        raw_values[cols.index('payload_hash')]=digest(projected)
                ids=[raw_values[cols.index(k)] for k in pk] if without else [values[0]]
                item={'table':name,'key':[encode(v) for v in ids],'rowid':not without,'columns':cols,'values':[encode(v) for v in raw_values]}
                raw=canonical(item).encode();raws.append(raw)
                changes.append({'kind':'SQLROW:'+name,'key':digest({'table':name,'key':item['key']}),'order':0,'lookup':None,'body':sha(raw),'deleted':0})
                if len(changes)>=100:flush('IN_PROGRESS')
        flush('COMPLETE')
    return {'rows':total,'schema_sha256':sha(schema_raw),'already_imported':False}

def migrate_tree(source_root,logical_root,*,store,quiesced=False):
    if not quiesced:raise DPError('AGENT_MIGRATION_QUIESCE: stop all old runtime writers before importing')
    source_root=LocalPath(source_root).resolve();logical_root=paths.Path(logical_root).resolve()
    if not source_root.is_dir() or not paths.virtual(logical_root):raise DPError('AGENT_MIGRATION_ROOT: source and configured logical Oracle roots required')
    before=inventory(source_root);fingerprint=digest({'source_root':str(source_root),'logical_root':str(logical_root),'files':before})
    marker=digest({'migration_root':str(logical_root)});state=store.state('a1:head:'+marker)
    if state and state['value'].get('fingerprint')!=fingerprint:
        raise DPError('AGENT_MIGRATION_CHANGED: original tree differs from the existing import receipt')
    if state and state['value'].get('status')=='COMPLETE':return {'status':'ALREADY_IMPORTED','fingerprint':fingerprint,'source_unchanged':True}
    revision=state['revision'] if state else 0
    revision=store.commit(marker,revision,{'type':'migration','root':str(logical_root),'fingerprint':fingerprint,'status':'IN_PROGRESS'},[])
    outcomes=[]
    with paths.using(store):
        for item in before:
            if item['kind'] in ('control-sidecar','knowledge-cache-excluded'):
                outcomes.append({**item,'action':'original preserved; not Agent business data'});continue
            source=source_root/item['path'];target=logical_root/item['path']
            from .detailed_log_storage import diagnostic_path
            if diagnostic_path(target):
                outcomes.append({**item,'action':'detailed log preserved on original NFS; not imported into Oracle'});continue
            target.parent.mkdir(parents=True,exist_ok=True)
            if item['kind']=='database':
                outcome=import_database(source,target,store,digest({'tree':fingerprint,'database':item}))
            else:
                old=paths.metadata(target)
                if old:
                    if sha(target.read_bytes())!=item['sha256']:raise DPError('AGENT_MIGRATION_FILE_CONFLICT: exact original differs')
                    outcome={'already_imported':True}
                else:
                    raw=source.read_bytes();paths.write_file(target,raw,exclusive=True);outcome={'already_imported':False}
            outcomes.append({'path':item['path'],'kind':item['kind'],**outcome})
    if inventory(source_root)!=before:
        raise DPError('AGENT_MIGRATION_SOURCE_CHANGED: keep Oracle tree blocked and reconcile the original writers')
    receipt={'status':'COMPLETE','source_root':str(source_root),'logical_root':str(logical_root),'fingerprint':fingerprint,
             'source_unchanged':True,'original_files':before,'outcomes':outcomes,'resume_compatibility':'original code/source binding still required'}
    raw=canonical(receipt).encode();store.put_bodies([raw])
    store.commit(marker,revision,{'type':'migration','root':str(logical_root),'fingerprint':fingerprint,'status':'COMPLETE','receipt':sha(raw)},[])
    return receipt

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--logical-root',required=True)
    parser.add_argument('--writers-stopped',action='store_true');parser.add_argument('--receipt',required=True)
    args=parser.parse_args(argv)
    if os.environ.get('DP','').lower()!='oracle':raise DPError('Set DP=oracle for the target Oracle connection')
    result=migrate_tree(args.source,args.logical_root,store=paths.records(),quiesced=args.writers_stopped)
    target=LocalPath(args.receipt)
    with target.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'status':result['status'],'source_unchanged':result['source_unchanged']},ensure_ascii=False))

if __name__=='__main__':main()
