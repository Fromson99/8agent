"""Known failure diagnostic with native metadata/reader; no model invocation."""
from pathlib import Path
import json,sys,hashlib
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0758-accepted-query-title-routing'
O=A/'artifacts/known-route';O.mkdir(exist_ok=False)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0758/integrated/revisions/rev-001/snapshot'
sys.path.insert(0,str(C/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent.workflow_tiers_policy import profile as validate_profile
from semantic_runtime.legal_agent.unified_runtime import open_cases
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.law_navigation import Investigation
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=read(R/'04_EXPERIMENTS/ADR/ADR-0757-dependency-recovery-qualification/artifacts/design/bindings.json')
q=read(R/'04_EXPERIMENTS/ADR/ADR-0757-dependency-recovery-qualification/artifacts/design/dataset.json')['cases'][0]['question']
class NoModel(LocalGemmaTransport):
    def send_once(self,**kw):raise AssertionError('metadata diagnostic cannot invoke model')
t=NoModel(C,R);policy=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');policy.update(model_binding=t.binding,max_output_tokens=t.policy['max_output_tokens']);policy=validate_profile(policy,require_model=True)
principal={'user_id':'adr0758-local','team_id':'public-laws','authenticated':True,'document_ids':list(t.public_scope)}
body={'question':q,'document_ids':list(t.public_scope),'public_question':True,'use_llm':True,'session_id':'known-route','request_id':'known-route'}
app=create_app(O,R/b['source_generation'],contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',legal_agent_profile=policy,legal_agent_transport=t,runtime_root=O/'runtime',memory_identity=lambda _:principal)
cases=open_cases(app.state.pipeline,O/'binding-runtime',body,principal)
try:
    s=cases.model_resource.ensure().sources
    s.entry_search={'mode':'STRUCTURE'}
    queries=['상법 회사 업무 재산상태 검사 검사인 선임 청구 요건','상법 검사인 조사 보고 의무 주주총회 소집 명령','상법 이사 감사 조사 보고 의무 회사 업무 재산상태 검사']
    s.recall_query_plan={'queries':queries,'law_names':['상법']}
    rec=SourceRecall(s).prepare();page=rec['structure_catalogue']
    assert rec['law_navigation']['query_origin']=='accepted_request_queries'
    assert rec['law_navigation']['route_queries']==queries
    assert page['items'][0]['source_id']=='article:156659ad50c11f9d4d562f52',page['items']
    assert not any(r.get('coordinate')=='제310조' for r in page['items'])
    inv=Investigation(s,q,rec,None,120,None,None);view,actions=inv.view()
    valid=[a for a in actions.values() if a.get('action')=='READ_STRUCTURE' and a.get('source_id')=='article:156659ad50c11f9d4d562f52']
    # The catalogue itself carries no acquired/evidence status. Verify menu
    # action by original unit identity (action payloads need not carry source_id).
    row=page['items'][0]
    valid=valid or [a for a in actions.values() if a.get('identity',{}).get('document_id')==row['document_id'] and str(a.get('identity',{}).get('unit_id'))==str(row['unit_id']) and a.get('action','').startswith('READ')]
    assert valid,actions
    result={'passed':True,'known_in_sample':True,'model_calls':0,'query_origin':rec['law_navigation']['query_origin'],'queries':queries,'top_coordinate':row['coordinate'],'top_source_id':row['source_id'],'read_action_count':len(valid),'code_files':{n:sha(C/n) for n in ['02_BACKEND/semantic_runtime/legal_agent/law_candidates.py','02_BACKEND/semantic_runtime/legal_agent/law_navigation.py','02_BACKEND/semantic_runtime/legal_agent/structure_query.py']}}
    (O/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
finally:cases.close()
