"""Resume only the interrupted requests over identical frozen product code."""
import argparse,json,logging,sqlite3,sys,time,traceback
from pathlib import Path
from common import ROOT,ADR,DESIGN,RUN,read,put,verify,verify_freeze,check_payload,candidate
from prepare import compact
sys.dont_write_bytecode=True

def main(cid,arm):
    verify_freeze();cp,c,rev,code=candidate(arm);sys.path.insert(0,str(code/'02_BACKEND'))
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
    from semantic_runtime.legal_agent.errors import TransportError,ContractError,ProposalError
    from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError
    from fastapi.testclient import TestClient
    b=verify();allowed=set(b['scope_document_ids']);case=next(c for c in read(DESIGN/'inputs.json') if c['case_id']==cid)
    d=RUN/cid/arm;runtime=d/'runtime';assert not (d/'summary.json').exists()
    client=ExperimentClient(ROOT,d/'provider',max_calls=160,max_repairs=0)
    active=[0,40]
    class Transport(LocalGemmaTransport):
        def send_once(self,*,body,ticket):
            verify()
            if client.calls-active[0]>=active[1]:raise TransportError('Cumulative original40-attempt cap exhausted',retryable=False)
            for m in body['messages']:
                if m['role']=='user':
                    try:check_payload(json.loads(m['content']),allowed)
                    except json.JSONDecodeError:pass
            try:r=client.chat_completions(body,phase='continuation-'+str(client.calls+1),timeout_seconds=ticket['remaining_seconds'])
            except ExperimentProviderError as e:raise TransportError(str(e),retryable=False,response=e.response) from e
            except Exception as e:raise TransportError(type(e).__name__,retryable=False,unknown=True) from e
            x=r['body_json'];choices=x.get('choices') or []
            if x.get('provider')!='Parasail' or x.get('model')!=self.binding['model']:raise ContractError('Binding mismatch')
            if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
                e=ProposalError('Incomplete response');e.response=r;raise e
            if (((x.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or choices[0].get('message',{}).get('reasoning')):raise ContractError('Reasoning unexpectedly enabled')
            return r
    transport=Transport(code,ROOT);profile=read(code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
    principal={'user_id':'CM_EXPERIMENT_USER','team_id':'cm_public','document_ids':sorted(allowed)}
    app=create_app(d,ROOT/b['generation'],contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,runtime_root=runtime,memory_identity=lambda r:principal)
    products=read(d/'products.json') if (d/'products.json').exists() else []
    def post(api,text,turn,session=None,prior=0):
        body={'question':text,'memory':True,'public_question':True,'session_id':session or cid,'request_id':arm+'-'+str(turn)}
        active[:]=[client.calls,40-prior];start=time.monotonic();begin=client.calls
        try:
            response=api.post('/v1/rag/ask',json=body);out=response.json();status=response.status_code
        except Exception as e:
            out={'status':'ERROR','error_type':type(e).__name__,'error':str(e)};status=500
            (d/('exception-'+str(turn)+'.txt')).write_text(traceback.format_exc())
        elapsed=time.monotonic()-start
        row={'case_id':cid,'arm':arm,'turn':turn,'input':body,'http_status':status,'output':out,'seconds':elapsed,
            'provider_attempt_start':begin+1,'provider_attempt_end':client.calls,'prior_physical_calls':prior,
            'latency_scope':'continuation segment; earlier interrupted interval not included','db':compact(runtime/'case-memory/cases-v3.sqlite')}
        put(d/('turn-'+str(turn)+'.json'),row)
        print(json.dumps({'case':cid,'arm':arm,'turn':turn,'status':out.get('status'),'http':status,'new_calls':client.calls-begin,'seconds':round(elapsed,1)},ensure_ascii=False),flush=True)
        return row
    with TestClient(app,raise_server_exceptions=True) as api:
        if (cid,arm)==('cm-051','guided'):
            for i,text in enumerate(case['guides'],1):
                products.append(post(api,text,i,prior=5 if i==1 else 0));put(d/'products.json',products)
        elif (cid,arm)==('cm-003','unguided'):
            for i,text in enumerate(case['control_turns'],1):
                products.append(post(api,text,i,prior=8 if i==1 else 0));put(d/'products.json',products)
        if arm=='guided' and products[-1]['http_status']==200 and products[-1]['output'].get('status')=='READY':
            if cid=='cm-003':
                # Recover the already accepted confirm/reuse response; no model replay.
                with sqlite3.connect('file:'+str(runtime/'case-memory/cases-v3.sqlite')+'?mode=ro',uri=True) as db:
                    for label,session in [('confirm',cid),('reuse',cid+'-new')]:
                        key=__import__('hashlib').sha256(json.dumps([principal['user_id'],principal['team_id'],session,arm+'-'+label],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                        raw=db.execute('SELECT response FROM request WHERE id=?',(key,)).fetchone();assert raw
                        result=json.loads(raw[0]);assert result.get('public_run_id')
                        out=read(runtime/'runs'/(result['public_run_id']+'.json'))
                        value={'input':{'request_id':arm+'-'+label,'session_id':session},'http_status':200,'output':out,'recovered_from_published_artifact':True}
                        if label=='confirm':confirmation=value
                        else:reused=value
            else:confirmation=post(api,'이 최종 답을 이번 경험으로 확정해서 기억해줘.','confirm');reused=None
            eid=confirmation['output'].get('experience_id');secondary={'confirmation':confirmation,'queries':{}}
            for kind in ('user_wiki','legal_wiki','experience'):
                if kind=='experience' and not eid:continue
                body={'query_kind':kind,**({'experience_id':eid} if kind=='experience' else {'question':''})}
                response=api.post('/v1/rag/memory/query',json=body);secondary['queries'][kind]={'input':body,'http_status':response.status_code,'output':response.json()}
            if eid:secondary['reuse']=reused or post(api,case['question'],'reuse',session=cid+'-new')
            put(d/'secondary.json',secondary)
    inherited=read(d/'inherited-provider/usage.json') if (d/'inherited-provider/usage.json').exists() else []
    put(d/'summary.json',{'complete':True,'provider_attempts':len(list((d/'inherited-provider').glob('call-*')))+client.calls,
        'usage':inherited+client.usage,'new_physical_calls':client.calls,'product_turns':len(products),'seconds':sum(x['seconds'] for x in products),
        'main_unchanged':True,'interrupted_segments_not_normal_latency':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--arm',required=True);a=p.parse_args();main(a.case,a.arm)
