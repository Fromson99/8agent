"""Pinned standalone data tool; does not install or modify the serving checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

HERE=Path(__file__).resolve().parent


def load():
    pins=json.loads((HERE/'CODE_PINS.json').read_text())
    for name,sha in pins.items():
        path=HERE/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise RuntimeError('CODE_PIN: '+name)
    backend=HERE/'runtime'
    for name,module in list(sys.modules.items()):
        if name=='lawrag' or name.startswith('lawrag.') or name=='semantic_runtime' or name.startswith('semantic_runtime.'):
            f=getattr(module,'__file__',None)
            if f and not Path(f).resolve().is_relative_to(backend):raise RuntimeError('KERNEL_BINDING: use a fresh kernel for this notebook')
    sys.path.insert(0,str(backend))
    from lawrag.pipeline import oracle_full_package
    return oracle_full_package


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['check','export','restore'])
    parser.add_argument('--generation',default='/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation')
    parser.add_argument('--output',required=True)
    parser.add_argument('--parts')
    parser.add_argument('--seconds',type=int,default=21600)
    args=parser.parse_args()
    module=load();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    # One data worker; thread only emits elapsed-time heartbeat while hashing.
    stop=threading.Event();started=time.monotonic()
    def heartbeat():
        while not stop.wait(15):print('작업 중 / elapsed_seconds=',int(time.monotonic()-started),flush=True)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        if args.action=='check':
            root,paths,info=module.inventory(args.generation)
            source_bytes=sum(item['bytes'] for item in info['files'].values())
            result={'status':'SOURCE_READABLE','generation':str(root),'dataset_version':info['dataset_version'], 'source_counts':info['source_counts'], 'files':info['files'],
                    'declared_input_bytes':source_bytes,'output':str(folder.resolve()),'free_bytes':module.resources(folder),
                    'scope':'whole declared generation, including source/assets/query projections','code_serving_revision':'not accessed'}
            module.io.atomic_json(folder/'source-check.json',result)
        elif args.action=='export':result=module.export(args.generation,folder,seconds=args.seconds)
        else:
            if not args.parts:parser.error('--parts is required for restore')
            result={'restored_generation':module.restore(args.parts,folder)}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:stop.set();thread.join(timeout=1)

if __name__=='__main__':main()
