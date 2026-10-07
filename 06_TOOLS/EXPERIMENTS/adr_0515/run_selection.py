"""Consume frozen recall output in a provenance-aware selection stage; no gold."""
from pathlib import Path
import concurrent.futures
import hashlib
import importlib.util
import json
import sys
import time
import traceback
import subprocess
import jsonschema

sys.dont_write_bytecode = True
R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0515-compact-provenance-selection'
P = R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
C = R/'02_BACKEND/lawrag/research/candidates/adr_0515/selection'


def read(p):
    return json.loads(p.read_text())


def write(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2)+'\n')


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        while chunk := f.read(8*1024*1024):
            h.update(chunk)
    return h.hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pin(case_id=None):
    frozen = read(A/'artifacts/frozen-design.json')
    for name, value in frozen['file_hashes'].items():
        if case_id and '/artifacts/run-001/' in name and not name.endswith('/'+case_id+'/result.json'):
            continue
        if sha(R/name) != value:
            raise RuntimeError('Frozen input drift: '+name)
    revision = read(C/'candidate.json')['revisions'][-1]
    for f in revision['files']:
        if sha(R/f['frozen_path']) != f['snapshot_sha256']:
            raise RuntimeError('Frozen candidate drift')
    root = C/'revisions'/revision['revision_id']/'snapshot'
    return module('pinned_source_selection', root/'02_BACKEND/semantic_runtime/legal_agent/source_selection.py'), module('pinned_experiment_client', root/'02_BACKEND/lawrag/research/experiment_client.py')


def authorize(prod):
    grant = read(A/'artifacts/export-rebinding.json')
    auth = R/'08_DEPLOYMENT/CONFIG/legal-source-export.json'
    if (not read(auth)['enabled'] or sha(auth) != grant['source_authorization_sha256']
        or sha(A/'artifacts/gemma-policy.json') != grant['policy_sha256']
        or grant['model'] != 'google/gemma-4-31b-it'
        or grant['destination'] != 'https://openrouter.ai/api/v1'
        or set(prod['public_scope_document_ids'])-set(grant['scope_document_ids'])
        or grant['private_documents_allowed'] is not False):
        raise RuntimeError('Public original authorization/provenance mismatch')
    return grant


def main():
    case_arg=sys.argv[sys.argv.index('--case')+1] if '--case' in sys.argv else None
    selection, transport = pin(case_arg)
    prod = read(A/'product-cases.json');grant = authorize(prod)
    manifest = read(A/'실험/manifest.json')
    if '--preflight' in sys.argv:
        transport.ExperimentClient(R,A/'artifacts/client-preflight',max_calls=2,max_output_tokens=4096,scoped_policy=A/'artifacts/gemma-policy.json')
        print(json.dumps({'preflight':'pass','physical_calls':0,'fixed_cases':len(prod['cases'])}));return
    run = A/'artifacts/run-001'
    if case_arg is None:run.mkdir(exist_ok=False)
    lookup = {c['case_id']:c for c in prod['cases']}
    ids = manifest['runs'][0]['case_ids'];results = {}
    def one(cid):
        started = time.monotonic();out = run/cid;out.mkdir()
        parent = P/'artifacts/run-001'/cid/'result.json'
        raw = read(parent)
        scope = set(prod['public_scope_document_ids'])
        if (raw.get('error') or any(e['document_id'] not in scope or
            e['metadata']['source_store_sha256'] != grant['source_store_sha256'] for e in raw['evidence'])):
            raise RuntimeError('Replay source scope/hash mismatch')
        client = transport.ExperimentClient(R,out/'model',max_calls=2,max_output_tokens=4096,scoped_policy=A/'artifacts/gemma-policy.json')
        answer = {'case_id':cid,'input_parent_path':str(parent.relative_to(R)),
                  'input_parent_sha256':sha(parent),'parent_retrieval_seconds':raw['request_seconds'],
                  'error':None,'status':'incomplete','first_ids':[],'recovered_ids':[],'final_ids':[]}
        def invoke(system,data,schema,phase,timeout):
            body = {'model':client.model,'messages':[{'role':'system','content':system},
                    {'role':'user','content':json.dumps(data,ensure_ascii=False,separators=(',',':'))}],
                    'temperature':0,'max_tokens':4096,'response_format':{'type':'json_schema',
                    'json_schema':{'name':'output','strict':True,'schema':schema}}}
            receipt = client.chat_completions(body,phase=phase,timeout_seconds=timeout)
            value = json.loads(receipt['body_json']['choices'][0]['message']['content'])
            jsonschema.validate(value,schema)
            client._write(out/'model'/f'call-{client.calls:03d}-{phase}'/'output.json',value)
            return value
        try:
            answer.update(selection.select_sources(lookup[cid]['question'],raw,invoke,
                          remaining_seconds=240-raw['request_seconds']-(time.monotonic()-started)))
        except Exception as exc:
            answer['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        answer.update(selection_wall_seconds=time.monotonic()-started,
                      composed_seconds=raw['request_seconds']+time.monotonic()-started,
                      physical_model_calls=client.calls,usage=client.usage)
        write(out/'result.json',answer)
        print(json.dumps({'case':cid,'first':len(answer['first_ids']),'recovered':len(answer['recovered_ids']),
              'final':len(answer['final_ids']),'calls':client.calls,'selection_seconds':round(answer['selection_wall_seconds'],2),
              'error':answer['error'] and answer['error']['type']},ensure_ascii=False),flush=True)
        return cid,str((out/'result.json').relative_to(R))
    if case_arg is not None:
        one(case_arg)
        return
    def isolated(cid):
        raw=read(P/'artifacts/run-001'/cid/'result.json')
        parent_seconds=raw['request_seconds'];timeout=max(1,240-parent_seconds)
        started=time.monotonic()
        log=(run/(cid+'.log')).open('w')
        process=subprocess.Popen([sys.executable,__file__,'--case',cid],cwd=R,stdout=log,stderr=subprocess.STDOUT)
        expired=False
        try:code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            expired=True;process.kill();code=process.wait()
        finally:log.close()
        out=run/cid;result_path=out/'result.json'
        if expired or not result_path.exists():
            usage=[]
            for u in (out/'model').glob('usage.json'):usage.extend(read(u))
            parent=P/'artifacts/run-001'/cid/'result.json'
            answer={'case_id':cid,'input_parent_path':str(parent.relative_to(R)),
                'input_parent_sha256':sha(parent),'parent_retrieval_seconds':parent_seconds,
                'error':{'type':'HardDeadlineExceeded' if expired else 'CaseProcessFailed','exit_code':code},
                'status':'incomplete','first_ids':[],'recovered_ids':[],'final_ids':[],
                'selection_wall_seconds':time.monotonic()-started,'composed_seconds':parent_seconds+time.monotonic()-started,
                'physical_model_calls':len(list((out/'model').glob('call-*'))),'usage':usage,
                'in_flight_usage_unknown':expired}
            write(result_path,answer)
        else:
            answer=read(result_path)
            answer['process_wall_seconds']=time.monotonic()-started
            answer['composed_seconds']=parent_seconds+answer['process_wall_seconds']
            write(result_path,answer)
        print(json.dumps({'case':cid,'final':len(answer['final_ids']),'calls':answer['physical_model_calls'],
              'seconds':round(answer['selection_wall_seconds'],2),'error':answer['error'] and answer['error']['type']},ensure_ascii=False),flush=True)
        return cid,str(result_path.relative_to(R))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(isolated,cid) for cid in ids]
        for f in concurrent.futures.as_completed(futures):
            cid,path = f.result();results[cid]=path
            write(run/'results.partial.json',{'cases':results})
    assert set(results)==set(ids)
    write(run/'results.json',{'cases':results,'parent_pool_replayed':True,'live_retrieval_rerun':False,
          'actual_answer_model_calls':0,'worker_count':3})


if __name__=='__main__':
    main()
