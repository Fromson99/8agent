"""Exact staged entry/navigation consumers; no grading data in product execution."""
from common import *
from types import SimpleNamespace as S
import sys,time,copy,traceback,resource,inspect,pytest
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
arm,cid=sys.argv[1:3];preflight='--preflight' in sys.argv;seal=read(ART/'stage.json');code=ROOT/seal['roots'][arm]
for n,h in seal['files'][arm].items():assert sha(code/n)==h,n
manifest=read(ADR/'실험/manifest.json')
if not preflight:assert sha(ART/'cases.json')==manifest['dataset']['sha256']
if arm=='candidate' and not preflight:
    binding=manifest['design']['code_isolation']['candidates'][0];path=ROOT/binding['manifest_path']
    assert sha(path)==binding['manifest_sha256']
    frozen=read(path);assert frozen['revisions'][-1]['revision_sha256']==binding['revision_sha256']
    targets={r['snapshot_path']:r['target_path'] for r in frozen['files']}
    for r in frozen['revisions'][-1]['files']:
        assert sha(ROOT/r['frozen_path'])==r['snapshot_sha256']==sha(code/targets[r['snapshot_path']])
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag,lawrag.pipeline
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'));lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import query_scope as qs,request_entry as entry,law_navigation as ln,decision_projection as dp
from semantic_runtime.legal_agent import unit_reading as ur,law_candidates as lc,completion_contracts as cc
from semantic_runtime.legal_agent.corrected_memory import Memory
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.unit_fulltext import UnitFulltextIndex
from test_bounded_source_main import settings
from test_legal_agent_double_harness import BINDING
assert Path(entry.__file__).resolve().is_relative_to(code)
case=next(c for c in read(ART/'cases.json') if c['id']==cid)
out=ART/('harness-preflight' if preflight else 'trials')/cid/arm;out.mkdir(parents=True,exist_ok=False)
client=S(calls=0,usage=[]) if preflight else ExperimentClient(ROOT,out/'model',max_calls=2,max_output_tokens=6000)
profile={**settings(),'model_binding':BINDING,'request_entry_policy':'fused-title-v1',
    'max_model_attempts':8,'max_read_chars':30000,'page_size':64,
    'candidate_navigation':{'mode':'law-first-v1','structure_first':True,'selectable_search':True,
        'compact_input':True,'investigation_control':True,'completion_contract':True,
        'completion_policy_version':'investigation-completion-v8','assessment_reentry_limit':0,'answer_first':True}}
class NoHiddenCalls:
    binding=BINDING
    def validate_model(self):return {'verified':True,'synthetic':True}
    def send_once(self,**kwargs):raise AssertionError('Unrecorded native model call')
gen=ART/'synthetic/built/generation';rt=out/'runtime'
app=create_app(ROOT,gen,contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',
    legal_agent_profile=profile,legal_agent_transport=NoHiddenCalls(),runtime_root=rt)
p=app.state.pipeline;p.term_agent.unit_fulltext=UnitFulltextIndex(ART/'synthetic/unit-index',read(gen/'navigation/manifest.json'))
started=time.monotonic();observations=[];result={'case_id':cid,'arm':arm,'route':case['route'],'error':None,'blocks':[],'requested_units':[],'decision':None}
def invoke(system,data,schema,phase,*args):
    if time.monotonic()-started>180:raise TimeoutError('frozen trial time budget')
    observations.append({'phase':phase,'data':copy.deepcopy(data)})
    if preflight:
        assert cid in ('set-20','set-28'),'Preflight only the independent single-node control'
        coordinate='제8조제4항제6호'
        if phase.startswith('request-entry'):
            return {'routing':{'mode':'CASE','answer':'','reason':'Harness control'},
                'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
                    'queries':['설비보전운영규정 '+coordinate],'format':'prose','reason':'Harness control',
                    'search_scope_change':{'operation':'REPLACE','user_quote':case['question'],
                        'targets':[{'document':'설비보전운영규정','structure':'제8조 제4항 제6호'}]}},
                'intent':{'purpose':'원문 확인','concepts':['점검'],'issues':[{'id':'Q1','question':'원문 확인','subject':'점검','kind':'OTHER','request_quote':case['question']}]},
                'context_quotes':[],'search':{'mode':'STRUCTURE','title_hint_ids':[],'reason':'Harness control'}}
        rule=next(r for r in schema['anyOf'] if r['properties']['choice'].get('const')=='LOCATE')
        return {'choice':'LOCATE','target':rule['properties']['target']['enum'][0],
            'issue_id':rule['properties']['issue_id']['enum'][0],'missing_need':'Harness control',
            'relation':'DIRECT','source_ref':None,
            'structure_filter':{'coordinate':coordinate,'title':'','coordinate_scope':'body'}}
    return client.generate(system,data,schema,phase=phase)
request={'question':case['question'],'document_ids':case['scope'],'use_llm':False}
try:
    with p.term_agent.open_session(request,query=p.plan(case['question'],case['scope']),runtime=rt/'native') as native:
        s=native.sources;s.profile.update(profile);pairs=[]
        try:
            if case['route']=='entry':
                executor=S(binding={'code':seal['files'][arm],'generation':sha(gen/'manifest.json')},
                    model=S(ensure=lambda:native,pipeline=p),shortcut_flags={})
                repo=Memory(rt/'entry.sqlite',executor,invoke)
                repo._entry_body={'question':case['question'],'document_ids':case['scope'],'session_id':'synthetic','request_id':cid}
                repo._entry_principal={'user_id':'synthetic','team_id':'risk_team','document_ids':case['scope']}
                context={'utterance':case['question'],'goals':[],'knowledge':[],'wiki_links':{},
                    'allowed_documents':[{'id':d,'name':s.matcher.documents[d]} for d in case['scope']]}
                try:
                    entry.run(repo,context)
                    result['decision']=executor.request_entry
                    command=executor.request_entry['command']
                    if command and command['method_id']=='CASE_START':
                        change=command.get('search_scope_change')
                        scope=qs.resolve(change,None,s.matcher,s.scope,case['question']) if change else None
                        if scope:
                            qs.attach(s,scope);result['scope']=scope
                            pairs=[(r['document_id'],r['unit_id']) for r in scope['targets'] if r['unit_id'] is not None]
                        else:
                            from semantic_runtime.legal_agent.structure_query import resolve
                            route=resolve(' '.join(command.get('queries') or []),s.matcher,s.scope)
                            if route['status']=='MATCH':pairs=[(r['document_id'],r['unit_id']) for r in route['pairs']]
                finally:repo.close()
            else:
                rec=SourceRecall(s).prepare()
                inv=ln.Investigation(s,case['question'],rec,invoke,180,None,None)
                inv.p['window']='structure'
                inv.p['structure_page']=qs.catalogue(s,document_id='A',limit=4)
                data,actions=inv.view();decision=dp.choose_read(inv,data,actions,'source-law-navigation-1')
                result['decision']=decision
                inv.execute(decision,data,actions)
                result['structure_page']=inv.p.get('structure_page')
                if decision['next_action'] in ('SEARCH_STRUCTURE','RETRY_LAW_STRUCTURE'):
                    page=inv.p['structure_page'];record=page.get('selection_resolution')
                    if record:pairs=[(record['document_id'],u) for u in record['unit_ids']]
                    else:pairs=[(r['document_id'],r['unit_id']) for r in page['items']]
                else:
                    for r in inv.p['selected'].values():result['blocks'].extend(
                        {'document_id':r['document_id'],**span} for e in r['evidence'] for span in e['spans'])
            result['requested_units']=[{'document_id':d,'unit_id':u} for d,u in pairs]
            state=ur.read_state(s)
            for did,uid in pairs:
                for sid in s.matcher._unit_sources(did,uid):
                    hit=lc.structure_hit(s,sid,uid);offers=ur.offers(s,hit)
                    offer=next((o for o in offers if o['unit_id']==uid and o['extent']=='subtree'),None)
                    if offer is None:raise RuntimeError('Selected subtree has no exact READ offer')
                    r=ur.read(s,hit,offer,action_state=state)
                    if not r['complete']:raise RuntimeError('Incomplete selected original READ')
                    for evidence in r['evidence']:
                        s.source.verify(evidence)
                        result['blocks'].extend({'document_id':did,**span} for span in evidence['spans'])
            result['state_binding']=native.work.binding
        except Exception as exc:
            result['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
finally:
    p.store.close()
    result.update(observations=observations,model_calls=client.calls,usage=client.usage,
        seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(out/'result.json',result)
print(json.dumps({'case':cid,'arm':arm,'calls':client.calls,'error':result['error'] and result['error']['type'],'blocks':len(result['blocks'])},ensure_ascii=False),flush=True)
