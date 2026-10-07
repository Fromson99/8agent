"""Frozen current-v6 API probe; natural user language, no resolver override or gold."""
import argparse
import json
import logging
import shutil
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from common import ROOT,ADR,DESIGN,RUN,read,put,sha,verify,verify_freeze,check_payload,candidate
sys.dont_write_bytecode=True

def database(path):
    if not path.is_file():return {}
    out={}
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for table in ('goal','event','head','route','wiki','judgment_ref','request','outbox','experience_dependency'):
            out[table]=[]
            for row in db.execute('SELECT * FROM '+table):
                value=dict(row)
                for key in ('state','command','before_state','after_state','payload','ref','response'):
                    if isinstance(value.get(key),str):
                        try:value[key]=json.loads(value[key])
                        except ValueError:pass
                out[table].append(value)
        out['knowledge']=[]
        for raw in db.execute('SELECT * FROM knowledge'):
            value=dict(raw);payload=json.loads(value['payload'])
            value['payload']={k:v for k,v in payload.items() if k!='parts'}
            out['knowledge'].append(value)
        out['node']=[]
        for ident,goal,stage in db.execute('SELECT id,goal,stage FROM node'):
            fields={'RECALL':('selected_for_read','corpus_ids','binding','discovery.discovered'),
                    'READ':('originals','binding'), 'SELECT':('final_ids','selected_originals','binding')}.get(stage)
            if fields:
                payload={}
                for field in fields:
                    raw=db.execute('SELECT json_extract(payload,?) FROM node WHERE id=?',('$.'+field,ident)).fetchone()[0]
                    value=json.loads(raw) if isinstance(raw,str) else raw
                    if '.' in field:
                        a,b=field.split('.');payload.setdefault(a,{})[b]=value
                    else:payload[field]=value
            else:payload=json.loads(db.execute('SELECT payload FROM node WHERE id=?',(ident,)).fetchone()[0])
            out['node'].append({'id':ident,'goal':goal,'stage':stage,'payload':payload})
    out['authority_sqlite']=str(path.relative_to(ROOT))
    return out

def main(cid,arm,mode):
    verify_freeze();cp,c,rev,code=candidate(arm)
    sys.path.insert(0,str(code/'02_BACKEND'))
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.legal_agent.errors import TransportError,ContractError,ProposalError
    from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError
    from fastapi.testclient import TestClient
    assert Path(create_app.__code__.co_filename).is_relative_to(code)
    logging.getLogger('genos').setLevel(logging.WARNING)
    b=verify();allowed=set(b['scope_document_ids'])
    case=next(x for x in read(DESIGN/'inputs.json') if x['case_id']==cid)
    directory=RUN/cid/arm;runtime=directory/'runtime'
    directory.mkdir(parents=True,exist_ok=True)
    preflight=mode=='preflight';provider=directory/('provider-'+mode)
    client=ExperimentClient(ROOT,provider,max_calls=280,max_output_tokens=6400,max_repairs=0)
    class Transport(LocalGemmaTransport):
        def send_once(self,*,body,ticket):
            assert not preflight,'Preflight model calls forbidden'
            verify()
            phase='unknown'
            for message in body['messages']:
                if message['role']=='user':
                    try:
                        data=json.loads(message['content']);check_payload(data,allowed)
                        view=data.get('view',data)
                        if isinstance(view,dict):phase=view.get('source_stage',view.get('phase',phase))
                    except json.JSONDecodeError:pass
            try:
                result=client.chat_completions(body,phase=str(phase),timeout_seconds=min(180,ticket['remaining_seconds']))
            except ExperimentProviderError as exc:raise TransportError(str(exc),retryable=False,response=exc.response) from exc
            except Exception as exc:raise TransportError(type(exc).__name__,retryable=False,unknown=True) from exc
            response=result['body_json'];choices=response.get('choices') or []
            if response.get('provider')!='Parasail' or response.get('model')!=self.binding['model']:raise ContractError('Pinned model/provider mismatch')
            if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
                error=ProposalError('Incomplete provider response');error.response=result;raise error
            if (((response.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or choices[0].get('message',{}).get('reasoning')):raise ContractError('Reasoning unexpectedly enabled')
            return result
    transport=Transport(code,ROOT)
    profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
    user='V6_AUDIT_'+cid
    principal={'user_id':user,'team_id':'public-audit','document_ids':sorted(allowed)}
    def app_for(root,who):
        return create_app(directory,ROOT/b['generation'],contracts_root=code,provider=object(),
            implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,
            runtime_root=root,memory_identity=lambda request:who)
    def post(api,text,label,session,root):
        target=directory/('turn-'+label+'.json');assert not target.exists(),'Frozen turn cannot be replayed'
        body={'question':text,'memory':True,'public_question':True,'session_id':session,'request_id':arm+'-'+label}
        first=client.calls;start=time.monotonic()
        try:
            response=api.post('/v1/rag/ask',json=body);output=response.json();status=response.status_code
        except Exception as exc:
            status=500;output={'status':'ERROR','error_type':type(exc).__name__,'error':str(exc)}
            (directory/('exception-'+label+'.txt')).write_text(traceback.format_exc())
        seconds=time.monotonic()-start
        row={'case_id':cid,'arm':arm,'turn':label,'input':body,'http_status':status,'output':output,'seconds':seconds,
            'provider_attempt_start':first+1,'provider_attempt_end':client.calls,'calls':client.calls-first,
            'db':database(root/'case-memory/cases-v3.sqlite'),'process_id':__import__('os').getpid()}
        put(target,row)
        print(json.dumps({k:v for k,v in {'case':cid,'arm':arm,'turn':label,'http':status,'status':output.get('status'),'calls':row['calls'],'seconds':round(seconds,2),'executed':output.get('executed')}.items()},ensure_ascii=False),flush=True)
        return row
    app=app_for(runtime,principal)
    if preflight:
        with TestClient(app) as api:health=api.get('/health').json()
        put(directory/'preflight.json',{'ready':True,'health':health,'model_calls':client.calls,'code_root':str(code.relative_to(ROOT))})
        print('Preflight ready '+cid+'/'+arm,flush=True);return
    if mode=='initial':
        assert arm=='baseline'
        with TestClient(app) as api:row=post(api,case['question'],'initial',cid,runtime)
        put(directory/'products.json',[row])
    elif mode=='fresh':
        assert arm=='baseline'
        fresh=directory/'fresh-runtime'
        with TestClient(app_for(fresh,{**principal,'user_id':user+'-fresh'})) as api:
            post(api,case['reuse_question'],'fresh',cid+'-fresh',fresh)
    elif mode=='learning':
        assert arm=='guided';assert not (directory/'products.json').exists()
        origin=RUN/cid/'baseline/runtime'
        # Preflight created an empty case store. Keep it separately before the measured fork.
        if runtime.exists():runtime.rename(directory/'preflight-runtime')
        assert (RUN/cid/'baseline/products.json').is_file()
        shutil.copytree(origin,runtime)
        hashes={str(p.relative_to(origin)):sha(p) for p in origin.rglob('*') if p.is_file()}
        assert all(sha(runtime/p)==h for p,h in hashes.items())
        put(directory/'fork-receipt.json',{'origin':str(origin.relative_to(ROOT)),'files':hashes})
        products=[]
        with TestClient(app_for(runtime,principal)) as api:
            for i,text in enumerate(case['guides'],1):
                products.append(post(api,text,'guide'+str(i),cid,runtime));put(directory/'products.json',products)
            if products[-1]['http_status']==200 and products[-1]['output'].get('status')=='READY':
                confirmation=post(api,case['confirmation'],'confirm',cid,runtime)
                queries={}
                for kind in ('user_wiki','legal_wiki','experience'):
                    if kind=='experience' and not confirmation['output'].get('experience_id'):continue
                    body={'query_kind':kind,'session_id':cid,'request_id':'query-'+kind,**({'experience_id':confirmation['output']['experience_id']} if kind=='experience' else {'question':''})}
                    response=api.post('/v1/rag/memory/query',json=body)
                    queries[kind]={'input':body,'http_status':response.status_code,'output':response.json()}
                put(directory/'wiki-before-restart.json',queries)
            else:put(directory/'secondary-blocked.json',{'reason':'Final guided request did not complete READY; experience pipeline not fabricated.'})
    elif mode=='reuse':
        assert arm=='guided'
        confirmation=directory/'turn-confirm.json'
        if not confirmation.exists() or read(confirmation)['output'].get('status')!='STORED':
            put(directory/'reuse-blocked.json',{'reason':'No confirmed experience to reuse'});return
        # A new interpreter and a new app reopen the same authority; no in-memory cache carries over.
        with TestClient(app_for(runtime,principal)) as api:
            queries={}
            for kind in ('user_wiki','legal_wiki'):
                response=api.post('/v1/rag/memory/query',json={'query_kind':kind,'question':''})
                queries[kind]={'http_status':response.status_code,'output':response.json()}
            put(directory/'wiki-after-restart.json',queries)
            post(api,case['reuse_question'],'automatic-reuse',cid+'-auto',runtime)
            post(api,case['explicit_reuse'],'explicit-reuse',cid+'-explicit',runtime)
            post(api,case['changed_question'],'changed-conditions',cid+'-changed',runtime)
    else:raise ValueError(mode)
    put(directory/('summary-'+mode+'.json'),{'complete':True,'mode':mode,'physical_calls':client.calls,'usage':client.usage,'process_id':__import__('os').getpid(),'model':transport.binding,'main_unchanged':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True,choices=('simple-public','cm-003'))
    p.add_argument('--arm',required=True,choices=('baseline','guided'))
    p.add_argument('--mode',required=True,choices=('preflight','initial','fresh','learning','reuse'))
    a=p.parse_args();main(a.case,a.arm,a.mode)
