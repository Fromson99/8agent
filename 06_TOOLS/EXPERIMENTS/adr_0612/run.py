"""Native actual public CM API probe with actual pinned Qwen. Gold remains offline."""
import hashlib,importlib.util,json,logging,re,sqlite3,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'02_BACKEND'));sys.dont_write_bytecode=True
from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery';D=ADR/'artifacts/design'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=lambda v:sorted(v) if isinstance(v,set) else str(v))+'\n')
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def snapshot(path):
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    out={}
    for table in ('goal','event','head','route','knowledge','ontology_node','ontology_edge','wiki','wiki_event'):
        out[table]=[]
        for r in db.execute('SELECT * FROM '+table):
            row=dict(r)
            for k in ('state','command','before_state','after_state','payload'):
                if row.get(k) is not None:row[k]=json.loads(row[k])
            if table=='knowledge':row['payload']={k:v for k,v in row['payload'].items() if k!='parts'}
            if table=='ontology_node':row.pop('payload',None)
            out[table].append(row)
    db.close();return out

def main(arm,preflight=False):
    logging.getLogger('genos').setLevel(logging.WARNING)
    for path,h in json.loads((D/'freeze.json').read_text()).items():assert sha(ROOT/path)==h
    ident={'BASELINE':'baseline-memory','RECOVERED':'bounded-memory'}[arm]
    cp=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0612'/ident/'candidate.json';c=json.loads(cp.read_text());r=c['revisions'][-1];paths={}
    for f in r['files']:
        p=ROOT/f['frozen_path'];assert sha(p)==f['snapshot_sha256'];paths[f['snapshot_path'].split('/snapshot/',1)[1]]=p
    if arm in ('BASELINE','RECOVERED'):load('semantic_runtime.legal_agent.memory_methods',paths['02_BACKEND/semantic_runtime/legal_agent/memory_methods.py'])
    mem=load('semantic_runtime.legal_agent.corrected_memory',paths['02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py'])
    native=load('semantic_runtime.legal_agent.memory_rag',paths['02_BACKEND/semantic_runtime/legal_agent/memory_rag.py'])
    appmod=load('semantic_runtime.model_memory_app',paths['02_BACKEND/semantic_runtime/app.py'])
    from binding import verify,check_payload
    binding=verify(all_files=True);allowed=set(binding['scope_document_ids'])
    run=ADR/('artifacts/preflight' if preflight else 'artifacts/run-001')/arm;assert not run.exists();run.mkdir(parents=True)
    client=ExperimentClient(ROOT,run/'provider',max_calls=350,max_output_tokens=6400,max_repairs=0)
    transport=[];format_repairs=[];callno=0;product_rows=[]
    from format_recovery import generate as bounded_generate
    def format_receipt(value):
        format_repairs.append(value);write(run/'format-repair-receipts.json',format_repairs)
    def invoke(system,data,schema,phase):
        nonlocal callno
        assert not preflight,'model invocation forbidden in preflight'
        verify();check_payload(data,allowed)
        callno+=1
        for attempt in range(2):
            try:
                time.sleep(1)
                physical_phase=f'n{callno:03d}-{phase}'+('-retry1' if attempt else '')
                if arm=='RECOVERED':return bounded_generate(client,system,data,schema,physical_phase,format_receipt)
                return client.generate(system,data,schema,phase=physical_phase)
            except ExperimentProviderError as exc:
                error_code=((exc.response or {}).get('body_json') or {}).get('error',{}).get('code')
                retryable=exc.retryable or error_code in (408,409,429,500,502,503,504)
                transport.append({'call':callno,'phase':phase,'attempt':attempt,'retryable':retryable,'response':exc.response})
                write(run/'transport-receipts.json',transport)
                if attempt or not retryable:raise
                time.sleep(5)
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
    from fastapi.testclient import TestClient
    generation=ROOT/binding['generation']
    principal={'user_id':'CM_EXPERIMENT_USER','team_id':'cm_public','document_ids':binding['scope_document_ids']}
    def factory(p,runtime,body,principal):return mem.Memory(run/'memory.sqlite',native.NativeRag(p,runtime,invoke),invoke)
    app=appmod.create_app(run,generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v5',legal_agent_profile={**DEFAULT_PROFILE,'bounded_source_selection_enabled':True},memory_factory=factory,memory_identity=lambda request:principal)
    if preflight:
        write(run/'result.json',{'ready':True,'public_scope_count':len(allowed),'model_calls':0});print('Preflight ready '+arm,flush=True);return
    aborted=None;latencies=[]
    with TestClient(app,raise_server_exceptions=True) as api:
        for case in json.loads((D/'inputs.json').read_text()):
            rows=[]
            for i,turn in enumerate(case['turns'],1):
                body={'memory':True,'request_id':case['case_id']+'-'+str(i),**turn}
                start=time.monotonic();call_start=client.calls
                try:
                    response=api.post('/v1/rag/ask',json=body);output=response.json()
                    if response.status_code!=200:output={'status':'ERROR','http_status':response.status_code,'body':output}
                except ExperimentProviderError as exc:
                    output={'status':'PROVIDER_BLOCKED','error_type':type(exc).__name__,'error':str(exc)};aborted=output
                except Exception as exc:output={'status':'ERROR','error_type':type(exc).__name__,'error':str(exc)}
                elapsed=time.monotonic()-start;latencies.append(elapsed)
                item={'turn':i,'input':body,'output':output,'seconds':elapsed,'provider_attempt_start':call_start+1,'provider_attempt_end':client.calls,'db':snapshot(run/'memory.sqlite')};rows.append(item);write(run/case['case_id']/f'turn-{i:02d}.json',item)
                product_rows=[r for r in product_rows if r['case_id']!=case['case_id']]+[{'case_id':case['case_id'],'turns':rows}];write(run/'products.json',product_rows)
                print(json.dumps({'case':case['case_id'],'turn':i,'status':output.get('status'),'executed':output.get('executed')},ensure_ascii=False),flush=True)
                if aborted:break
            if aborted:break
    summary={'external_calls_successful':len(client.usage),'provider_attempts':client.calls,'provider_errors':len(transport),'attempted_turns':sum(len(c['turns']) for c in product_rows),'latency_seconds':{'p50':statistics.median(latencies),'p95':sorted(latencies)[round(.95*(len(latencies)-1))]},'usage':client.usage,'retrieval_quality':'not_scored_until_completed','main_unchanged':True}
    if aborted:
        write(run/'execution-abort.json',{'status':'failed','cause':aborted,'summary':summary,'not_executed':'remaining native turns and prior49 regression; no score fabricated'})
        print(json.dumps({'provider_blocked':True,'summary':{k:v for k,v in summary.items() if k!='usage'}}),flush=True);raise SystemExit(2)
    write(run/'product-result.json',{'status':'complete','arm':arm,'products':product_rows,'summary':summary})
    print(json.dumps({'completed':True,'arm':arm,'turns':summary['attempted_turns'],'calls':client.calls},ensure_ascii=False),flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--arm',required=True,choices=['BASELINE','RECOVERED']);p.add_argument('--preflight',action='store_true');a=p.parse_args();main(a.arm,a.preflight)
