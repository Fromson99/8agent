"""Prospectively fixed fictional threshold cases; no corpus or internal data."""
from pathlib import Path
import sys,json,hashlib,time,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0811-workflow-version-source-binding';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
arm=sys.argv[1];f=read(D/'freeze.json');assert all(sha(R/n)==h for n,h in f['files'].items())
base=read(D/'baseline.json');C=R/(f['code_root'] if arm=='connected' else base['manifest']['code_root']);O=A/'artifacts/model'/arm;O.mkdir(parents=True,exist_ok=False)
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'02_BACKEND'),str(R/'02_BACKEND')]
from workflow.adapters.projection import prepare
from workflow.risk_team_compare_workflow import compare as cmp
from workflow.risk_team_compare_workflow.contracts import COMPARE,DIMENSIONS
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.model_contract import structured_request,structured_content
from lawrag.research.experiment_client import ExperimentClient
from jsonschema import validate
cases=read(D/'model-cases.json');client=ExperimentClient(R,O/'raw',max_calls=len(cases),max_output_tokens=4000,max_repairs=0)
results=[]
for case in cases:
    # The expected verdict is deliberately read only after the product result.
    internal=case['internal'];external=case['external'];issue={'id':'i','label':case['question'],'numeric':True}
    sources=[{'evidence_id':side,'side':side,'document_id':side,'metadata':{'document_name':'모의내규' if side=='internal' else '모의외규'},'spans':[{'text':text}],'text':text,'source_complete':True,'version_verified':True} for side,text in [('internal',internal),('external',external)]]
    citations=[{'evidence':e['evidence_id'],'quote':e['text']} for e in sources]
    pair={'pair_id':'p','issue_id':'i','internal':['internal'],'external':['external'],'applicability':{'status':'MATCH','reason':'동일한 모의 대상과 기준일을 명시함','as_of':'2026-10-01','citations':citations},'basis_relation':'DIRECT','basis_path':[{'from_evidence':'internal','to_evidence':'external','citation':citations[0]}],'comparison_eligibility':True,'reason':'가상 문서의 명시 참조와 적용 조건','content_difference':'','content_citations':[]}
    data={'question':case['question'],'scope':{'issues':[issue]},'as_of':'2026-10-01','sources':sources,'basis':{'pairs':[pair],'gaps':[]},'packet':{'dependency_closure_complete':True,'index':0,'count':1,'plan_hash':case['id']}}
    # Use the actual COMPARE call's instructions from the selected arm, captured
    # without touching corpus or reimplementing its model-facing wording.
    import workflow.presentation as presentation
    presentation.packets=lambda *a,**k:[(data,sources)]
    presentation.checkpoint=lambda *a:None
    from types import SimpleNamespace as NS
    captured={}
    class Capture(Exception):pass
    def capture(stage,view,schema,instructions,checked):captured.update(stage=stage,view=view,schema=schema,instructions=instructions,checked=checked);raise Capture()
    state={'basis':data['basis'],'scope':data['scope']}
    ctx=NS(request={'use_llm':True},repo=NS(save=lambda s:None,work=NS(event=lambda *a:None)),model=NS(decide=capture))
    try:cmp.compare(ctx,state)
    except Capture:pass
    assert captured
    view,schema,expand,receipt=prepare('COMPARE',captured['view'],captured['schema'])
    instructions=captured['instructions']+' 이 입력은 외부기관·회사 실자료가 아닌 명시적 모의 규정이다. 현재 schema의 모든 수치 차원을 각각 판단하라.'
    body=provider_request(structured_request(model='qwen/qwen3.8-27b',max_tokens=4000,schema_name='WorkflowNumericComparison',schema=schema,messages=[{'role':'system','content':instructions},{'role':'user','content':json.dumps({'view':view},ensure_ascii=False)}]))
    put(O/(case['id']+'-binding.json'),{'code_root':str(C.relative_to(R)),'projection':receipt,'dimensions':DIMENSIONS,'request_sha256':hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
    start=time.monotonic();result={'case_id':case['id'],'canonical_valid':False,'verdict':None}
    try:
        raw=client.chat_completions(body,phase='numeric-'+case['id'],timeout_seconds=180)
        assert raw['body_json']['model']=='qwen/qwen3.8-27b' and raw['body_json']['provider']=='Parasail'
        proposal=json.loads(structured_content(raw['body_json'],require_complete=True));put(O/(case['id']+'-proposal.json'),proposal)
        validate(proposal,schema);canonical=expand(proposal);put(O/(case['id']+'-canonical.json'),canonical)
        validate(canonical,COMPARE);captured['checked'](canonical)
        result.update(canonical_valid=True,verdict=canonical['rows'][0]['verdict'])
    except Exception as exc:result.update(error_type=type(exc).__name__,error=str(exc)[:4000])
    result.update(elapsed_seconds=time.monotonic()-start,expected=case['expected'],correct=result['canonical_valid'] and result['verdict']==case['expected'])
    results.append(result);put(O/'result.json',{'arm':arm,'results':results,'model_calls':client.calls,'usage':client.usage,'quality_certified':False,'scope':'synthetic comparison only; no retrieval/full workflow quality claim'})
    print(json.dumps(result,ensure_ascii=False),flush=True)
