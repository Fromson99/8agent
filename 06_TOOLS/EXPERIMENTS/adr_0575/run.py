"""Frozen full HTTP/Coordinator/journal run on explicitly synthetic originals."""
from contextlib import nullcontext
import json
from pathlib import Path
import time
import traceback

from harness import R,A,C,candidate,fixture,app,write,sha,synthetic_transport

def noisy_fixture(path):
    from conftest import term_glossary
    from test_document_release import source
    from lawrag.pipeline.term_generation import build_generation
    path.mkdir(parents=True,exist_ok=True);glossary=term_glossary.__wrapped__(path)
    raw=source(path/'source.sqlite',[('d','모의승인규정',[
        '원칙상 이사회 승인을 받아야 한다. 다만 제2조의 예외를 확인한다.',
        '적법하게 위임된 경우에는 별도 이사회 승인을 받지 않는다.',
        '이사회 승인 실적 통계표: 지난달 승인 처리100건이다. 적용 원칙이나 위임 예외를 규정하는 조문이 아니라 처리 실적을 기록한 표이다.'
    ])])
    build_generation(raw,glossary,path/'built',serving=True)
    return path/'built/generation'

class LiveTransport:
    public_scope = ('d',)
    def __init__(self,client,manifest):
        from lawrag.research.openrouter_legal_adapter import OpenRouterSingleSendAdapter
        self.adapter=OpenRouterSingleSendAdapter(client);self.binding=self.adapter.binding
        self.manifest=manifest;self.calls=[]
    def validate_model(self): return self.adapter.validate_model()
    def authorize(self,query,request,manifest,*,public_question):
        # This fixture was created by this runner, with no real/private input.
        if manifest!=self.manifest or set(query['scope']['document_version_ids'])-{'d'}: raise ValueError('not the frozen synthetic fixture')
        return {'classification':'SYNTHETIC','generation_id':manifest['generation_id']}
    def validate_authorization(self,context):
        if context.binding['generation_id']!=self.manifest['generation_id']: raise ValueError('synthetic binding drift')
    def send_once(self,*,body,ticket):
        self.calls.append(body);return self.adapter.send_once(body=body,ticket=ticket)

def verify():
    m=json.loads((A/'실험/manifest.json').read_text())
    for p,h in m['design']['frozen_inputs'].items(): assert sha(R/p)==h,p
    return m

def one(case,arm,generation,out):
    from fastapi.testclient import TestClient
    from lawrag.research.experiment_client import ExperimentClient
    out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((generation/'manifest.json').read_text())
    client=ExperimentClient(R,out/'calls',max_calls=8,max_output_tokens=4096,schema_in_prompt=False,max_repairs=0)
    transport=LiveTransport(client,manifest)
    record={'case_id':case['id'],'arm':arm,'status':'ERROR','seconds':None,'calls':0,'usage':[],'error':None}
    start=time.perf_counter()
    try:
        with candidate(arm=arm):
            a=app(out,generation,transport,enabled=arm=='integrated')
            with TestClient(a) as http:
                response=http.post('/v1/rag/ask',json={'question':case['question'],'document_ids':['d'],'public_question':True})
                write(out/'http-result.json',{'status_code':response.status_code,'body':response.json()})
                if response.status_code!=200: raise RuntimeError('HTTP '+str(response.status_code))
                value=response.json();write(out/'wire-bodies.json',transport.calls)
                record.update(status='ANSWER',run_id=value['run_id'],answer=value['answer'],assembly=value['assembly'])
    except Exception as exc:
        record['error']={'type':type(exc).__name__,'message':str(exc)};(out/'error.txt').write_text(traceback.format_exc())
    record.update(seconds=time.perf_counter()-start,calls=client.calls,usage=client.usage)
    write(out/'result.json',record);print(json.dumps({k:record[k] for k in ['case_id','arm','status','seconds','calls','error']},ensure_ascii=False),flush=True)
    return record

def generation_roundtrip(generation,records,out):
    from fastapi.testclient import TestClient
    from lawrag.research.experiment_client import ExperimentClient
    from lawrag.core.action_memory import Memory,episode_from_journal
    from lawrag.pipeline.action_memory import build
    path=out/'generation-roundtrip';path.mkdir()
    t=synthetic_transport()
    send=t.send_once
    def select_norms(*,body,ticket):
        from test_legal_agent_double_harness import wire
        v=json.loads(body['messages'][1]['content'])['view']
        if v.get('source_stage')=='source-triage' and v.get('originals'):
            t.calls.append(body)
            choices=[{'id':c['id'],'reason':'이사회 승인 원칙 및 적법한 위임 예외'} for c in v['originals'] if all('통계표' not in e['text'] for e in c['excerpts'])]
            return wire({'issues':['승인 원칙과 위임 예외'],'choices':choices})
        return send(body=body,ticket=ticket)
    t.send_once=select_norms
    a=app(path,generation,t,enabled=True)
    with TestClient(a) as http:
        value=http.post('/v1/rag/ask',json={'question':'이사회 승인 원칙과 위임 예외를 확인해 주세요.','document_ids':['d']})
        if value.status_code!=200: raise ValueError('synthetic log generation failed')
    write(path/'initial-api.json',value.json())
    import shutil
    for record in records:
        if record['arm']!='integrated' or record['status']!='ANSWER': continue
        source=out/'cases'/record['case_id']/'integrated/runtime/legal-agent/runs'
        for journal in source.glob('*/*/journal.sqlite'):
            target=path/'runtime/legal-agent/runs'/journal.parent.parent.name/journal.parent.name/'journal.sqlite'
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(journal,target)
    allowed_synthetic_generations={json.loads((g/'manifest.json').read_text())['generation_id'] for g in [generation,out/'fixture/built/generation']}
    client=ExperimentClient(R,path/'concept-calls',max_calls=1,max_output_tokens=4096,schema_in_prompt=True,max_repairs=0)
    class Model:
        def eligible(self,e): return e['binding']['generation_id'] in allowed_synthetic_generations
        def generate(self,episodes,concepts,remaining,output):
            from lawrag.core.action_memory import CONCEPT_SYSTEM,concept_input,concept_schema
            return client.generate(CONCEPT_SYSTEM,concept_input(episodes,concepts),concept_schema(episodes,concepts),phase='concept-generation')
    status=build(R,runtime=path/'runtime',manual=True,model=Model(),batch_size=8,max_seconds=180)
    write(path/'build-result.json',status)
    follow_client=ExperimentClient(R,path/'followup-calls',max_calls=8,max_output_tokens=4096,schema_in_prompt=False,max_repairs=0)
    transport=LiveTransport(follow_client,json.loads((generation/'manifest.json').read_text()))
    a=app(path,generation,transport,enabled=True)
    with TestClient(a) as http:
        follow=http.post('/v1/rag/ask',json={'question':'적법하게 권한을 위임한 경우 이사회 승인이 필요한지 원칙과 예외를 확인해 주세요.','document_ids':['d'],'public_question':True})
    write(path/'followup-api.json',{'status_code':follow.status_code,'body':follow.json()})
    write(path/'followup-wire.json',transport.calls)
    first=json.loads(transport.calls[0]['messages'][1]['content'])['view'] if transport.calls else {}
    memory=Memory(path/'runtime/action-memory/memory.sqlite',readonly=True)
    try: active_exclusions=memory.db.execute("SELECT count(*) FROM observation WHERE predicate='EXCLUDES' AND status='ACTIVE'").fetchone()[0]
    finally: memory.close()
    result={'state':status['state'],'generated_concepts':status['concepts'],'relations':status['relations'],'proposed_exclusions':status['proposed_exclusions'],
        'actual_next_request_received_concepts':bool(first.get('investigation_concepts')),'followup_status':follow.status_code,
        'generation_calls':len(list((path/'concept-calls').glob('call-*'))),'followup_calls':follow_client.calls,'usage':(json.loads((path/'concept-calls/usage.json').read_text()) if (path/'concept-calls/usage.json').exists() else [])+follow_client.usage,
        'exclusions_applied_without_review':bool(active_exclusions),
        'actual_logs_synthetic':True}
    write(path/'result.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def main():
    verify();out=A/'artifacts/run-001';out.mkdir(exist_ok=False)
    # Source generation is shared and produced before replacing any modules.
    generation=fixture(out/'fixture');noise=noisy_fixture(out/'noise-fixture')
    write(out/'data-bindings.json',{'fixture_manifest_sha256':sha(generation/'manifest.json'),'noise_manifest_sha256':sha(noise/'manifest.json')})
    cases=json.loads((A/'artifacts/design/cases.json').read_text());rows=[]
    for i,case in enumerate(cases):
        order=['baseline','integrated'] if i%2==0 else ['integrated','baseline']
        for arm in order: rows.append(one(case,arm,generation,out/'cases'/case['id']/arm))
    with candidate():
        try: learned=generation_roundtrip(noise,rows,out)
        except Exception as exc:
            learned={'state':'FAILED','error_type':type(exc).__name__,'message':str(exc)};write(out/'generation-error.json',learned);print(json.dumps(learned),flush=True)
    write(out/'result.json',{'status':'complete','classification':'SYNTHETIC','results':rows,'generation':learned})

if __name__=='__main__': main()
