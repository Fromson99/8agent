"""Exact parent-record projections; no live model or large index loading."""
from common import *
import sys,tarfile,tempfile,sqlite3,os
C=ROOT/read(ART/'stage.json')['roots']['candidate'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import unit_relations as rel
from semantic_runtime.legal_agent.navigation_input import expand_cards,compact_cards
P=ROOT/read(ART/'stage.json')['parent']/'artifacts/known-query/candidate'
with tarfile.open(P/'runtime.tar.gz') as t:
    member=next(m for m in t.getmembers() if m.name.endswith('cases-v4.sqlite'))
    with tempfile.NamedTemporaryFile() as f:
        f.write(t.extractfile(member).read());f.flush();db=sqlite3.connect(f.name)
        saved=json.loads(db.execute('select payload from stage_progress where payload like ? order by rowid desc limit 1',('%"reference_states"%',)).fetchone()[0]);db.close()
states=[]
def find(v):
    if isinstance(v,dict):
        if 'reference_states' in v:states.append(v)
        for x in v.values():
            if isinstance(x,(dict,list)):find(x)
    elif isinstance(v,list):
        for x in v:
            if isinstance(x,(dict,list)):find(x)
find(saved)
assert states
state=next(v for v in states if any(x.get('queue') for x in v['reference_states'].values()))
queued=next(x['queue'] for x in state['reference_states'].values() if x.get('queue'))
raw=read(P/'model/call-005-service/request.json');view=expand_cards(json.loads(next(x['content'] for x in raw['messages'] if x['role']=='user'))['view'])
old_targets=[g['target']['source_id'] for g in view['groups']]
view['groups']=[rel.directory_menu(g,'R1-'+str(i+1).zfill(3)) for i,g in enumerate(queued)]
view.pop('all_group_summaries',None)
view['connection_directory']={'version':'selected-scope-directory-v1','listed_groups':len(queued),'queued_groups':len(queued),'catalog_complete':False,'unselected_status':'UNEXAMINED','absence_proven':False}
view['omitted_groups']=0
wire=compact_cards(view);expanded=expand_cards(wire)
targets=[g['target']['source_id'] for g in expanded['groups']]
assert targets==[g['target']['source_id'] for g in queued]
required='article:645fca288aa46a513eadc1ed'
assert required in targets and required not in old_targets
offered={row['id']:g for row,g in zip(view['groups'],queued)}
rel.validate({'decisions':[],'needs_more':False},offered,sparse=True)
sizes=[]
for p in sorted((P/'model').glob('call-*/request.json')):
    if not any(x in p.parent.name for x in ('002','003','004')):continue
    raw=read(p);before=json.loads(next(x['content'] for x in raw['messages'] if x['role']=='user'))['view']
    original=expand_cards(before);packed=compact_cards(original)
    assert expand_cards(packed)==original
    sizes.append({'call':p.parent.name,'before_utf8_bytes':len(json.dumps(before,ensure_ascii=False).encode()),'after_utf8_bytes':len(json.dumps(packed,ensure_ascii=False).encode()),'lossless':True})
reduction=1-sum(r['after_utf8_bytes'] for r in sizes)/sum(r['before_utf8_bytes'] for r in sizes)
report={'directory':{'queued_groups':len(queued),'visible_groups':len(targets),'previous_visible_groups':len(old_targets),
    'decree163_visible':required in targets,'source_ids_unchanged':True,'canonical_chars':len(json.dumps(view,ensure_ascii=False)),
    'wire_chars':len(json.dumps(wire,ensure_ascii=False)),'all_read_options_preserved':all(expanded['groups'][i]['read_options']==rel.menu(g,'x')['read_options'] for i,g in enumerate(queued))},
    'navigation_inputs':sizes,'total_utf8_reduction_ratio':reduction,'criteria_met':reduction>=.1 and len(json.dumps(view,ensure_ascii=False))<98000,
    'model_calls':0,'source_archive_sha256':sha(P/'runtime.tar.gz')}
save(ART/'offline-projection.json',report)
print(json.dumps(report,ensure_ascii=False,indent=2))
