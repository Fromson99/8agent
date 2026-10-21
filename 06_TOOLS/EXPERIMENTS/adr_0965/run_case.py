"""Frozen native investigation consumer; no gold is loaded into product calls."""
from common import *
import sys,time,resource,traceback,copy
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
arm,case_id=sys.argv[1:3]
seal=read(ART/'stage.json');code=ROOT/seal['roots'][arm]
for p,h in seal['files'][arm].items():assert sha(code/p)==h,p
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
import lawrag.pipeline
lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
from lawrag.research.experiment_client import ExperimentClient
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent import law_navigation as ln, query_scope as qs
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.unit_fulltext import UnitFulltextIndex
from test_bounded_source_main import settings
from test_legal_agent_double_harness import BINDING
assert Path(ln.__file__).resolve().is_relative_to(code)
manifest=read(ADR/'실험/manifest.json');assert sha(ART/'cases.json')==manifest['dataset']['sha256']
if arm=='candidate':
    binding=manifest['design']['code_isolation']['candidates'][0]
    path=ROOT/binding['manifest_path'];assert sha(path)==binding['manifest_sha256']
    frozen=read(path);revision=frozen['revisions'][-1]
    assert revision['revision_sha256']==binding['revision_sha256']
    targets={r['snapshot_path']:r['target_path'] for r in frozen['files']}
    for row in revision['files']:
        assert sha(ROOT/row['frozen_path'])==row['snapshot_sha256']
        assert sha(code/targets[row['snapshot_path']])==row['snapshot_sha256']
case=next(c for c in read(ART/'cases.json') if c['id']==case_id)
out=ART/'trials'/case_id/arm
assert not out.exists(),'Completed or partial trial cannot silently rerun'
out.mkdir(parents=True)
client=ExperimentClient(ROOT,out/'model',max_calls=8,max_output_tokens=3000)
profile={**settings(),'model_binding':BINDING,'max_model_attempts':32,'max_read_chars':20000,
 'candidate_navigation':{'mode':'law-first-v1','structure_first':True,'selectable_search':True,
 'compact_input':True,'investigation_control':True,'completion_contract':True,
 'completion_policy_version':'investigation-completion-v8','assessment_reentry_limit':0}}
gen=ART/'synthetic/built/generation';rt=out/'runtime'
class InertNativeTransport:
    binding=BINDING
    def validate_model(self):return {'verified':True,'synthetic':True,'native_model_calls':0}
    def send_once(self,**kwargs):raise AssertionError('Native model calls forbidden; use ExperimentClient')
app=create_app(ROOT,gen,contracts_root=code,provider=object(),implementation='legal-agent-unified-v6',
 legal_agent_profile=profile,legal_agent_transport=InertNativeTransport(),runtime_root=rt)
p=app.state.pipeline
p.term_agent.unit_fulltext=UnitFulltextIndex(ART/'synthetic/unit-index',read(gen/'navigation/manifest.json'))
snapshots=[];started=time.monotonic();record={'case_id':case_id,'arm':arm,'sources':[],'selected':[],'error':None}
def invoke(system,data,schema,phase,timeout):
    snapshots.append(copy.deepcopy(data))
    if time.monotonic()-started>300:raise RuntimeError('frozen case wall budget exhausted')
    return client.generate(system,data,schema,phase=phase)
request={'question':case['question'],'document_ids':case['scope'],'use_llm':False}
try:
    with p.term_agent.open_session(request,query=p.plan(case['question'],case['scope']),runtime=rt/'investigation') as native:
        s=native.sources
        s.profile.update(profile)
        rec=SourceRecall(s).prepare()
        inv=ln.Investigation(s,case['question'],rec,invoke,300,None,None)
        inv.p['structure_page']=qs.catalogue(s,queries=[case['lookup']])
        initial=copy.deepcopy(inv.p['structure_page']);record['initial']=initial
        try:
            result=inv.run()
            record['result']=result
            for row in result.get('read_scopes',[]):
                hit=s.matcher.sources[row['source_id']];did=hit['document_id'];uid=hit['unit_id']
                coordinate=s.matcher.stored_coordinates[did,uid].canonical_surface()
                record['selected'].append({'doc_id':did,'node':coordinate})
            record['sources']=result.get('selected_originals',[])
        except Exception as exc:
            record['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        record['state']=inv.p
        record['observations']=snapshots
        record['source_coordinates']=[{'doc_id':d,'node':c.canonical_surface()} for (d,u),c in s.matcher.stored_coordinates.items() if c and c.unit=='조']
finally:
    p.store.close()
    record.update(model_calls=client.calls,usage=client.usage,seconds=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(out/'result.json',record)
print(json.dumps({'case':case_id,'arm':arm,'calls':client.calls,'error':record['error'] and record['error']['type'],'selected':record['selected']},ensure_ascii=False),flush=True)
