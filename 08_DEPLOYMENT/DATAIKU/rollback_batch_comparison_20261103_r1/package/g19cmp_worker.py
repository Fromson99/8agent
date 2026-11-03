"""Single sequential child. All field mutations are isolated rollback probes."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import sys
import time
import uuid
from g19cmp_common import read,write,error,literal,canonical
from g19cmp_source import sample
from g19cmp_core import (KINDS,POLICIES,MAX_PAYLOAD,row_hash,partitions,pair_order,
    expanded_contract,response_sql,payload_clock,receipt,isolated_rows,integrity_sql,summaries)


def run(config, output):
    ctx=config['context']; output=Path(output); package=Path(ctx['package'])
    result={'status':'RUNNING','trials':[],'source_samples':[],'integrity':[],'skipped':[],
            'queries':0,'active':None,'run_id':config['run_id'],'plan_sha256':config['plan_sha256'],
            'original_loader_status':ctx['state'].get('status'),'binding':ctx['state']['binding'],
            'limits':{'seconds':600,'sql_calls':600,'actual_payload_bytes':MAX_PAYLOAD},
            'scope':'rollback comparisons; no COMMIT/full-load/final verification/embedding/DB capacity prediction'}
    started=time.monotonic(); original_path=Path(ctx['state_dir'])/'state.json'
    before=hashlib.sha256(original_path.read_bytes()).hexdigest()
    def save(): write(output,result)
    def guard():
        if time.monotonic()-started>600: raise ValueError('COMPARISON_TIME_BUDGET')
        if result['queries']>=600: raise ValueError('COMPARISON_SQL_BUDGET')
        if hashlib.sha256(original_path.read_bytes()).hexdigest()!=before: raise ValueError('ORIGINAL_STATE_CHANGED')
        rss=int(Path('/proc/self/status').read_text().split('VmRSS:')[1].split()[0])
        result['max_sampled_rss_kib']=max(result.get('max_sampled_rss_kib',0),rss)
        if rss>768*1024: raise ValueError('COMPARISON_RSS_LIMIT')
        mem=Path('/proc/meminfo').read_text()
        available=int(mem.split('MemAvailable:')[1].split()[0])
        total=int(mem.split('MemTotal:')[1].split()[0])
        if available<max(256*1024,total//20): raise ValueError('HOST_MEMORY_HEADROOM')
    def active(name):
        guard(); result['active']={'name':name,'started_epoch':time.time()};save()
    def end(): result['active']=None;save()
    import dataiku
    executor=dataiku.SQLExecutor2(connection='AIDP')
    def query(name,sql,limit=250):
        active(name); result['queries']+=1
        try:
            frame=executor.query_to_df(sql,infer_from_schema=True,parse_dates=False)
            frame=frame.astype(object).where(frame.notna(),None)
            if len(frame)>limit:raise ValueError('QUERY_RESULT_LIMIT')
            return [{str(k).upper():v.item() if hasattr(v,'item') else v for k,v in r.items()}
                    for r in frame.to_dict(orient='records')]
        finally:end()
    def empty(contract,release):
        sql='SELECT COUNT(*) AS N FROM '+contract.table('SRCH_ROW')+' WHERE '+contract.col('SRCH_ROW',contract.tables['SRCH_ROW']['primary_key'][0])+'='+literal(release)
        if query('isolated release empty',sql)!=[{'N':0}]:raise ValueError('ROLLBACK_NAMESPACE_NOT_EMPTY_NO_AUTO_DELETE')
    try:
        with (Path(ctx['state_dir'])/'job.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if read(original_path)!=ctx['state']:raise ValueError('ORIGINAL_STATE_CHANGED_BEFORE_START')
            sys.path.insert(0,str(package))
            import run as loader
            import jdbc_transport as transport
            if Path(loader.__file__).resolve().parent!=package.resolve() or Path(transport.__file__).resolve().parent!=package.resolve():
                raise ValueError('LOADER_IMPORT_ORIGIN')
            if loader.verify_code()!=ctx['state']['binding']['code']:raise ValueError('INSTALLED_CODE_CHANGED')
            contract=expanded_contract(loader.Contract,package/'contract.json')
            identity=query('DB identity',"SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','SERVICE_NAME') AS SERVICE_NAME FROM DUAL")
            if identity!=ctx['state']['binding']['database']:raise ValueError('DB_IDENTITY_CHANGED')
            class ReadDB:
                def query(self,sql,limit=250):return query('target preflight',sql,limit)
            db=ReadDB()
            if loader.object_binding(db,contract)!=ctx['state']['binding']['objects']:raise ValueError('DB_OBJECTS_CHANGED')
            contract.preflight(db,'SRCH_ROW')
            def execute(sql,binds,mode,nonce,record,clock=True):
                guard(); prep=time.perf_counter()
                payload_bytes=sum(len(v.encode()) for _,v,t in binds if t=='CLOB')
                if payload_bytes>MAX_PAYLOAD:raise ValueError('ACTUAL_PAYLOAD_LIMIT_NO_AUTO_RESIZE')
                rendered=transport.render(sql,binds,write=True)
                if clock:rendered=payload_clock(rendered)
                record.update(render_s=time.perf_counter()-prep,payload_bytes=payload_bytes,
                    sql_bytes=len(rendered.encode()),sql_sha256=hashlib.sha256(rendered.encode()).hexdigest(),status='IN_FLIGHT')
                active('rollback '+mode);result['queries']+=1;start=time.perf_counter()
                try:
                    frame=executor.query_to_df('SELECT 1 AS OK FROM DUAL',pre_queries=[rendered],post_queries=['ROLLBACK'])
                    if mode=='exception':raise ValueError('EXPECTED_DIAGNOSTIC_RECEIPT_MISSING')
                    if len(frame)!=1 or int(frame.iloc[0]['OK'])!=1:raise ValueError('NORMAL_SUCCESS_RESPONSE_UNCONFIRMED')
                    record['server_parts']='UNMEASURED_NORMAL_RESPONSE'
                except Exception as exc:
                    values=receipt(exc,nonce) if mode=='exception' else None
                    if values is None:
                        record.update(status='FAILED_OR_OUTCOME_UNKNOWN',error=error(exc));raise
                    record.update(values)
                finally:
                    record['request_s']=time.perf_counter()-start;end()
            def trial(rows,spans,kind,phase,arm,pair,release,nonce,mode='normal'):
                input_hash=row_hash(rows)
                record={'kind':kind,'phase':phase,'arm':arm,'pair':pair,'rows':len(rows),
                    'source_sha256':input_hash,'probe_release':release,'status':'PREPARING','batches':[]}
                result['trials'].append(record);save();start=time.perf_counter()
                empty(contract,release)
                for begin,finish in spans:
                    active('prepare batch '+kind)
                    prep=time.perf_counter();sql,binds=contract.batch('SRCH_ROW',rows[begin:finish])
                    sql=response_sql(sql,nonce,mode)
                    batch={'begin':begin,'end':finish,'rows':finish-begin,'prepare_s':time.perf_counter()-prep}
                    record['batches'].append(batch);end()
                    execute(sql,binds,mode,nonce,batch)
                    empty(contract,release)
                    batch['status']='ROLLED_BACK_VERIFIED';save()
                if row_hash(rows)!=input_hash:raise ValueError('SOURCE_ROWS_MUTATED')
                record.update(status='ROLLED_BACK_VERIFIED',request_s=sum(b['request_s'] for b in record['batches']),
                    prepare_render_s=sum(b['prepare_s']+b['render_s'] for b in record['batches']),
                    elapsed_s=time.perf_counter()-start,rollback_remaining_rows=0)
                save()
            tables=ctx['descriptor']['tables']
            for kind_index,name in enumerate(KINDS):
                candidates=[(k,v) for k,v in tables.items() if (v.get('table') or k.split('.',1)[-1])==name]
                if len(candidates)!=1:
                    result['skipped'].append({'target':name,'reason':'KIND_ABSENT_OR_AMBIGUOUS'});save();continue
                kind,spec=candidates[0]
                active('source prefix '+kind)
                rows,weights,meta=sample(ctx,loader,'SRCH_ROW',kind)
                meta['planned_rows']=spec['rows'];result['source_samples'].append(meta);end()
                if not rows or len(rows)!=len(weights):
                    result['skipped'].append({'kind':kind,'reason':'SOURCE_UNMEASURED'});save();continue
                original_input=row_hash(rows);meta['original_mapped_sha256']=original_input
                # Bound the response comparison to the same payload, not different row counts.
                release=hashlib.sha256((config['run_id']+kind+'response').encode()).hexdigest()
                response_rows=isolated_rows(rows[:2000],contract,release)
                while response_rows:
                    _,binds=contract.batch('SRCH_ROW',response_rows)
                    size=len(binds[0][1].encode())
                    if size<=2*1024**2:break
                    if len(response_rows)==1:response_rows=[];break
                    response_rows=response_rows[:max(1,min(len(response_rows)-1,int(len(response_rows)*2*1024**2/size*.95)))]
                if not response_rows:
                    result['skipped'].append({'kind':kind,'reason':'RESPONSE_PAYLOAD_UNMEASURED'});save();continue
                trial(response_rows[:16],[(0,min(16,len(response_rows)))],kind,'warmup','normal',-1,release,uuid.uuid4().hex)
                # Three value-preservation checks before timing. No test commits.
                if len(response_rows)>=4:
                    for mode in ('same_rows','conflict','missing'):
                        record={'kind':kind,'mode':mode,'probe_release':release,'status':'PREPARING'}
                        result['integrity'].append(record);save();empty(contract,release)
                        sql,binds=integrity_sql(contract,response_rows,mode)
                        execute(sql,binds,'normal','',record,clock=False)
                        empty(contract,release);record['status']='ROLLED_BACK_VERIFIED';save()
                else:result['skipped'].append({'kind':kind,'reason':'INSUFFICIENT_INTEGRITY_SAMPLE'})
                for pair in range(3):
                    nonce=uuid.uuid4().hex
                    for arm in pair_order(pair,kind_index,'normal','exception'):
                        trial(response_rows,[(0,len(response_rows))],kind,'response',arm,pair,release,nonce,arm)
                batch_release=hashlib.sha256((config['run_id']+kind+'batch').encode()).hexdigest()
                batch_rows=isolated_rows(rows,contract,batch_release)
                plans={arm:partitions(weights,*policy) for arm,policy in POLICIES.items()}
                if plans['baseline']==plans['large']:
                    result['skipped'].append({'kind':kind,'reason':'BATCH_PARTITIONS_IDENTICAL_NO_EFFECT_TEST',
                        'sample_rows':len(rows),'baseline_requests':len(plans['baseline']),'large_requests':len(plans['large'])});save()
                else:
                    meta['batch_plans']={arm:{'requests':len(spans),'max_rows':max(e-b for b,e in spans)} for arm,spans in plans.items()}
                    for pair in range(3):
                        nonce=uuid.uuid4().hex
                        for arm in pair_order(pair,kind_index,'baseline','large'):
                            trial(batch_rows,plans[arm],kind,'batch',arm,pair,batch_release,nonce)
                if row_hash(rows)!=original_input:raise ValueError('ORIGINAL_SAMPLE_MUTATED')
                del rows,weights,response_rows,batch_rows
            result['status']='COMPLETE' if not result['skipped'] else 'PARTIAL'
    except Exception as exc:
        result['status']='STOPPED';result['error']=error(exc)
        result['reason']=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]{1,180}',str(exc)) else type(exc).__name__
    finally:
        after=hashlib.sha256(original_path.read_bytes()).hexdigest()
        result['original_state_sha256_before']=before;result['original_state_sha256_after']=after
        result['original_state_unchanged']=before==after
        if before!=after:result['status']='STOPPED_ORIGINAL_STATE_CHANGED'
        for trial_record in result['trials']:
            if trial_record['status']=='PREPARING':trial_record['status']='INCOMPLETE_NO_RETRY'
        result['active']=None;result['elapsed_s']=time.monotonic()-started
        try:result['summaries']=summaries(result['trials'])
        except ValueError as exc:result['status']='STOPPED_PAIRED_SOURCE_MISMATCH';result['summary_error']=str(exc)
        save()


if __name__=='__main__':run(read(sys.argv[1]),Path(sys.argv[2]))
