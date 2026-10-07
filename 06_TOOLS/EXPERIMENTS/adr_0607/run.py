"""Native synthetic API probe with actual pinned Qwen. Gold remains offline."""
import hashlib,importlib.util,json,logging,re,sqlite3,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'02_BACKEND'));sys.dont_write_bytecode=True
from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0607-native-memory-repaired-model-run';D=ADR/'artifacts/design'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=lambda v:sorted(v) if isinstance(v,set) else str(v))+'\n')
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def main():
    logging.getLogger('genos').setLevel(logging.WARNING)
    for path,h in json.loads((D/'freeze.json').read_text()).items():assert sha(ROOT/path)==h
    cp=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0607/repaired-memory/candidate.json';c=json.loads(cp.read_text());r=c['revisions'][-1];paths={}
    for f in r['files']:
        p=ROOT/f['frozen_path'];assert sha(p)==f['snapshot_sha256'];paths[f['snapshot_path'].split('/snapshot/',1)[1]]=p
    mem=load('semantic_runtime.legal_agent.corrected_memory',paths['02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py'])
    native=load('semantic_runtime.legal_agent.memory_rag',paths['02_BACKEND/semantic_runtime/legal_agent/memory_rag.py'])
    appmod=load('semantic_runtime.model_memory_app',paths['02_BACKEND/semantic_runtime/app.py'])
    run=ADR/'artifacts/run-001';assert not run.exists();run.mkdir()
    client=ExperimentClient(ROOT,run/'provider',max_calls=600,max_output_tokens=4096,max_repairs=0)
    transport=[];callno=0;product_rows=[]
    def invoke(system,data,schema,phase):
        nonlocal callno
        callno+=1
        for attempt in range(2):
            try:
                time.sleep(1)
                return client.generate(system,data,schema,phase=f'n{callno:03d}-{phase}'+('-retry1' if attempt else ''))
            except ExperimentProviderError as exc:
                error_code=((exc.response or {}).get('body_json') or {}).get('error',{}).get('code')
                retryable=exc.retryable or error_code in (408,409,429,500,502,503,504)
                transport.append({'call':callno,'phase':phase,'attempt':attempt,'retryable':retryable,'response':exc.response})
                write(run/'transport-receipts.json',transport)
                if attempt or not retryable:raise
                time.sleep(5)
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
    from fastapi.testclient import TestClient
    generation=ROOT/'04_EXPERIMENTS/ADR/ADR-0603-corrected-route-integration-audit-receipts/artifacts/run-001/native/built/generation'
    import contracts
    (run/'contracts').mkdir()
    contract_result=contracts.exercise(mem,native,appmod,run/'contracts',paths)
    write(run/'functional-contracts.json',contract_result)
    if contract_result['passed']!=contract_result['total']:raise RuntimeError('functional contract regression')
    proto=load('adr0607_chain',paths['02_BACKEND/semantic_runtime/legal_agent/chain_prototype.py'])
    repo=load('semantic_runtime.legal_agent.adr0607_repository',paths['02_BACKEND/semantic_runtime/legal_agent/repository.py']);proto.NativeRepository=repo.WorkRepository
    guards=load('adr0601_guards',ROOT/'06_TOOLS/EXPERIMENTS/adr_0601/guards.py')
    inherited=guards.exercise(proto,json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-0601-rag-chain-empty-state-guards/artifacts/design/RAW/documents.json').read_text()),run/'inherited-guards')
    write(run/'inherited.json',inherited)
    if inherited['passed']!=inherited['total']:raise RuntimeError('inherited state contract regression')
    principal={'user_id':'SYNTHETIC_USER','team_id':'risk_team','document_ids':['d']}
    def factory(p,runtime,body,principal):return mem.Memory(run/'memory.sqlite',native.NativeRag(p,runtime,invoke),invoke)
    app=appmod.create_app(run,generation,contracts_root=ROOT,provider=object(),implementation='legal-agent-tools-v5',legal_agent_profile={**DEFAULT_PROFILE,'bounded_source_selection_enabled':True},memory_factory=factory,memory_identity=lambda request:principal)
    aborted=None;latencies=[]
    with TestClient(app,raise_server_exceptions=True) as api:
        for case in json.loads((D/'inputs.json').read_text()):
            rows=[]
            for i,turn in enumerate(case['turns'],1):
                body={'memory':True,'request_id':case['case_id']+'-'+str(i),**turn}
                start=time.monotonic()
                try:
                    response=api.post('/v1/rag/ask',json=body);output=response.json()
                    if response.status_code!=200:output={'status':'ERROR','http_status':response.status_code,'body':output}
                except ExperimentProviderError as exc:
                    output={'status':'PROVIDER_BLOCKED','error_type':type(exc).__name__,'error':str(exc)};aborted=output
                except Exception as exc:output={'status':'ERROR','error_type':type(exc).__name__,'error':str(exc)}
                elapsed=time.monotonic()-start;latencies.append(elapsed)
                item={'turn':i,'input':body,'output':output,'seconds':elapsed};rows.append(item);write(run/case['case_id']/f'turn-{i:02d}.json',item)
                product_rows=[r for r in product_rows if r['case_id']!=case['case_id']]+[{'case_id':case['case_id'],'turns':rows}];write(run/'products.json',product_rows)
                print(json.dumps({'case':case['case_id'],'turn':i,'status':output.get('status'),'executed':output.get('executed')},ensure_ascii=False),flush=True)
                if aborted:break
            if aborted:break
    summary={'external_calls_successful':len(client.usage),'provider_attempts':client.calls,'provider_errors':len(transport),'attempted_turns':sum(len(c['turns']) for c in product_rows),'latency_seconds':{'p50':statistics.median(latencies),'p95':sorted(latencies)[round(.95*(len(latencies)-1))]},'usage':client.usage,'retrieval_quality':'not_scored_until_completed','main_unchanged':True}
    if aborted:
        write(run/'execution-abort.json',{'status':'failed','cause':aborted,'summary':summary,'not_executed':'remaining native turns and prior49 regression; no score fabricated'})
        print(json.dumps({'provider_blocked':True,'summary':{k:v for k,v in summary.items() if k!='usage'}}),flush=True);raise SystemExit(2)
    gold=json.loads((D/'gold.json').read_text());grades=[]
    for case in product_rows:
        spec=gold[case['case_id']];checks=[]
        for row in case['turns']:
            i=row['turn'];o=row['output'];expected=spec.get('statuses',[None]*len(case['turns']))[i-1]
            if expected:checks.append({'turn':i,'kind':'status','expected':expected,'observed':o.get('status'),'pass':o.get('status')==expected})
            else:checks.append({'turn':i,'kind':'completion','expected':'STORED' if i==len(case['turns']) else 'READY','observed':o.get('status'),'pass':o.get('status')==('STORED' if i==len(case['turns']) else 'READY')})
            proc=spec.get('procedure',[None]*len(case['turns']))[i-1]
            if case['case_id']=='native-long-chain' and i==len(case['turns'])-1:proc='A'
            if proc:checks.append({'turn':i,'kind':'procedure','expected':proc,'observed':(o.get('answer') or {}).get('text'),'pass':bool(re.search(r'(?<![A-Z])'+proc+r'(?![A-Z])',(o.get('answer') or {}).get('text','')))})
            if str(i) in spec.get('executed',{}):checks.append({'turn':i,'kind':'stage','expected':spec['executed'][str(i)],'observed':o.get('executed'),'pass':o.get('executed')==spec['executed'][str(i)]})
        grades.append({'case_id':case['case_id'],'checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks)})
    write(run/'result.json',{'status':'complete','products':product_rows,'grades':grades,'summary':summary})
    print(json.dumps({'completed':True,'passed':sum(g['passed'] for g in grades),'total':sum(g['total'] for g in grades)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
