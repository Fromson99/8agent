"""Existing pipeline's bounded nightly log -> concept experience builder."""
from __future__ import annotations
from semantic_runtime.legal_agent.shortcut_store import selected_store

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import jsonschema
from lawrag.core.action_memory import Memory, episode_from_journal, concept_input, concept_schema, CONCEPT_SYSTEM, now, digest
from lawrag.platform.workspace import load_layout

KST=ZoneInfo('Asia/Seoul')

def _generate_child(connection,model,episodes,concepts,seconds,output):
    try:
        connection.send({'ok':True,'value':model.generate(episodes,concepts,seconds,output)})
    except Exception as exc:
        connection.send({'ok':False,'error_type':type(exc).__name__})
    finally: connection.close()

def bounded_generate(model,episodes,concepts,seconds,output):
    """Hard elapsed deadline, independent of remote HTTP keepalive behavior."""
    context=multiprocessing.get_context('fork')
    parent,child=context.Pipe(duplex=False)
    process=context.Process(target=_generate_child,args=(child,model,episodes,concepts,seconds,output))
    process.start();child.close()
    try:
        if not parent.poll(max(0,seconds)): raise TimeoutError('concept model elapsed deadline')
        value=parent.recv()
        if not value['ok']: raise RuntimeError('concept worker: '+value['error_type'])
        return value['value']
    finally:
        parent.close()
        if process.is_alive(): process.terminate()
        process.join(timeout=1)
        if process.is_alive(): process.kill();process.join(timeout=1)

def window(at=None):
    at=(at or datetime.now(timezone.utc)).astimezone(KST)
    end=at.replace(hour=6,minute=0,second=0,microsecond=0)
    start=at.replace(hour=0,minute=0,second=0,microsecond=0)
    return {'timezone':'Asia/Seoul','inside':start<=at<end,'now':at.isoformat(),
            'end':end.isoformat(),'seconds_left':max(0,(end-at).total_seconds()),'night_id':start.date().isoformat()}

def atomic_json(path,value):
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w') as f:
        f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def emit(directory,kind,value):
    row={'at':now(),'kind':kind,**value}
    with (directory/'build.jsonl').open('a') as f:
        f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()

class PublicModel:
    """Revalidate each log's original public question grant before any export."""
    def __init__(self,root,output):
        from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
        self.transport=LocalGemmaTransport(root,root);self.output=output
    def eligible(self,episode):
        b=episode['binding'];r=b.get('external_authorization') or {}
        try:
            receipt=self.transport.authorize({'scope':b['scope']},{'use_llm':True},b,
                                             public_question=r.get('public_question_asserted') is True)
            return receipt==r
        except Exception: return False
    def generate(self,episodes,concepts,remaining,output):
        if not all(self.eligible(e) for e in episodes): raise ValueError('episode is not authorised for current public model')
        schema=concept_schema(episodes,concepts);payload={
            'model':self.transport.binding['model'],'temperature':0,'max_tokens':4096,'stream':False,
            'chat_template_kwargs':{'enable_thinking':False},
            'messages':[{'role':'system','content':CONCEPT_SYSTEM},{'role':'user','content':json.dumps({'input':concept_input(episodes,concepts),'output_schema':schema},ensure_ascii=False)}],
            'response_format':{'type':'json_schema','json_schema':{'name':'ActionConceptBatch','strict':True,'schema':schema}}}
        output.mkdir(parents=True,exist_ok=False);atomic_json(output/'request.json',payload)
        try: raw=self.transport.send_once(body=payload,ticket={'remaining_seconds':remaining})
        except Exception as exc:
            if getattr(exc,'response',None): atomic_json(output/'response.json',exc.response)
            raise
        atomic_json(output/'response.json',raw)
        value=json.loads(raw['body_json']['choices'][0]['message']['content']);jsonschema.validate(value,schema)
        atomic_json(output/'output.json',value);return value

def negative_feedback(runtime):
    """Only native hash-bound feedback; old incompatible feedback remains intact."""
    import hashlib
    negatives={}
    for path in (runtime/'feedback').glob('*.json'):
        try:
            e=json.loads(path.read_text())['event'];target=e['target'];run=Path(target['run_path'])
            if run.resolve().parent!=(runtime/'runs').resolve(): continue
            if hashlib.sha256(run.read_bytes()).hexdigest()!=target['run_sha256']: continue
            if e['signal'] in ('MISSING_EVIDENCE','DATA_ERROR','STALE_GENERATION','BAD_ANSWER','WRONG_ANSWER','IRRELEVANT'):
                ident=json.loads(run.read_text()).get('run_id',run.stem)
                negatives.setdefault(ident,[]).append({'event_id':e['id'],'signal':e['signal'],'reason':e['reason']})
        except (ValueError,KeyError,OSError): continue
    return negatives

def build(root,*,runtime=None,max_seconds=120,batch_size=4,model=None,manual=False,at=None):
    layout=load_layout(root);runtime=Path(runtime or layout.path('runtime')/'semantic')
    directory=runtime/'action-memory';directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
    w=window(at)
    if not w['inside'] and not manual:
        value={'state':'OUTSIDE_WINDOW','window':w,'updated_at':now()}
        emit(directory,'BUILD_SKIPPED',value);atomic_json(directory/'last-invocation.json',value)
        return value
    # No background process can continue beyond06:00. Timeout is passed to model.
    deadline=time.monotonic()+min(max_seconds,w['seconds_left'] if not manual else max_seconds)
    with (directory/'build.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return {'state':'ALREADY_RUNNING','window':w}
        memory=Memory(directory/'memory.sqlite');(directory/'memory.sqlite').chmod(0o600);started=now();stamp=str(time.time_ns())
        counts={'journals_seen':0,'unchanged_journals':0,'new_episodes':0,'unusable_journals':0,'built_episodes':0,'waiting_authorization':0,'errors':0,'model_calls':0}
        def remaining():
            wall=window()
            return min(deadline-time.monotonic(),wall['seconds_left'] if not manual else max_seconds)
        def save(state,**extra):
            value={'state':state,'started_at':started,'updated_at':now(),'window':w,'counts':counts.copy(),**memory.status(),**extra}
            if state in {'COMPLETED','FAILED','WAITING_MODEL'}:
                from lawrag.pipeline.legal_llm_wiki import export_wiki
                try:
                    value['legal_llm_wiki']=export_wiki(memory,directory/'legal_llm_wiki')
                except (ValueError,OSError,sqlite3.Error) as exc:
                    value['legal_llm_wiki']={'state':'FAILED','error_type':type(exc).__name__}
                    emit(directory,'WIKI_EXPORT_FAILED',{'error_type':type(exc).__name__})
                    value['state']='FAILED'
            atomic_json(directory/'status.json',value)
            text=f"# RAG 개념 경로 야간 구축\n\n상태: {state}\n갱신: {value['updated_at']}\n작업 시간: 한국시간 00:00~06:00\n\n"
            text+='\n'.join(f'- {k}: {v}' for k,v in counts.items())+'\n\n개념: '+str(value['concepts'])+'\n관계: '+json.dumps(value['relations'],ensure_ascii=False)+'\n'
            text+='\nGUIDES_TO는 조사 경험이다. EXCLUDES는 원문·검증 근거가 있는 관계만 적용한다.\n'
            (directory/'STATUS.md').write_text(text)
            return value
        try:
            emit(directory,'BUILD_STARTED',{'build_id':stamp,'window':w});save('INGESTING')
            negative=negative_feedback(runtime)
            for path in sorted((runtime/'legal-agent/runs').glob('*/*/journal.sqlite')):
                if remaining()<1: break
                counts['journals_seen']+=1
                signature=digest({'files':[(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in (path,path.with_name(path.name+'-wal')) if p.exists()],
                                  'feedback':negative.get(path.parent.name,[])})
                old=memory.db.execute('SELECT signature FROM intake_cursor WHERE path=?',(str(path.resolve()),)).fetchone()
                if old and old[0]==signature:
                    counts['unchanged_journals']+=1;continue
                try:
                    e=episode_from_journal(path,negative.get(path.parent.name,()))
                    if e is None: counts['unusable_journals']+=1
                    else: counts['new_episodes']+=int(memory.ingest(e))
                    if e is not None:
                        with memory.transaction(): memory.db.execute('INSERT OR REPLACE INTO intake_cursor VALUES(?,?)',(str(path.resolve()),signature))
                except (ValueError,sqlite3.Error,OSError) as exc:
                    counts['errors']+=1;emit(directory,'INGEST_ERROR',{'journal':str(path),'error_type':type(exc).__name__})
            save('GENERATING')
            if model is None:
                try: model=PublicModel(Path(root),directory/'calls')
                except Exception as exc:
                    emit(directory,'MODEL_NOT_READY',{'error_type':type(exc).__name__});return save('WAITING_MODEL',model_ready=False)
            pending=memory.pending(batch_size);eligible=[e for e in pending if model.eligible(e)]
            counts['waiting_authorization']=len(pending)-len(eligible)
            for e in pending:
                if e not in eligible:
                    with memory.transaction():
                        memory.db.execute("UPDATE episode SET state='WAITING_AUTH',updated_at=? WHERE id=?",(now(),e['id']))
                        memory.event('WAITING_AUTH',{'episode_id':e['id']})
            if eligible and remaining()>2:
                concepts=memory.catalogue(eligible[0]['binding'],sorted({d for e in eligible for d in e['binding']['scope']['document_version_ids']}));counts['model_calls']+=1
                emit(directory,'MODEL_STARTED',{'build_id':stamp,'episode_ids':[e['id'] for e in eligible],'timeout_seconds':remaining()})
                try:
                    value=bounded_generate(model,eligible,concepts,max(.1,remaining()-2),directory/'calls'/stamp)
                    jsonschema.validate(value,concept_schema(eligible,concepts))
                    delivered={e['id'] for e in concept_input(eligible,concepts)['episodes'] if e.get('originals')}
                    if any(c['episode_id'] not in delivered for c in value['exclusion_candidates']):
                        raise ValueError('exclusion original was not delivered to this model call')
                    if remaining()>0:
                        memory.adopt(value['assignments'],value['exclusion_candidates']);covered={a['episode_id'] for a in value['assignments']}
                        counts['built_episodes']=len(covered)
                        for e in eligible:
                            if e['id'] not in covered:
                                with memory.transaction():
                                    memory.db.execute("UPDATE episode SET state='ABSTAINED',updated_at=? WHERE id=?",(now(),e['id']))
                        emit(directory,'MODEL_FINISHED',{'build_id':stamp,'built_episodes':len(covered)})
                    else: emit(directory,'DEADLINE_OUTPUT_DEFERRED',{'build_id':stamp})
                except Exception as exc:
                    counts['errors']+=1
                    with memory.transaction():
                        for e in eligible: memory.db.execute("UPDATE episode SET state='FAILED',error=?,updated_at=? WHERE id=?",(type(exc).__name__,now(),e['id']))
                    emit(directory,'MODEL_FAILED',{'build_id':stamp,'error_type':type(exc).__name__})
            value=save('FAILED' if counts['errors'] else 'COMPLETED',model_ready=True)
            emit(directory,'BUILD_FINISHED',{'build_id':stamp,'state':value['state'],'counts':counts});return value
        finally: memory.close()

def main(argv=None):
    if argv is None:
        import sys
        argv = sys.argv[1:]
    if argv[:1] and argv[0] in ('diagnose', 'propose', 'comparison-plan', 'compare'):
        from .failure_improvement import main as improvement_main
        return improvement_main(argv)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','status','wiki-export','wiki-status','wiki-check','wiki-unlink','wiki-retire']);p.add_argument('--root',default=str(Path(__file__).resolve().parents[3]));p.add_argument('--runtime');p.add_argument('--max-seconds',type=int,default=120);p.add_argument('--batch-size',type=int,default=4);p.add_argument('--manual',action='store_true',help='Explicit daytime smoke test; scheduled builds never use this.')
    p.add_argument('--observation-id');p.add_argument('--concept-id');p.add_argument('--episode-id')
    p.add_argument('--reason',default='');p.add_argument('--reviewer',default='')
    p.add_argument('--abstraction-status',choices=['DISPUTED','RETRACTED'],default='RETRACTED')
    p.add_argument('--mode',choices=['legacy','shortcut-v4'],default='legacy')
    p.add_argument('--generation',type=Path);p.add_argument('--model-profile',type=Path);p.add_argument('--principal',type=Path)
    a=p.parse_args(argv)
    if not 1<=a.batch_size<=8 or not 1<=a.max_seconds<=300: p.error('batch-size1..8 and max-seconds1..300 required')
    runtime=Path(a.runtime) if a.runtime else load_layout(a.root).path('runtime')/'semantic'
    if a.mode=='shortcut-v4':
        from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
        path=selected_store(runtime)
        if not path.is_file():print(json.dumps({'state':'NOT_BUILT'}));return 1
        if a.command=='status':
            repo=ShortcutRepository(path)
            try:value=repo.status()
            finally:repo.close()
        elif a.command=='build':
            schedule=window()
            if not a.manual and not schedule['inside']:
                print(json.dumps({'state':'OUTSIDE_WINDOW','window':schedule}));return 0
            if not a.manual:a.max_seconds=min(a.max_seconds,max(1,int(schedule['seconds_left'])))
            if not a.generation or not a.model_profile or not a.principal:p.error('--generation, --model-profile and trusted --principal required')
            from semantic_runtime.storage import Store
            from semantic_runtime.pipeline import Pipeline
            from .legal_wiki_compiler import build_with_pipeline
            profile=json.loads(a.model_profile.read_text());principal=json.loads(a.principal.read_text())
            if profile.get('model_binding',{}).get('trust_zone')!='internal':p.error('CLI compiler requires selected internal transport; external research uses ExperimentClient')
            if not principal.get('authenticated'):p.error('trusted authenticated principal required')
            store=Store(a.generation)
            try:
                pipeline=Pipeline(Path(a.root),store,object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile)
                def principal_for(scope):
                    repo=ShortcutRepository(path)
                    try:
                        if repo.scope(principal)!=scope:raise ValueError('scope is not authorized by this worker principal')
                    finally:repo.close()
                    return principal
                repo=ShortcutRepository(path)
                try:worker_scope=repo.scope(principal)
                finally:repo.close()
                features=pipeline.contracts.pipeline.get('shortcut_v4',{}).get('features',{})
                if not features.get('compile'):raise ValueError('shortcut compiler feature is disabled')
                with (runtime/'case-memory'/'.wiki-worker').open('a') as worker_lock:
                    fcntl.flock(worker_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    from semantic_runtime.legal_agent.shortcut_store import store_owner
                    with store_owner(runtime):
                        value=build_with_pipeline(pipeline,runtime,principal_for_scope=principal_for,batch_size=a.batch_size,max_seconds=a.max_seconds,scope=worker_scope)
                atomic_json(runtime/'case-memory'/'compiler-status.json',value)
            finally:store.close()
        else:p.error('shortcut-v4 supports build/status; projection uses unified-memory wiki-rebuild')
        print(json.dumps(value,ensure_ascii=False,indent=2));return 1 if any(x.get('status')=='FAILED' for x in value.get('results',[])) else 0
    if a.command.startswith('wiki-'):
        from lawrag.pipeline.legal_llm_wiki import operate
        try:
            value=operate(runtime/'action-memory',a.command,observation_id=a.observation_id,
                          concept_id=a.concept_id,episode_id=a.episode_id,reason=a.reason,
                          reviewer=a.reviewer,status=a.abstraction_status)
        except (ValueError,OSError,sqlite3.Error) as exc:
            print(json.dumps({'state':'FAILED','error':str(exc)},ensure_ascii=False));return 1
        print(json.dumps(value,ensure_ascii=False,indent=2))
        return 1 if value.get('ok') is False else 0
    if a.command=='build': value=build(a.root,runtime=runtime,max_seconds=a.max_seconds,batch_size=a.batch_size,manual=a.manual)
    else:
        path=runtime/'action-memory/status.json';value=json.loads(path.read_text()) if path.exists() else {'state':'NOT_BUILT','window':window()}
    print(json.dumps(value,ensure_ascii=False,indent=2))
    return 1 if value['state']=='FAILED' else 0

if __name__=='__main__': raise SystemExit(main())
