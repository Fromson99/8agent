"""Synthetic public-only history fixtures, isolated from the user's real DB.

These are contract fixtures, not completed historical model answers. Both arms
receive the same seed requests/source coordinates, with no legal conclusions.
"""
import json,sqlite3
from pathlib import Path

def seed(pipeline,runtime,principal,binding,seed_file):
    from types import SimpleNamespace
    from semantic_runtime.legal_agent.shortcut_cases import ShortcutCases
    from semantic_runtime.legal_agent.corrected_memory import STAGES,digest,encoded
    from semantic_runtime.legal_agent.core_evidence_route import finalize
    flags={'core_evidence_route':True}
    host=SimpleNamespace(pipeline=pipeline,binding=binding)
    cases=ShortcutCases(Path(runtime)/'case-memory/cases-v4.sqlite',host,None,flags=flags)
    db=sqlite3.connect((pipeline.store.path/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    receipts=[]
    try:
        for n,item in enumerate(json.loads(Path(seed_file).read_text())['seeds'],1):
            source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(item['source_id'],)).fetchone()[0])
            assert source['document_id'] in principal['document_ids']
            body={'question':item['question'],'session_id':'synthetic-memory-'+str(n),'request_id':'seed-'+str(n),
                  'document_ids':[source['document_id']],'public_question':True}
            intake=cases.shortcut.intake(body,principal);inv=cases.shortcut.connect(intake['id'],principal)
            cases.active_case=inv['id'];cases.original_session=body['session_id'];cases.internal_session=inv['id']
            cases.identity(inv['id'],principal)
            gid='synthetic-public-memory:'+item['seed_id']
            state={'task':item['question'],'facts':[],'document_ids':[source['document_id']],'source_category':'external','queries':[item['topic']]}
            cases.db.execute('INSERT INTO goal VALUES(?,?,?,?,?,?,?)',(gid,inv['id'],1,encoded(state),1,'READY',None))
            spans=[]
            for b in source['blocks']:
                raw=pipeline.store.source(source['document_id'],str(b['block_id']))
                if raw['text']:spans.append({'block_id':str(b['block_id']),'start_cp':0,'end_cp':len(raw['text']),'text':raw['text']})
            original={'source_id':source['id'],'document_id':source['document_id'],'unit_id':source['unit_id'],
                      'document_name':source['document_name'],'text':source['text'],'adopted_spans':spans}
            nodes={}
            for stage in STAGES:
                payload={'fixture':'SYNTHETIC_PUBLIC_MEMORY_NOT_MODEL_EXECUTION','stage':stage}
                if stage=='INTENT':payload.update(purpose=item['topic'],background_quotes=[])
                if stage=='READ':payload.update(originals=[original],evidence=[])
                if stage=='SELECT':payload.update(final_ids=[source['id']],selected_originals=[original])
                cur=cases.db.execute('INSERT INTO node(goal,stage,revision,payload,hash) VALUES(?,?,?,?,?)',(gid,stage,1,encoded(payload),digest(payload)))
                nodes[stage]=cur.lastrowid;cases.db.execute('INSERT INTO head VALUES(?,?,?)',(gid,stage,cur.lastrowid))
            payload={'fixture':'SYNTHETIC_PUBLIC_MEMORY_NOT_MODEL_EXECUTION','state':state,'nodes':nodes,
                     'judgment_refs':{'SELECT':{'run_id':'synthetic-seed','payload_hash':digest(cases.parts(gid)['SELECT']['payload'])}}}
            route=cases.db.execute('INSERT INTO route(goal,revision,status,payload,hash) VALUES(?,?,?,?,?)',(gid,1,'ACTIVE',encoded(payload),digest(payload))).lastrowid
            receipts.append(finalize(cases,{'goal_id':gid,'revision':1,'route_id':route,'status':'READY'},principal))
        return {'fixtures':receipts,'model_calls':0,'source':'SYNTHETIC_PUBLIC_ONLY','actual_user_history':False}
    finally:db.close();cases.close()
