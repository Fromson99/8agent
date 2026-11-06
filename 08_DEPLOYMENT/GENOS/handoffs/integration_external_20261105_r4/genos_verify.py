#!/usr/bin/env python3
"""Read-only checkout consumer check. Does not certify the code-serving revision."""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
from contextlib import closing
from it35_common import *

def verify(code_root,config_path):
    verify_package();root=Path(code_root).resolve();cfg=read_json(config_path)
    sys.path.insert(0,str(root/'02_BACKEND'))
    os.environ.update(DP='nfs',GENOS_BACKEND='1',GENOS_GENERATION=cfg['source_generation']['path'],
        GENOS_RAG_ONTOLOGY_CONFIG=str(Path(config_path).resolve()),GENOS_RAG_ONTOLOGY_ENABLED='on')
    from semantic_runtime.ontology_work.configuration import repository
    from semantic_runtime.legal_agent.ontology_scenarios import bind_current
    repo=repository();source=Path(cfg['source_generation']['path'])/'store.sqlite'
    sqlite_sources(source);_,rows=snapshot();docs={s['anchor']['document_id'] for s in read_json(PAYLOAD/'sources.json')}
    paths=0
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
        for pub in rows['publication']:
            package=repo.publication(pub['PUB_ID'],docs)['context']['scenario_package'];fragments=[]
            for s in package['originals']:
                a=s['anchor'];text='\n'.join(r[0] for r in db.execute('SELECT text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(a['document_id'],a['unit_id'])))
                fragments.append({**s,'text':text,'evidence_refs':['verification-'+s['id']]})
                if pub['PUB_ID'] not in [r['publication_id'] for r in repo.lookup(a,docs)]:raise ValueError('Consumer lookup failed')
                if repo.lookup(a,set()):raise ValueError('Document scope failed')
            catalog=bind_current(package,fragments)
            if catalog['withheld']:raise ValueError('Source binding withheld')
            paths+=len(catalog['paths'])
    if paths!=inventory()['paths']:raise ValueError('Path count')
    result={'status':'CHECKOUT_ONTOLOGY_READY','code_root':str(root),'configuration_code_sha256':file_sha(root/CONFIG_PATH),
        'source_generation':cfg['source_generation'],'ontology_database_sha256':cfg['database']['sha256'],
        'bundles':inventory()['bundles'],'paths':paths,'field_serving_verified':False,'model_calls':0}
    print(json.dumps(result,ensure_ascii=False,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--code-root',required=True);p.add_argument('--config',required=True);a=p.parse_args();verify(a.code_root,a.config)
