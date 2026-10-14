"""Execute unchanged frozen knowledge_lab against an independent finite oracle."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
from itertools import product
from pathlib import Path
import argparse
import gzip
import json
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT=Path.cwd()
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0715-deduction-execution-audit'
CANDIDATE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0715/audited'
PARENT=ROOT/'04_EXPERIMENTS/ADR/ADR-0713-legal-knowledge-lab-deduction'
OUT=ADR/'artifacts/run-001'
sha=lambda p:sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())

def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def load():
    sys.dont_write_bytecode=True
    b=read(ADR/'artifacts/design/binding.json')
    assert sha(CANDIDATE/'candidate.json')==b['manifest_sha256']
    m=read(CANDIDATE/'candidate.json')
    rev=next(r for r in m['revisions'] if r['revision_id']==b['revision_id'])
    assert rev['revision_sha256']==b['revision_sha256'] and not m['production_loadable']
    for f in rev['files']:
        assert sha(ROOT/f['frozen_path'])==f['snapshot_sha256']
        target=next(row['target_path'] for row in m['files'] if row['snapshot_path']==f['snapshot_path'])
        if target.startswith('02_BACKEND/knowledge_lab/'):
            parent=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0713/lab/revisions/rev-007/snapshot'/target
            assert sha(parent)==f['snapshot_sha256'],'Parent code differs'
    sys.path.insert(0,str(ROOT/'02_BACKEND'))
    from lawrag.platform.workspace import load_layout
    workspace=load_layout()
    sys.path.insert(0,str(CANDIDATE/'revisions'/b['revision_id']/'snapshot/02_BACKEND'))
    assert sha(ADR/'artifacts/design/inputs.json')==b['inputs_sha256']
    assert sha(PARENT/'artifacts/design/baseline.json')==b['baseline_sha256']
    return workspace,read(PARENT/'artifacts/design/baseline.json')

def key(a):
    return a['predicate'],tuple(a['args']),a.get('negative',False)

def closure_oracle(case):
    """Ground every assignment then compute a set closure. No kernel imports."""
    entities=list(case['context']['entities'])
    known={key(f['atom']) for f in case['facts']}
    ground=[]
    for r in case['kb']['units']:
        variables=sorted({x for a in r['body']+[r['head']] for x in a['args'] if x.startswith('?')})
        for values in product(entities,repeat=len(variables)):
            b=dict(zip(variables,values))
            def instantiate(a):
                return a['predicate'],tuple(b.get(x,x) for x in a['args']),a.get('negative',False)
            ground.append((frozenset(instantiate(a) for a in r['body']),instantiate(r['head'])))
    changed=True
    while changed:
        previous=len(known)
        for body,head in ground:
            if body<=known:known.add(head)
        changed=len(known)!=previous
    return known

def serve(port):
    workspace,baseline=load()
    from knowledge_lab.app import create_app
    import uvicorn
    app=create_app(workspace,baseline,workspace.path('runtime')/'knowledge-lab'/'adr-0715-http',
                   ROOT/'06_TOOLS/EXPERIMENTS/adr_0713/run_lab.py')
    uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning')

def execute():
    if OUT.exists():raise RuntimeError('Run artifacts already exist; do not overwrite a completed or partial run')
    OUT.mkdir(parents=True)
    workspace,baseline=load()
    from knowledge_lab.logic import solve,compose,check_proof,CHECKER_SHA256
    from knowledge_lab.demo import dataset,atom
    data=read(ADR/'artifacts/design/inputs.json')
    records=[]
    trace=gzip.open(OUT/'io.jsonl.gz','wt',encoding='utf-8')
    def record(group,id,ok,**detail):
        row=dict(group=group,id=id,passed=bool(ok),**detail)
        records.append(row)
        if not ok:print('FAIL',group,id,detail.get('actual',detail.get('detail','')),flush=True)
    def call(c,goal=None):
        start=time.perf_counter()
        out=solve(c['kb'],c['facts'],goal or c['goal'],c['context'])
        ms=(time.perf_counter()-start)*1000
        replay=check_proof(c['kb'],out['proof'],c['context']) if out['proof'] else None
        trace.write(json.dumps(dict(id=c['id'],goal=goal or c['goal'],result=out,replay=replay,elapsed_ms=ms),ensure_ascii=False)+'\n')
        return out,replay,ms
    for c in data['handcrafted']:
        result,replay,ms=call(c)
        checks={'state':result['status']==c['expected'],'proof_replay':replay is not False}
        if 'expect_missing' in c:checks['missing']=set(map(key,result['missing']))==set(map(key,c['expect_missing']))
        if 'expect_dependencies' in c:
            checks['dependencies']={d['id'] for d in (result['proof'] or {}).get('dependencies',[])}==set(c['expect_dependencies'])
        if 'expect_assumption' in c:checks['assumption']=c['expect_assumption'] in (result['proof'] or {}).get('assumptions',[])
        record('handcrafted',c['id'],all(checks.values()),expected=c['expected'],actual=result['status'],checks=checks,missing=result['missing'],elapsed_ms=ms)
    print('Handcrafted complete',flush=True)
    false_positive=false_negative=limits=proof_failures=0
    for c in data['generated']:
        closure=closure_oracle(c)
        for goal in c['goals']:
            expected=key(goal) in closure
            result,replay,ms=call(c,goal)
            actual=result['proof'] is not None
            false_positive+=int(actual and not expected)
            false_negative+=int(expected and not actual)
            limits+=int(result['status']=='LIMIT_REACHED')
            proof_failures+=int(replay is False)
            record('oracle',c['id']+':'+goal['predicate']+'('+goal['args'][0]+')',expected==actual and replay is not False and result['status']!='LIMIT_REACHED',
                   expected=expected,actual=result['status'],elapsed_ms=ms,replay=replay)
    print('Oracle complete',flush=True)
    d=dataset();v=lambda p:atom(p)
    cr=compose(d['kb'],[v('X'),v('Y'),v('C')],v('D'),d['context'])
    trace.write(json.dumps(dict(id='composition',result=cr),ensure_ascii=False)+'\n')
    record('composition','unseen-universal-theorem',bool(cr.get('derived')) and len(cr['derived']['dependencies'])==3 and not cr['derived']['assumptions'],actual=cr['status'])
    weak=deepcopy(d);weak['kb']['units'][0]['kind']='HYPOTHESIS'
    wr=compose(weak['kb'],[v('A'),v('C')],v('D'),d['context'])
    trace.write(json.dumps(dict(id='weak-composition',result=wr),ensure_ascii=False)+'\n')
    record('composition','weakness-not-upgraded',bool(wr.get('derived')) and 'HYPOTHESIS:wiki-1' in wr['derived']['assumptions'],actual=wr['status'])
    reverse=compose(d['kb'],[v('D')],v('K'),d['context'])
    record('composition','no-reverse-theorem',not reverse.get('derived'),actual=reverse['status'])
    dated=deepcopy(d);dated['kb']['units'][0]['scope'].update(valid_from='2025-01-01',valid_to='2027-12-31')
    dated['kb']['units'][1]['scope'].update(valid_from='2026-01-01',valid_to='2028-12-31')
    dr=compose(dated['kb'],[v('A'),v('C')],v('D'),d['context'])
    record('composition','scope-intersection',dr.get('derived',{}).get('scope',{}).get('valid_from')=='2026-01-01' and dr['derived']['scope']['valid_to']=='2027-12-31',actual=dr.get('derived',{}).get('scope'))
    # A valid proof remains logically valid when an unrelated alternative exists.
    from prepare import case,rule,atom as a
    alt=case('proof-stability',[rule('ad',[a('A')],a('D')),rule('cd',[a('C')],a('D'))],[a('A','a'),a('C','a')],a('D','a'),'CONDITIONAL')
    pr=solve(alt['kb'],alt['facts'],alt['goal'],alt['context'])['proof']
    reordered=deepcopy(alt['kb']);reordered['units'].reverse()
    record('proof-stability','reorder-independent-rules',check_proof(reordered,pr,alt['context']),actual=check_proof(reordered,pr,alt['context']))
    # Genuine HTTP sockets, persistent SQL and restart, not a mocked transport.
    port=5582;base=f'http://127.0.0.1:{port}'; token=None;server=None
    def start_server():
        nonlocal server,token
        log=(OUT/'http-server.log').open('a')
        server=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve','--port',str(port)],cwd=ROOT,stdout=log,stderr=log)
        log.close()
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('Audit HTTP server failed to start')
            try:
                html=urllib.request.urlopen(base,timeout=1).read().decode()
                token=re.search(r'name="lab-token" content="([^"]+)"',html).group(1);return
            except (OSError,AttributeError):time.sleep(.1)
        raise RuntimeError('Audit HTTP startup timeout')
    def api(path,body=None):
        req=urllib.request.Request(base+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
            headers={'X-Lab-Token':token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:code=response.status;result=json.load(response)
        except urllib.error.HTTPError as e:code=e.code;result=json.load(e)
        trace.write(json.dumps(dict(transport='real-http',path=path,request=body,http_status=code,response=result),ensure_ascii=False)+'\n')
        return code,result
    try:
        runtime=workspace.path('runtime')/'knowledge-lab'/'adr-0715-http'
        if runtime.exists():raise RuntimeError('HTTP sandbox exists; refusing to overwrite')
        start_server()
        code,_=api('/api/demo',{});record('http','seed-demo',code==200,actual=code)
        request={k:d[k] for k in ['facts','goal','context']}
        code,proved=api('/api/prove',request)
        record('http','unseen-path-live',code==200 and bool(proved.get('proof')),actual=proved.get('status'))
        payload=dict(premises=[v('A'),v('C')],goal=v('D'),context=d['context'])
        code,saved=api('/api/derived',payload);ident=saved.get('id')
        record('http','save-new-theorem',code==200 and bool(ident),actual=code)
        code,again=api('/api/derived',payload)
        record('http','deduplicate-theorem',code==200 and again.get('id')==ident and again.get('already_saved') is True,actual=again)
        code,reused=api('/api/prove',request)
        _,kb=api('/api/kb')
        root=(reused.get('proof') or {}).get('root')
        root_rule=(reused.get('proof') or {}).get('nodes',{}).get(root,{}).get('rule')
        record('http','saved-theorem-actually-used',code==200 and root_rule==ident,actual=root_rule,expected=ident)
        server.terminate();server.wait(timeout=10);start_server()
        code,after=api('/api/kb')
        record('http','restart-keeps-theorem',code==200 and any(u['id']==ident for u in after['units']),actual=code)
        # A second distinct theorem has D in its premises, ensuring it depends on
        # the previous derivation if it is selected by the engine.
        ep=dict(id='E',label='후속 결론 E',types=['Entity'])
        api('/api/predicate',ep)
        de=deepcopy(d['kb']['units'][0]);de.update(id='wiki-d-e',body=[v('D')],head=v('E'))
        api('/api/unit',dict(unit=de,expected_revision=0))
        code,nested=api('/api/derived',dict(premises=[v('X'),v('Y'),v('C')],goal=v('E'),context=d['context']))
        nested_id=nested.get('id')
        record('http','save-next-theorem',code==200 and bool(nested_id),actual=code)
        _,kb=api('/api/kb')
        nested_unit=next((u for u in kb['units'] if u['id']==nested_id),{})
        record('http','next-theorem-reuses-saved-parent',ident in {x['id'] for x in nested_unit.get('derivation_dependencies',[])},actual=[x['id'] for x in nested_unit.get('derivation_dependencies',[])])
        conflict=deepcopy(request);conflict['facts'].append({**d['facts'][0],'id':'not-b','atom':atom('B','대상1',True)})
        code,blocked=api('/api/prove',conflict)
        record('http','cache-cannot-bypass-conflict',code==200 and blocked.get('proof') is None,actual=blocked.get('status'))
        code,_=api('/api/retire',dict(id='wiki-1',expected_revision=1))
        _,retired=api('/api/kb');states={u['id']:u.get('state') for u in retired['units']}
        record('http','parent-retirement-invalidates-two-levels',code==200 and states.get(ident)=='STALE' and states.get(nested_id)=='STALE',actual={ident:states.get(ident),nested_id:states.get(nested_id)})
        code,after=api('/api/prove',request)
        record('http','withdrawal-blocks-old-conclusion',code==200 and not after.get('proof'),actual=after.get('status'))
        _,history=api('/api/history?kind=unit&id=wiki-1')
        record('http','withdrawal-history-preserved',len(history.get('items',[]))==2,actual=len(history.get('items',[])))
        # Fresh independent source remains usable after parent withdrawal.
        alternate=deepcopy(d['kb']['units'][0]);alternate.update(id='independent-c-d',body=[v('C')],head=v('D'))
        api('/api/unit',dict(unit=alternate,expected_revision=0))
        code,independent=api('/api/prove',request)
        record('http','independent-path-survives-withdrawal',code==200 and bool(independent.get('proof')),actual=independent.get('status'))
    except Exception as exc:
        record('http','unexpected-harness-error',False,detail=repr(exc))
    finally:
        if server is not None and server.poll() is None:server.terminate();server.wait(timeout=10)
    before=read(ADR/'artifacts/design/before.json')
    record('integrity','MAIN-pointer-unchanged',sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==before['pointer_sha256'])
    record('integrity','parent-frozen-code-unchanged',all(sha(ROOT/p)==h for p,h in before['parent_files'].items()))
    record('integrity','main-working-entrypoints-unchanged',all(sha(ROOT/p)==h for p,h in before['working_files'].items()))
    trace.close()
    groups={g:dict(total=sum(r['group']==g for r in records),passed=sum(r['group']==g and r['passed'] for r in records)) for g in sorted({r['group'] for r in records})}
    timings=[r['elapsed_ms'] for r in records if 'elapsed_ms' in r]
    result=dict(status='complete',passed=all(r['passed'] for r in records),groups=groups,
        oracle=dict(total=1200,false_positive=false_positive,false_negative=false_negative,limit_reached=limits,proof_replay_failures=proof_failures),
        latency_ms=dict(p50=statistics.median(timings),p95=sorted(timings)[int(len(timings)*.95)],max=max(timings),scope='Single process synthetic per-query kernel time; proof replay and IO excluded'),
        checker_sha256=CHECKER_SHA256,model_calls=0,api_cost_usd=0,production_modified=False,records=records)
    put(OUT/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');parser.add_argument('--port',type=int,default=5582)
    args=parser.parse_args()
    serve(args.port) if args.serve else execute()
