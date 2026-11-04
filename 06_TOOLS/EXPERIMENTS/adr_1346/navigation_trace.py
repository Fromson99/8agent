"""Read-only audit of completed model choices and relation presentation."""
from common import *
import sqlite3

C=ROOT/read(DES/'candidate-bounded.json')['code_root']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage
case_id=sys.argv[1] if len(sys.argv)>1 else 'charter'
base=ART/('public-live/'+case_id+'-bounded')
assert (base/'resource-final.json').exists()

def walk(v,path=''):
    if isinstance(v,dict):
        yield path,v
        for k,x in v.items():yield from walk(x,path+'/'+k)
    elif isinstance(v,list):
        for i,x in enumerate(v):yield from walk(x,path+'/'+str(i))

frames=[]
for p in sorted((base/'canonical').glob('[0-9][0-9][0-9].json.gz')):
    d=read(p);v=d['view'];op=p.with_name(p.name.replace('.json.gz','-output.json.gz'))
    out=read(op) if op.exists() else None
    cards=[];sources=[];scopes=[];controls=[]
    for path,x in walk(v):
        if 'direction' in x and ('reference_witness' in x or 'connections' in x):cards.append({'path':path,'value':x})
        if isinstance(x.get('spans'),list) and x.get('document_id'):sources.append({'path':path,**{k:x.get(k) for k in ('id','source_id','document_id','heading','coordinate','text')},'block_ids':list(dict.fromkeys(str(s.get('block_id')) for s in x['spans']))})
        for key in ('connection_scope_choices','connection_review','selected_scope_id','structure_selection_progress'):
            if key in x:scopes.append({'path':path+'/'+key,'value':x[key]})
        for key in ('repair_feedback','source_goals','source_goal_execution','answer_progress_context'):
            if key in x:controls.append({'path':path+'/'+key,'value':x[key]})
    frames.append({'number':int(p.name[:3]),'stage':v.get('source_stage',d['phase']),'output':out,'sources':sources,'relation_cards':cards,'scopes':scopes,'controls':controls})

events=[]
for p in sorted((base/'runtime').rglob('*.sqlite')):
    db=journal_storage.connect(p.as_uri()+'?mode=ro',uri=True)
    tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'event' in tables and {'kind','payload_json'}<={x[1] for x in db.execute('PRAGMA table_info(event)')}:
        for row in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'):
            if any(k in row['kind'] for k in ('CONNECTION','READ','SOURCE_GOAL','ASSESS','REJECT','STOP','SUPERVIS')):
                events.append({'journal':str(p.relative_to(base)),'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
    db.close()
ref=write_raw_json(ART/(case_id+'-navigation-trace.json.gz'),{'frames':frames,'events':events,'read_only':True,'new_model_calls':0})
put(ART/(case_id+'-navigation-trace-ref.json'),ref)
for f in frames:
    o=f['output'] or {}
    print(json.dumps({'number':f['number'],'stage':f['stage'],'output_keys':list(o),'output':o,'source_blocks':[s['block_ids'] for s in f['sources']],'relation_card_count':len(f['relation_cards'])},ensure_ascii=False)[:5500])
