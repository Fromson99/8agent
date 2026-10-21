"""Pinned standalone data tool; does not install or modify the serving checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

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
    from lawrag.pipeline import oracle_query_package
    return oracle_query_package


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['check','export','restore'])
    parser.add_argument('--generation',default='/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation')
    parser.add_argument('--output',required=True)
    parser.add_argument('--parts')
    parser.add_argument('--seconds',type=int,default=21600)
    parser.add_argument('--resume-r1',action='store_true')
    args=parser.parse_args()
    module=load();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    try:
        if args.action=='check':
            with module.tracking(folder,lambda status,**fields:module.event(folder,status,**fields)):
                module.report('SOURCE_HASH_CHECK')
                root,manifest,items,files,selection=module.immutable_inputs(args.generation)
            source_bytes=sum((root/name).stat().st_size for name in files)
            result={'status':'SOURCE_READABLE','generation':str(root),'dataset_version':files['manifest.json'],
                    'declared_input_bytes':source_bytes,'output':str(folder.resolve()),'free_bytes':module.resources(folder),
                    'oracle_source_completion':'checked later in Dataiku','code_serving_revision':'not accessed'}
            module.io.atomic_json(folder/'source-check.json',result)
        elif args.action=='export':result=module.export(args.generation,folder,seconds=args.seconds,resume_r1=args.resume_r1,direct_parts=True)
        else:
            if not args.parts:parser.error('--parts is required for restore')
            result={'restored_db':module.restore(args.parts,folder)}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:pass

if __name__=='__main__':main()
