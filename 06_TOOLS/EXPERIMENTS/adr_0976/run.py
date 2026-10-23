"""Sequential, metadata-only corpus audit and native API contracts, model calls 0."""
from pathlib import Path
import sys, json, hashlib, resource, sqlite3, time
from types import SimpleNamespace as S

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0976-division-container-traversal'
ART=ADR/'artifacts'
def read(p): return json.loads(Path(p).read_text())
def save(p,v): Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

arm=sys.argv[1]; code=ART/f'code-{arm}'
stage=read(ART/'stage.json')
assert all(sha(code/n)==h for n,h in stage['files'][arm].items())
sys.dont_write_bytecode=True
sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import lawrag,lawrag.pipeline,lawrag.core
lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
lawrag.pipeline.__path__.append(str(ROOT/'02_BACKEND/lawrag/pipeline'))
lawrag.core.__path__.append(str(ROOT/'02_BACKEND/lawrag/core'))
resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
if sys.argv[2]=='test':
    import pytest
    import semantic_runtime.app as app_module
    original=app_module.create_app
    def create(*a,**kw):
        if Path(kw.get('contracts_root',ROOT)).resolve()==ROOT:kw['contracts_root']=code
        return original(*a,**kw)
    app_module.create_app=create
    import test_legal_agent_double_harness as fixture
    fixture.ROOT=code
    raise SystemExit(pytest.main(sys.argv[3:]))

from semantic_runtime.inherited_navigation import _derive_bindings
from semantic_runtime.legal_agent import structure_selection as ss, structure_query as sq
generation=ROOT/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
db=sqlite3.connect('file:'+str(generation/'store.sqlite')+'?mode=ro',uri=True)
db.execute('PRAGMA cache_size=-4096')
start=time.monotonic(); reports=[]; totals={'documents':0,'nodes':0,'body_articles':0,'reachable_articles':0,'legacy_divisions':0}
for did,name in db.execute('SELECT document_id,name FROM document ORDER BY document_id'):
    raw={}
    for uid,parent,j in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)):
        n=json.loads(j);raw[(did,str(uid))]={**n,'parent':str(parent) if parent is not None else None,'raw_structure':n}
    units,coords=_derive_bindings(raw)
    m=S(units=units,stored_coordinates=coords,documents={did:name})
    expected={uid for (d,uid),c in coords.items() if c and c.unit=='조' and not c.chain
              and units[(d,uid)].get('coordinate_scope')=='body'
              and units[(d,uid)].get('coordinate_binding',{}).get('mode')!='unresolved'}
    legacy=[uid for (d,uid),c in coords.items() if c and c.unit in ('편','장','절','관')
            and units[(d,uid)].get('coordinate_scope')=='repeated']
    reason=None
    try: reached=set(ss.Nodes(m,did,'body').descendants(None,'조'))
    except ss.SelectionError as e: reached=set();reason=e.code
    missed=expected-reached
    totals['documents']+=1;totals['nodes']+=len(units);totals['body_articles']+=len(expected)
    totals['reachable_articles']+=len(reached);totals['legacy_divisions']+=len(legacy)
    if missed or legacy or reason:
        reports.append({'did':did,'name':name,'nodes':len(units),'expected':len(expected),
                        'reached':len(reached),'legacy_divisions':len(legacy),'missed':sorted(missed),'reason':reason})
    if did=='7bbe815ff43b6635':
        sel={'coordinate_scope':'body','groups':[{'parent_path':[],'unit':'조','include':[{'kind':'SINGLE','value':{'n':434}}],'exclude':[]}]}
        try: commercial=ss.resolve(sel,m,did,[did]);ss.verify(commercial,m,[did])
        except ss.SelectionError as e:commercial={'code':e.code,'message':str(e)}
    if totals['documents']%200==0: print(arm,totals['documents'],flush=True)
db.close()
save(ART/f'audit-{arm}.json',{'totals':totals,'documents':reports,'commercial_434':commercial,
     'seconds':time.monotonic()-start,'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
     'model_calls':0,'generation_manifest_sha256':sha(generation/'manifest.json')})
print(json.dumps(totals), 'commercial',commercial.get('unit_ids',commercial.get('code')),flush=True)
