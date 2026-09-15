#!/usr/bin/env python3
"""Standalone GENOS package orchestration; does not read or change repository MAIN."""
import argparse,importlib.util,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def authoring():
    p=ROOT/'06_TOOLS/OFFLINE/genos_authoring.py'
    spec=importlib.util.spec_from_file_location('genos_authoring',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def package_paths():
    return ROOT/'data/structured-prellm.sqlite',ROOT/'runs/authoring'

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    source,queue=package_paths()
    for name in ['prepare','run','status','publish','serve','retry','rework','doctor']:
        cmd=sub.add_parser(name)
        if name in ['prepare','run','status','publish','retry','rework']:cmd.add_argument('--queue',default=str(queue))
        if name in ['prepare','run','publish']:cmd.add_argument('--source-db',default=str(source))
        if name in ['prepare','run']:
            cmd.add_argument('--model',default=os.environ.get('GENOS_LLM_MODEL'))
            cmd.add_argument('--endpoint',default=os.environ.get('GENOS_LLM_URL'))
            cmd.add_argument('--model-revision',default=os.environ.get('GENOS_LLM_REVISION'))
            cmd.add_argument('--authority-generation',default='genos-structured-prellm-v1')
            cmd.add_argument('--max-attempts',type=int,default=3)
            cmd.add_argument('--segment-chars',type=int,default=12000)
            cmd.add_argument('--max-tokens',type=int,default=8192)
        if name=='run':
            cmd.add_argument('--execute',action='store_true')
            cmd.add_argument('--max-calls',type=int,default=10)
            cmd.add_argument('--workers',type=int,default=1)
            cmd.add_argument('--timeout',type=float,default=300)
        if name=='status':
            cmd.add_argument('--watch',type=float,default=0);cmd.add_argument('--json',action='store_true');cmd.add_argument('--failures',type=int,default=5)
        if name=='publish':
            cmd.add_argument('--output',required=True);cmd.add_argument('--allow-partial',action='store_true')
        if name=='serve':
            cmd.add_argument('--generation',required=True);cmd.add_argument('--host',default='127.0.0.1');cmd.add_argument('--port',type=int,default=5566)
            cmd.add_argument('--runtime-dir',default=str(ROOT/'runs/server'))
        if name in ['retry','rework']:
            cmd.add_argument('--job-id',required=True);cmd.add_argument('--reason',required=True)
            if name=='retry':cmd.add_argument('--additional-attempts',type=int,default=1)
    args=p.parse_args()
    if args.command=='status':
        import genos_progress
        argv=['--queue',args.queue,'--watch',str(args.watch),'--failures',str(args.failures)]
        return genos_progress.main(argv+(['--json'] if args.json else []))
    if args.command=='doctor':
        import sqlite3,importlib.metadata,subprocess
        if sys.version_info<(3,11):raise ValueError('Python 3.11 or newer is required')
        subprocess.run([sys.executable,str(ROOT/'verify_package.py')],check=True)
        with sqlite3.connect(':memory:') as c:c.execute("create virtual table check_fts using fts5(text,tokenize='trigram')")
        sys.path.insert(0,str(ROOT/'02_BACKEND'))
        from semantic_runtime.contracts import Contracts,sha
        contracts=Contracts(ROOT)
        for entry in contracts.pipeline['engines'].values():
            path=ROOT/entry['manifest'];assert sha(path)==entry['sha256'],path
            for rel,h in json.loads(path.read_text())['files'].items():assert sha(ROOT/rel)==h,rel
        for name in ['requests','jsonschema','fastapi','uvicorn','httpx','python-dotenv','anthropic']:
            print(name,importlib.metadata.version(name))
        print('PASS: package/contracts/engine hashes/SQLite FTS5; no model request made');return 0
    if args.command=='serve':
        import uvicorn
        sys.path.insert(0,str(ROOT/'02_BACKEND'))
        from semantic_runtime.app import create_app
        from semantic_runtime.provider import Haiku
        class SourceOnly(Haiku):
            def call(self,*a,**kw):raise ValueError('LLM answers require SEMANTIC_LLM_ENDPOINT (internal Haiku service); source-only search is available')
        work=Path(args.runtime_dir).resolve();endpoint=os.environ.get('SEMANTIC_LLM_ENDPOINT')
        provider=(Haiku(work,work/'90_RUNTIME/semantic/provider',False,backend='openai-compatible',endpoint=endpoint,trust_zone='internal') if endpoint else SourceOnly(work,work/'90_RUNTIME/semantic/provider'))
        app=create_app(work,Path(args.generation).resolve(),contracts_root=ROOT,provider=provider)
        uvicorn.run(app,host=args.host,port=args.port);return 0
    m=authoring()
    if args.command in ['prepare','run']:
        path=Path(args.queue)
        if not (path/'queue.sqlite').is_file():
            if not all([args.model,args.endpoint,args.model_revision]):p.error('set GENOS_LLM_URL, GENOS_LLM_MODEL and GENOS_LLM_REVISION first')
            # No source conversion on GENOS: only bind model identity and prepare durable segmented jobs.
            m.prepare(path,Path(args.source_db),m.EXTRACT_SYSTEM,m.contract_module().profile_schema('OBSERVATION',m.ROOT),
                      model=args.model,revision=args.model_revision,endpoint=args.endpoint,authority_generation=args.authority_generation,
                      max_attempts=args.max_attempts,segment_chars=args.segment_chars,max_tokens=args.max_tokens)
        elif args.command=='prepare':raise ValueError('Queue already prepared; use run/status to preserve progress')
        q=m.Queue(path)
        if args.command=='prepare':result=q.status()
        else:
            if args.model and args.model!=q.identity['model']:raise ValueError('model differs from existing queue')
            if args.endpoint and m.endpoint_url(args.endpoint)!=q.identity['endpoint']:raise ValueError('endpoint differs from existing queue')
            if args.model_revision and args.model_revision!=q.identity['model_revision']:raise ValueError('revision differs from existing queue')
            if args.execute and not args.model_revision:p.error('set the frozen GENOS_LLM_REVISION to resume execution')
            if args.model_revision:os.environ['GENOS_LLM_REVISION']=args.model_revision
            result=m.run(q,execute=args.execute,max_calls=args.max_calls,workers=args.workers,timeout=args.timeout)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if args.command=='run' and args.execute and any(n for state,n in result['jobs'].items() if state not in ('REVIEW_PASSED_CANDIDATE','SUPERSEDED_BY_REWORK')):
            return 2
        return 0
    q=m.Queue(args.queue)
    if args.command=='publish':
        out=Path(args.output).resolve()
        if out.exists():raise ValueError('New immutable output path required')
        handoff=out.with_name(out.name+'-handoff')
        q.handoff(handoff,allow_partial=args.allow_partial)
        result=m.load_handoff(ROOT,Path(args.source_db),handoff,out)
        print(json.dumps({'generation':str(out),'handoff':str(handoff),'data_status':'DRAFT'},ensure_ascii=False,indent=2))
    elif args.command=='retry':q.retry(args.job_id,args.reason,args.additional_attempts);print(json.dumps(q.status(),ensure_ascii=False))
    elif args.command=='rework':print(q.rework(args.job_id,args.reason))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,FileNotFoundError) as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
