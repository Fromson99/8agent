#!/usr/bin/env python3
"""Offline readiness check for GENOS document navigation; no model/network calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'02_BACKEND'))
sys.path.insert(0, str(ROOT))


def check():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env', override=False)
    from semantic_runtime.contracts import Contracts, sha
    from semantic_runtime.document_browser import documents
    from semantic_runtime.navigation_agent import glossary_assets
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.storage import Store
    import service
    result = {'schema_version':'genos-document-tools-readiness-v1', 'network_calls':0,
              'model_calls':0, 'quality_certified':False, 'checks':[], 'ready':False}

    def record(name, action):
        try:
            value=action();result['checks'].append({'name':name,'ok':True,'result':value})
            return value
        except Exception as exc:
            result['checks'].append({'name':name,'ok':False,'error_type':type(exc).__name__,'error':str(exc)})
            return None

    def code():
        path=ROOT/'CODE_MANIFEST.json'
        if not path.is_file():raise ValueError('Install the supplied code bundle first (CODE_MANIFEST.json missing)')
        manifest=json.loads(path.read_text());bad=[]
        for row in manifest['files']:
            p=(ROOT/row['path']).resolve();p.relative_to(ROOT)
            if not p.is_file() or sha(p)!=row['sha256']:bad.append(row['path'])
        if bad:raise ValueError('Installed code differs: '+', '.join(bad))
        contracts=Contracts(ROOT)
        for entry in contracts.pipeline['engines'].values():
            p=ROOT/entry['manifest']
            if sha(p)!=entry['sha256']:raise ValueError('engine manifest mismatch')
            for name,expected in json.loads(p.read_text())['files'].items():
                if sha(ROOT/name)!=expected:raise ValueError('engine dependency mismatch: '+name)
        return {'files':len(manifest['files']),'manifest_sha256':sha(path),'python':sys.version.split()[0]}
    record('installed_code',code)

    def settings():
        if os.environ.get('SEMANTIC_LLM_BACKEND')!='genos':raise ValueError('Set SEMANTIC_LLM_BACKEND=genos')
        if os.environ.get('GENOS_RAG_IMPLEMENTATION')!='document-navigation-v1':raise ValueError('Set GENOS_RAG_IMPLEMENTATION=document-navigation-v1')
        from semantic_runtime.genos import from_env
        target, _ = from_env('llm')
        if not target.headers.get('Authorization'):raise ValueError('Missing setting name: GENOS_LLM_KEY')
        return {'backend':'genos','implementation':'document-navigation-v1','credentials_present':True}
    record('settings',settings)

    def generation():
        binding=service._explicit_generation() or service._data_generation()
        if binding is None:raise ValueError('Set GENOS_GENERATION or GENOS_DATA_ROOT with CURRENT; local-release fallback is not a GENOS generation')
        _,path,selected=binding
        with_store=Store(path)
        try:
            pipeline=Pipeline(ROOT,with_store,implementation='document-navigation-v1')
            index=pipeline.term_agent.get_index()
            glossary=glossary_assets(path,pipeline.term_agent.config)
            try:glossary.check_unchanged()
            finally:glossary.close()
            catalogue=documents(with_store,limit=1)
            return {'generation_id':with_store.manifest['generation_id'], 'mode':selected['mode'],
                    'store_sha256':with_store.manifest['store_sha256'], 'documents':catalogue['total'],
                    'unknown_category_count':catalogue['unknown_category_count'],
                    'index_schema':index.manifest['schema_version']}
        finally:with_store.close()
    record('selected_generation_and_glossary',generation)
    result['ready']=all(row['ok'] for row in result['checks'])
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=check();print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['ready'] else 2


if __name__=='__main__':raise SystemExit(main())
