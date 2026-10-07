"""File entrypoint keeps multiprocessing spawn safe; build a new inactive generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dev',type=Path,default=Path.home()/'DEV');parser.add_argument('--source',required=True,type=Path);parser.add_argument('--glossary',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    dev=args.dev.resolve();os.environ['LAWRAG_WORKSPACE_ROOT']=str(dev);sys.path.insert(0,str(dev/'02_BACKEND'))
    from lawrag.pipeline.term_generation import build_generation
    from semantic_runtime.contracts import sha
    from lawrag.pipeline.term_serving_bundle import verify_assets
    from semantic_runtime.navigation_storage import verify_build
    print(json.dumps({'stage':'build.start','sys_executable':sys.executable,'python_version':sys.version,'dev':str(dev),'source':str(args.source.resolve()),'source_sha256':sha(args.source),'glossary':str(args.glossary.resolve()),'output':str(args.output.resolve()),'activation':False},ensure_ascii=False),flush=True)
    result=build_generation(args.source,args.glossary,args.output,serving=True)
    verify_build(args.output);verify_assets(args.output/'generation')
    print(json.dumps({'stage':'build.verified','result':result,'git_push':'not_run','serving_revision':'not_deployed','workflow_test':'not_run'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
