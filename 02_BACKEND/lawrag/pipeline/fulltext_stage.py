"""Rebuild only FTS on an explicitly completed immutable navigation generation."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import tempfile
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from semantic_runtime.contracts import sha, write
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime import fulltext


def derive(generation, output, *, granularity='unit', workers=2):
    generation,output=Path(generation).resolve(),Path(output).resolve()
    if generation==output or generation.is_relative_to(output) or output.is_relative_to(generation):
        raise ValueError('fulltext output must be separate from its parent generation')
    if granularity not in {'article','unit'}: raise ValueError('invalid fulltext granularity')
    if any(p.is_symlink() for p in generation.rglob('*')): raise ValueError('generation symlinks rejected')
    with closing(Store(generation)) as store:
        nav=(generation/store.manifest['navigation']['path']).resolve();nav.relative_to(generation)
        if sha(nav/'manifest.json')!=store.manifest['navigation']['manifest_sha256']:
            raise ValueError('parent navigation manifest mismatch')
        TermIndex(nav,store)
        parent=store.manifest
    pins={str(p.relative_to(generation)):sha(p) for p in (generation/'manifest.json',generation/'store.sqlite',nav/'manifest.json',nav/'navigation.sqlite')}
    from semantic_runtime import unit_fulltext
    identity={'parent_generation':str(generation),'parent_pins':pins,'granularity':granularity,
              'builder_sha256':sha(__file__),'fulltext_builder_sha256':sha(fulltext.__file__),
              'unit_builder_sha256':sha(unit_fulltext.__file__) if granularity=='unit' else None,
              'workers':workers,'tokenizer_version':fulltext.tokenizer_version()}
    if output.exists():
        receipt=json.loads((output/'fulltext-stage.json').read_text())
        if receipt['identity']!=identity: raise ValueError('fulltext stage inputs/code changed; use a new output')
        if not receipt.get('completed') or sha(output/'manifest.json')!=receipt['manifest_sha256']:
            raise ValueError('completed fulltext generation manifest changed')
        if any(sha(output/name)!=digest for name,digest in pins.items() if name!='manifest.json'):
            raise ValueError('completed fulltext generation source/navigation changed')
        with closing(Store(output)) as store:
            TermIndex(output/parent['navigation']['path'],store)
            fulltext.open_bound(output,store.manifest['fulltext'],json.loads((nav/'manifest.json').read_text()))
        return receipt
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        # Do not copy/rebuild the previous FTS. Other immutable payloads are retained.
        old_ft=parent.get('fulltext',{}).get('path')
        old_path=(generation/old_ft).resolve() if old_ft else None
        if old_path: old_path.relative_to(generation)
        for child in generation.iterdir():
            if child==old_path or child.name=='fulltext-stage.json':continue
            destination=tmp/child.name
            if child.is_dir():shutil.copytree(child,destination,copy_function=_copy)
            else:_copy(child,destination)
        target=tmp/'fulltext-units' if granularity=='unit' else tmp/'fulltext-rebuilt'
        if target.exists(): raise ValueError('new fulltext path collision')
        manifest=fulltext.build(tmp/parent['navigation']['path'],target,workers,
                                granularity=granularity,generation=tmp)
        updated={**parent,'fulltext':{'path':str(target.relative_to(tmp)),
                    'manifest_sha256':sha(target/'manifest.json'),'navigation_index_sha256':manifest['navigation_index_sha256']},
                 'fulltext_derivation':{'parent_manifest_sha256':pins['manifest.json'],'granularity':granularity}}
        # Manifest is a private copy; original navigation/source pins are unchanged.
        (tmp/'manifest.json').unlink()
        write(tmp/'manifest.json',updated)
        with closing(Store(tmp)) as store:
            TermIndex(tmp/parent['navigation']['path'],store)
            fulltext.open_bound(tmp,updated['fulltext'],json.loads((nav/'manifest.json').read_text()))
        if any(sha(generation/name)!=v for name,v in pins.items()):raise ValueError('parent changed during fulltext build')
        receipt={'schema_version':'fulltext-only-stage-v1','identity':identity,'completed':True,
                 'navigation_rebuilt':False,'structure_rebuilt':False,'glossary_rebuilt':False,
                 'activated':False,'serving_verified':False,'fulltext':updated['fulltext'],
                 'manifest_sha256':sha(tmp/'manifest.json'),'counts':manifest['counts']}
        write(tmp/'fulltext-stage.json',receipt)
        if output.exists():raise ValueError('output appeared during fulltext build')
        os.rename(tmp,output)
        print('FULLTEXT_STAGE VERIFIED '+str(output),flush=True)
        return receipt
    except BaseException:
        # Parent is untouched; incomplete derived data is retained for diagnosis.
        print('FULLTEXT_STAGE incomplete retained '+str(tmp),flush=True)
        raise


def _copy(source,target):
    source,target=Path(source),Path(target)
    if source.suffix=='.sqlite':
        try:os.link(source,target);return str(target)
        except OSError:pass
    return shutil.copyfile(source,target)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--granularity',choices=['unit','article'],default='unit')
    p.add_argument('--workers',type=int,default=2)
    p.add_argument('--log-dir',type=Path)
    args=p.parse_args(argv)
    logdir=args.log_dir or args.output.parent/(args.output.name+'.logs')
    if any(logdir.resolve().is_relative_to(path.resolve()) for path in (args.generation,args.output)):
        raise ValueError('log directory must be outside immutable generations')
    logdir.mkdir(parents=True,exist_ok=True)
    # Append on resume; each attempt has a START/FINISHED or FAILED record.
    with (logdir/'build.log').open('a',encoding='utf-8',buffering=1) as log, (logdir/'progress.jsonl').open('a',encoding='utf-8',buffering=1) as events:
        lock=threading.RLock();stop=threading.Event();state={};started=time.monotonic()
        original_out,original_err=sys.stdout,sys.stderr
        class Tee:
            def __init__(self,stream):self.stream=stream
            def write(self,value):
                with lock:self.stream.write(value);log.write(value)
                return len(value)
            def flush(self):
                with lock:self.stream.flush();log.flush()
        sentinel=object();previous=getattr(fulltext,'_BUILD_PROGRESS',sentinel)
        def report(**value):
            with lock:
                now=time.monotonic()
                if value.get('task')!=state.get('task'):state.clear();state['task_started']=now
                state.update(value)
                row={**value,'time_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':round(now-started,3)}
                events.write(json.dumps(row,ensure_ascii=False)+'\n')
                done,total=state.get('completed'),state.get('total');elapsed=now-state['task_started']
                eta=round((total-done)*elapsed/done,1) if isinstance(done,(int,float)) and done>0 and isinstance(total,(int,float)) else 'not_measured'
                print(f"FULLTEXT {state.get('task')} completed={done}/{total} elapsed={now-started:.1f}s estimated_remaining_seconds={eta}",flush=True)
        def heartbeat():
            while not stop.wait(5):
                with lock:report(**{k:v for k,v in state.items() if k!='task_started'})
        sys.stdout,sys.stderr=Tee(original_out),Tee(original_err)
        fulltext._BUILD_PROGRESS=report
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        try:
            report(task='fulltext-stage',status='START',completed=0,total=None)
            receipt=derive(args.generation,args.output,granularity=args.granularity,workers=args.workers)
            print(json.dumps(receipt,ensure_ascii=False),flush=True)
            report(task='fulltext-stage',status='FINISHED',completed=1,total=1)
        except BaseException:
            traceback.print_exc()
            report(task='fulltext-stage',status='FAILED',completed=0,total=None)
            raise
        finally:
            stop.set();thread.join()
            sys.stdout,sys.stderr=original_out,original_err
            if previous is sentinel:delattr(fulltext,'_BUILD_PROGRESS')
            else:fulltext._BUILD_PROGRESS=previous
