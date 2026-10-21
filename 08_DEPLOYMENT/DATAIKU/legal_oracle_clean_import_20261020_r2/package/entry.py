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
    from lawrag.pipeline import oracle_existing_zip
    return oracle_existing_zip


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['inspect','restore','split','join'])
    parser.add_argument('--archive')
    parser.add_argument('--parts')
    parser.add_argument('--output',required=True)
    args=parser.parse_args();module=load()
    if args.action=='join':
        if not args.parts:parser.error('--parts required')
        result={'joined_zip':module.join(args.parts,args.output)}
    else:
        if not args.archive:parser.error('--archive required')
        if args.action=='inspect':
            result=module.inspect_archive(args.archive)
            result.pop('metadata');result.pop('members')
        elif args.action=='restore':result=module.restore(args.archive,args.output)
        else:result=module.split(args.archive,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
