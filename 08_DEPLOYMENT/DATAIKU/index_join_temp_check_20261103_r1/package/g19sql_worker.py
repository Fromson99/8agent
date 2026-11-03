"""Bounded SELECT-only collector. No loader imports, SQL replays or write recovery."""
import fcntl
import hashlib
from pathlib import Path
import time
import sys
from g19sql_common import bind, read, write, error, timing
from g19sql_queries import IDENTITY, bounded, metadata, candidates, plans, temp, readonly


def conclusions(result):
    queries = result.get('queries',{})
    rows = lambda n: queries.get(n,{}).get('rows',[])
    indexes = []
    for index in rows('indexes'):
        columns = sorted([c for c in rows('index_columns') if c['INDEX_OWNER']==index['OWNER'] and c['INDEX_NAME']==index['INDEX_NAME']], key=lambda c:c['COLUMN_POSITION'])
        names = [c['COLUMN_NAME'] for c in columns]
        pk = result['binding']['pk_columns']
        indexes.append({**index,'columns':names,
            'pk_leading_columns':set(names[:len(pk)])==set(pk) if queries.get('index_columns',{}).get('status')=='OK' else None})
    cached = []
    for cursor in result.get('cursors',[]):
        prefix = cursor['key']
        plan_rows = rows(prefix+'_plan')
        runtime = rows(prefix+'_runtime')
        stats = {r['ID']:r for r in runtime}
        operations = []
        for row in plan_rows:
            op = row['OPERATION']+' '+(row.get('OPTIONS') or '')
            if any(term in op for term in ('TABLE ACCESS','INDEX','JOIN','SORT','GROUP','UNIQUE')):
                operations.append({**row,'last_starts':stats.get(row['ID'],{}).get('LAST_STARTS')})
        cached.append({**cursor,'operations':operations,
            'runtime_rows_available':bool(runtime),
            'nonzero_last_starts':any((r.get('LAST_STARTS') or 0)>0 for r in runtime) if any(r.get('LAST_STARTS') is not None for r in runtime) else None,
            'workarea_last_temp_bytes':[r['LAST_TEMPSEG_SIZE'] for r in runtime if r.get('LAST_TEMPSEG_SIZE') is not None],
            'attribution':'SAME_ACCOUNT_TARGET_CANDIDATE_NOT_EXACT_COMPARISON_RUN'})
    result['index_summary']=indexes
    result['plan_summary']=cached


def dba_sql(ctx):
    blocks = ['-- SELECT only. Use the SAME database/PDB as the saved comparison.',
              '-- Cached candidates are NOT proof of ownership by one comparison run.',
              '-- TEMP snapshot after completion is NOT historical peak usage.',
              '-- No source data, SQL text or predicate literals are selected.']
    entries = [('identity',IDENTITY,1),*metadata(ctx),('cached_candidates',candidates(ctx),12),('current_account_temp',temp(ctx),100)]
    for name,sql,_ in entries:
        blocks += ['-- '+name,readonly(sql)+';']
    for name,view,cols in (
        ('candidate_plans','GV$SQL_PLAN','p.ID,p.PARENT_ID,p.OPERATION,p.OPTIONS,p.OBJECT_OWNER,p.OBJECT_NAME,p.CARDINALITY,p.TEMP_SPACE'),
        ('candidate_runtime','GV$SQL_PLAN_STATISTICS_ALL','p.ID,p.LAST_STARTS,p.LAST_OUTPUT_ROWS,p.LAST_CR_BUFFER_GETS,p.LAST_DISK_READS,p.LAST_ELAPSED_TIME,p.LAST_TEMPSEG_SIZE,p.MAX_TEMPSEG_SIZE,p.LAST_EXECUTION')):
        sql = ('SELECT c.INST_ID,c.SQL_ID,c.CHILD_NUMBER,c.PLAN_HASH_VALUE,'+cols+' FROM ('+candidates(ctx)+') c JOIN '+view+
               ' p ON p.INST_ID=c.INST_ID AND p.SQL_ID=c.SQL_ID AND p.CHILD_NUMBER=c.CHILD_NUMBER AND p.PLAN_HASH_VALUE=c.PLAN_HASH_VALUE ORDER BY c.INST_ID,c.SQL_ID,c.CHILD_NUMBER,p.ID')
        blocks += ['-- '+name+' (up to 13 cached candidates; final row limit 3328)',readonly(bounded(sql,3328))+';']
    return '\n\n'.join(blocks)+'\n'


def collect(ctx, output, query, clock=time.monotonic):
    output=Path(output)
    result={'status':'RUNNING','queries':{},'cursors':[],'active':None,
        'binding':{k:ctx[k] for k in ('comparison_path','comparison_sha256','comparison_run_id','owner','table','pk_columns','database','object','package','code_sha256','contract_sha256')},
        'loader_status':ctx['loader_status'],'timing':timing(ctx['report']),
        'comparison_skipped':ctx['report'].get('skipped',[]),
        'limits':{'queries':40,'seconds':240,'per_query_parent_seconds':45,'cached_cursors':12},
        'scope':'dictionary and cached plans only; no exact-run attribution or historical TEMP peak',
        'queries_count':0}
    started=clock()
    state=Path(ctx['state_path'])
    (output/'DBA_READONLY_CHECK.sql').write_text(dba_sql(ctx),encoding='utf-8')
    def save(): write(output/'worker-result.json',result)
    def guard():
        if clock()-started>240: raise ValueError('READONLY_TIME_BUDGET')
        if result['queries_count']>=40: raise ValueError('READONLY_QUERY_BUDGET')
        if hashlib.sha256(state.read_bytes()).hexdigest()!=ctx['original_state_sha256']:
            raise ValueError('ORIGINAL_STATE_CHANGED')
    def call(name,sql,limit):
        guard();readonly(sql)
        result['active']={'name':name,'started_epoch':time.time()}
        result['queries_count']+=1;save();start=clock()
        try:
            values=query(sql)
            if not isinstance(values,list): raise ValueError('INVALID_QUERY_RESULT')
            result['queries'][name]={'status':'TRUNCATED' if len(values)>limit else 'OK',
                'rows':values[:limit],'returned_rows':len(values),'seconds':clock()-start}
            return values[:limit]
        except Exception as exc:
            details=error(exc)
            allowed={'ORA-00942','ORA-01031','ORA-00904'}
            optional=bool(details['codes']) and set(details['codes'])<=allowed
            result['queries'][name]={'status':'UNAVAILABLE' if optional else 'FAILED',**details,'seconds':clock()-start}
            if not optional: raise
            return []
        finally:
            result['active']=None;save()
    try:
        with (state.parent/'job.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            current=call('identity',IDENTITY,1)
            if current!=ctx['database']: raise ValueError('DATABASE_IDENTITY_UNCONFIRMED')
            queries=metadata(ctx)
            name,sql,limit=queries[0]
            if call(name,sql,limit)!=ctx['object']: raise ValueError('TARGET_OBJECT_CHANGED_OR_UNAVAILABLE')
            for name,sql,limit in queries[1:]:call(name,sql,limit)
            cursors=call('cached_candidates',candidates(ctx),12)
            runtime_unavailable=False
            for index,cursor in enumerate(cursors):
                key='cursor_'+str(index+1)
                result['cursors'].append({**cursor,'key':key})
                for name,sql,limit in plans(cursor,ctx['pk_columns']):
                    if name=='runtime' and runtime_unavailable: continue
                    call(key+'_'+name,bounded(sql,limit),limit)
                    if name=='runtime' and result['queries'][key+'_'+name]['status']=='UNAVAILABLE':runtime_unavailable=True
            call('current_account_temp',temp(ctx),100)
            result['status']='COLLECTED' if all(q['status']=='OK' for q in result['queries'].values()) else 'PARTIAL'
            if not cursors:result['status']='PARTIAL'
    except Exception as exc:
        result.update(status='STOPPED',error=error(exc))
    finally:
        result['active']=None
        result['elapsed_s']=clock()-started
        try: result['original_state_unchanged']=hashlib.sha256(state.read_bytes()).hexdigest()==ctx['original_state_sha256']
        except OSError:result['original_state_unchanged']=False
        if not result['original_state_unchanged']:result['status']='STOPPED_ORIGINAL_STATE_CHANGED'
        conclusions(result);save()
    return result


def main(config, output):
    config=read(config);output=Path(output)
    try:
        ctx=bind(config['comparison_path'])
        import dataiku
        executor=dataiku.SQLExecutor2(connection='AIDP')
        def query(sql):
            frame=executor.query_to_df(sql,infer_from_schema=True,parse_dates=False)
            frame=frame.astype(object).where(frame.notna(),None)
            return [{str(k).upper():v.item() if hasattr(v,'item') else v for k,v in r.items()}
                    for r in frame.to_dict(orient='records')]
        collect(ctx,output,query)
    except Exception as exc:
        write(output/'worker-result.json',{'status':'PREPARATION_STOPPED','error':error(exc),'queries':{},'active':None})


if __name__=='__main__':main(sys.argv[1],sys.argv[2])
