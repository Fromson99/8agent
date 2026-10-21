"""Offline exact discovery/read/return/citation coverage of user feedback locations."""
from pathlib import Path
import gzip,json,sqlite3,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
known={'3-6':{'source_id':'article:d338e0e2b3d1f626cc047f7b','block':'469'},'3-24-4':{'source_id':'article:c3af79efc692a91026430460','block':'814'},'3-26(7)':{'source_id':'article:10c815112abfecf4d1097e37','block':'897'}}
def walk(v):
 if isinstance(v,dict):
  yield v
  for x in v.values():yield from walk(x)
 elif isinstance(v,list):
  for x in v:yield from walk(x)
for arm in ('rebased','bridged'):
 P=A/'artifacts/run-001'/arm/'leverage-comparison'
 if not (P/'audit.json').exists():continue
 a=read(P/'audit.json');views=[];term_events=[];coverage={k:{'hint_views':[],'read':False,'returned':False,'cited':False,'read_block':False,'returned_block':False,'cited_block':False} for k in known}
 for file in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
  with gzip.open(file,'rt',encoding='utf8') as f:value=json.load(f)
  v=value['view'];outpath=file.with_name(file.name.replace('.json.gz','-output.json.gz'))
  if outpath.exists():
   with gzip.open(outpath,'rt',encoding='utf8') as f:output=json.load(f)
  else:output={}
  nodes=list(walk(v));actions=v.get('actions',[]);actions=list(actions.values()) if isinstance(actions,dict) else actions
  target=output.get('target_id');selected=next((x for x in actions if x.get('id')==target),None) if target else None
  term=v.get('document_term_candidates');refs=v.get('references',{})
  views.append({'number':int(file.name[:3]),'stage':v.get('source_stage'),'reference_anchors':len(refs.get('current_anchors',[])),'reference_cards':len(refs.get('dependency_cards',[])),'term_pages':[{k:r.get(k) for k in ('document_id','status','terms','total','next_action')}|{'source_ids':[x['source_id'] for x in r.get('items',[])]} for r in (term or {}).get('documents',[])],'lead_count':len(v.get('investigation_leads',{}).get('items',[])),'parent_next_tasks':[task for item in output.get('items',[]) for task in item.get('next_tasks',[])],'choice':{'target_id':target,'action':selected,'reason':output.get('reason')}})
  for k,w in known.items():
   if any(n.get('source_id')==w['source_id'] for n in nodes):coverage[k]['hint_views'].append(int(file.name[:3]))
 for j in a['journals']:
  path=R/j['path'];db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  for row in db.execute("SELECT payload_json FROM event WHERE kind='DOCUMENT_TERM_CANDIDATES'"):term_events.append({'side':j['side'],**json.loads(row[0])})
  for e in db.execute('SELECT evidence_id,source_id,document_id FROM evidence_unit'):
   for k,w in known.items():
    if e['source_id']!=w['source_id']:continue
    has=bool(db.execute('SELECT 1 FROM evidence_span WHERE evidence_id=? AND block_id=?',(e['evidence_id'],w['block'])).fetchone())
    if j['side']=='external':coverage[k]['read']=True;coverage[k]['read_block']|=has
    if j['side']=='parent':
     returned=e['evidence_id'] in a['children'].get('external',{}).get('returned_evidence_ids',[])
     cited=e['evidence_id'] in a['evidence_refs']
     coverage[k]['returned']|=returned;coverage[k]['cited']|=cited
     coverage[k]['returned_block']|=returned and has;coverage[k]['cited_block']|=cited and has
  db.close()
 result={'arm':arm,'legal_gold':False,'coverage':coverage,'model_views':views,'term_queries':term_events,'limits':'hint_views means any source ID in the recorded model view, not proof of original text delivery. Separate exact journal blocks establish acquisition/return/citation. Article 3-24-4 block814 is the first applicable paragraph witness, not whole-article completeness.'}
 (P/'trace.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(arm,json.dumps(coverage,ensure_ascii=False))
