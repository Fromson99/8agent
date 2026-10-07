"""Frozen paired full-HTTP probe for direct GUIDE recall and compact planning."""
import json
from pathlib import Path
import shutil
import sqlite3
import time
import traceback

from harness import R,A,candidate,app,write,sha

PARENT=R/'04_EXPERIMENTS/ADR/ADR-0575-native-schema-nightly-integration/artifacts/run-001'
GENERATION=PARENT/'noise-fixture/built/generation'
MEMORY=PARENT/'generation-roundtrip/runtime/action-memory/memory.sqlite'
ARMS=('baseline','guide_direct','guide_compact')

class LiveTransport:
    public_scope=('d',)
    def __init__(self,client,manifest):
        from lawrag.research.openrouter_legal_adapter import OpenRouterSingleSendAdapter
        self.adapter=OpenRouterSingleSendAdapter(client)
        self.binding=self.adapter.binding
        self.manifest=manifest
        self.calls=[]
    def validate_model(self): return self.adapter.validate_model()
    def authorize(self,query,request,manifest,*,public_question):
        if manifest!=self.manifest or set(query['scope']['document_version_ids'])-{'d'}:
            raise ValueError('outside frozen synthetic fixture')
        return {'classification':'SYNTHETIC','generation_id':manifest['generation_id']}
    def validate_authorization(self,context):
        if context.binding['generation_id']!=self.manifest['generation_id']:
            raise ValueError('synthetic binding drift')
    def send_once(self,*,body,ticket):
        self.calls.append(body)
        return self.adapter.send_once(body=body,ticket=ticket)

def verify():
    m=json.loads((A/'실험/manifest.json').read_text())
    assert m['design']['criteria_frozen_before_run']
    for p,h in m['design']['frozen_inputs'].items():
        assert sha(R/p)==h,p
    for c in m['design']['code_isolation']['candidates']:
        assert sha(R/c['manifest_path'])==c['manifest_sha256']
        assert sha(R/c['runner_path'])==c['runner_sha256']
    return m

def journal_summary(runtime):
    paths=list((runtime/'legal-agent/runs').glob('*/*/journal.sqlite'))
    if len(paths)!=1: return {'journal_count':len(paths)}
    db=sqlite3.connect(f'file:{paths[0]}?mode=ro',uri=True)
    try:
        events=[(kind,json.loads(payload)) for kind,payload in db.execute(
            "SELECT kind,payload_json FROM event WHERE kind IN "
            "('ACTION_MEMORY_SCOPE','ACTION_MEMORY_DIRECT_RECALL','ACTION_MEMORY_DIRECT_FALLBACK',"
            "'SOURCE_RECALL_POOL','BOUNDED_SOURCE_SELECTION') ORDER BY seq")]
    finally: db.close()
    pools=[v for k,v in events if k=='SOURCE_RECALL_POOL']
    selected=[v for k,v in events if k=='BOUNDED_SOURCE_SELECTION']
    scopes=[v for k,v in events if k=='ACTION_MEMORY_SCOPE']
    return {'journal_count':1,'direct_events':sum(k=='ACTION_MEMORY_DIRECT_RECALL' for k,_ in events),
        'fallback_events':sum(k=='ACTION_MEMORY_DIRECT_FALLBACK' for k,_ in events),
        'read_complete':sorted({sid for p in pools for sid in p['read_complete']}),
        'selected_ids':selected[-1]['final_ids'] if selected else [],
        'scope':scopes[-1] if scopes else None,
        'pool_count':len(pools)}

def one(case,arm,out):
    from fastapi.testclient import TestClient
    from lawrag.research.experiment_client import ExperimentClient
    out.mkdir(parents=True,exist_ok=False)
    memory_path=out/'runtime/action-memory/memory.sqlite'
    memory_path.parent.mkdir(parents=True)
    shutil.copyfile(MEMORY,memory_path)
    manifest=json.loads((GENERATION/'manifest.json').read_text())
    client=ExperimentClient(R,out/'calls',max_calls=8,max_output_tokens=4096,
        schema_in_prompt=False,max_repairs=0)
    transport=LiveTransport(client,manifest)
    row={'case_id':case['id'],'arm':arm,'status':'ERROR','seconds':None,'calls':0,
        'usage':[],'fulltext_rank_calls':0,'error':None}
    start=time.perf_counter()
    try:
        with candidate(arm=arm):
            from semantic_runtime.fulltext import FulltextIndex
            original=FulltextIndex.rank
            def counted(index,*args,**kwargs):
                row['fulltext_rank_calls']+=1
                return original(index,*args,**kwargs)
            FulltextIndex.rank=counted
            try:
                application=app(out,GENERATION,transport,arm=arm)
                with TestClient(application) as http:
                    response=http.post('/v1/rag/ask',json={
                        'question':case['question'],'document_ids':['d'],'public_question':True})
                    write(out/'http-result.json',{'status_code':response.status_code,'body':response.json()})
                    if response.status_code!=200: raise RuntimeError('HTTP '+str(response.status_code))
                    value=response.json()
                    write(out/'wire-bodies.json',transport.calls)
                    row.update(status='ANSWER',run_id=value['run_id'],answer=value['answer'],
                        assembly=value['assembly'])
            finally: FulltextIndex.rank=original
    except Exception as exc:
        row['error']={'type':type(exc).__name__,'message':str(exc)}
        (out/'error.txt').write_text(traceback.format_exc())
    row.update(seconds=time.perf_counter()-start,calls=client.calls,usage=client.usage,
        journal=journal_summary(out/'runtime'))
    write(out/'result.json',row)
    print(json.dumps({k:row[k] for k in ('case_id','arm','status','seconds','calls',
        'fulltext_rank_calls','error')},ensure_ascii=False),flush=True)
    return row

def main():
    verify()
    out=A/'artifacts/run-001'
    out.mkdir(exist_ok=False)
    cases=json.loads((A/'artifacts/design/cases.json').read_text())
    orders=(('baseline','guide_direct','guide_compact'),
        ('guide_compact','baseline','guide_direct'),
        ('guide_direct','guide_compact','baseline'),
        ('baseline','guide_compact','guide_direct'))
    rows=[]
    for case,order in zip(cases,orders):
        for arm in order:
            rows.append(one(case,arm,out/'cases'/case['id']/arm))
    write(out/'result.json',{'status':'complete','classification':'SYNTHETIC',
        'source_generation':json.loads((GENERATION/'manifest.json').read_text())['generation_id'],
        'results':rows})

if __name__=='__main__': main()
