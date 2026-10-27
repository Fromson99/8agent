"""Read a local operator-owned request journal; never expose provider wire payloads."""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from semantic_runtime.contracts import digest


def read_trace(runtime,run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',run_id): raise ValueError('invalid run ID')
    root=Path(runtime).resolve(strict=True)
    found=list((root/'legal-agent/runs').glob('*/'+run_id+'/journal.sqlite'))
    if len(found)!=1: raise ValueError('run must resolve uniquely in explicit runtime root')
    path=found[0].resolve(strict=True); path.relative_to(root)
    if path.stat().st_uid!=os.getuid(): raise ValueError('journal must be owned by current operator')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        if db.execute('PRAGMA user_version').fetchone()[0] not in (3,4,5): raise ValueError('v3/v4/v5 trace required')
        run=dict(db.execute('SELECT * FROM run').fetchone()); binding=json.loads(run['binding_json'])
        if run['run_id']!=run_id or digest(binding)!=run['binding_hash']: raise ValueError('run binding mismatch')
        events=[]
        for r in db.execute('SELECT seq,kind,payload_json,payload_hash FROM event ORDER BY seq'):
            if digest(json.loads(r['payload_json']))!=r['payload_hash']: raise ValueError('event hash mismatch')
            events.append({'seq':r['seq'],'kind':r['kind'],'hash':r['payload_hash']})
        actions=[]
        for r in db.execute('SELECT * FROM action_context ORDER BY created_seq'):
            proposal=json.loads(r['proposed_json'])
            if digest(proposal)!=r['proposal_hash']: raise ValueError('action hash mismatch')
            actions.append({'action_id':r['action_id'],'actor':r['actor'],'proposal':proposal,'status':r['status'],
                'parent_action_id':r['parent_action_id'],'input_view_id':r['input_view_id'],
                'result':json.loads(r['result_json'] or '{}')})
        versions=[]
        for r in db.execute('SELECT * FROM entity_version ORDER BY created_seq,kind,entity_id,version'):
            payload=json.loads(r['payload_json'])
            if digest(payload)!=r['payload_hash']: raise ValueError('entity hash mismatch')
            versions.append({'kind':r['kind'],'id':r['entity_id'],'version':r['version'],'payload':payload})
        return {'run_id':run_id,'status':run['status'],'binding_hash':run['binding_hash'],
                'events':events,'actions':actions,'versions':versions,
                'presentations':[dict(r) for r in db.execute('SELECT * FROM item_presentation ORDER BY view_id,kind,item_id')]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    print(json.dumps(read_trace(args.runtime_root,args.run_id),ensure_ascii=False,indent=2))
