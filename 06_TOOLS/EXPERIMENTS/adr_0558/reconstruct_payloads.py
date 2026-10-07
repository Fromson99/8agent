"""39 archival wire reconstructions, no product execution or model sends."""
import json,gzip,sqlite3,hashlib,sys,importlib.util
from copy import deepcopy
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0558-model-presentation-repair';OLD=R/'04_EXPERIMENTS/ADR/ADR-0557-structure-main-qwen14/artifacts/run-001'
def read(p):return json.loads(p.read_text())
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def main():
 f=read(A/'artifacts/frozen-design.json');sys.path.insert(0,str(R/f['code_root']/'02_BACKEND'))
 import semantic_runtime.legal_agent as package
 package.__path__.insert(0,str(R/f['candidate_overlays']['presentation']))
 from semantic_runtime.legal_agent.gateway import compact_wire_view
 from semantic_runtime.legal_agent.numbered_references import NumberedReferences
 from semantic_runtime.legal_agent.model_presentation import mapping,unique,INSTRUCTIONS
 rows=[]
 for directory in sorted(OLD.iterdir()):
  path=directory/'structure-main';resultpath=path/'result.json'
  if not resultpath.exists():continue
  result=read(resultpath)
  with gzip.open(path/'trace.json.gz','rt') as z:trace=json.load(z)
  ev={e['evidence_id']:e for e in trace['evidence']}
  j=sqlite3.connect((R/result['journal_path']).resolve().as_uri()+'?mode=ro',uri=True)
  views={k:json.loads(v) for k,v in j.execute('select view_id,body_json from model_view')}
  for rp in sorted((path/'calls').glob('call-*/request.json')):
   request=read(rp);wire=json.loads(request['messages'][1]['content'])['view'];phase=wire.get('source_stage',wire['phase'])
   raw=views.get(wire.get('view_id'))
   if raw is None:
    matches=[v for v in views.values() if v.get('phase')==wire['phase'] and v.get('base_state_revision')==wire.get('base_state_revision')]
    raw=matches[0] if len(matches)==1 else None
   row={'case_id':directory.name,'call':rp.parent.name,'phase':phase,'archive_sha256':hashlib.sha256(rp.read_bytes()).hexdigest(),'baseline_message_chars':sum(len(m['content']) for m in request['messages']),'baseline_wire_chars':len(enc(wire)),'reconstruction_available':raw is not None}
   if raw is None:rows.append(row);continue
   raw=deepcopy(raw)
   for e in raw.get('exact_evidence',[]):
    original=ev[e['evidence']]
    e.update({k:original[k] for k in ('document_id','unit_id','source_artifact_hash','generation_id')})
    # Archival reconstruction can prove stored heading, not a newly executed ancestor chain.
    e['coordinate_label']=original['metadata'].get('heading') or '구조 위치 미확인'
   originalraw=deepcopy(raw)
   for arm in ('presentation','selected-only'):
    raw=deepcopy(originalraw)
    if arm=='selected-only' and phase=='compose':
     selected=set(raw.get('evidence_roles',{}).get('support',[]))
     row['selected_text_chars']=sum(len(e['text']) for e in raw.get('exact_evidence',[]) if e['evidence'] in selected)
     row['excluded_unselected_text_chars']=sum(len(e['text']) for e in raw.get('exact_evidence',[]) if e['evidence'] not in selected)
     # These archived bounded cases have no explicit relation assessment additions.
     assert not any(h['kind']=='relation_assessment' for h in raw.get('work',{}).get('entities',[]))
     raw['exact_evidence']=[e for e in raw.get('exact_evidence',[]) if e['evidence'] in selected]
    for section in ('originals','selected_original_excerpts'):
     for card in raw.get(section,[]):card['via_references']=unique(card.get('via_references',[]))
    for table in ('deferred_candidates','candidates'):
     if isinstance(raw.get(table),dict) and 'rows' in raw[table]:
      for card in raw[table]['rows']:card[4]=unique(card[4])
    projected=compact_wire_view(raw,raw['phase']);refs=NumberedReferences(raw)
    if phase=='compose':row[arm+'_reconstructed_evidence']=len(mapping(raw,projected))
    numbered=('reference_numbers' in wire)
    if numbered:projected=refs.view(projected)
    if phase=='compose':
     projected.pop('navigation_choices',None)
     for kind in ('targets','blocks','cursors'):projected.get('reference_numbers',{}).pop(kind,None)
    row[arm+'_wire_chars']=len(enc(projected))
    row[arm+'_message_chars']=sum(len(m['content']) for m in request['messages'][:1])+len(json.dumps({'view':projected},ensure_ascii=False))+(len(INSTRUCTIONS) if phase=='compose' else 0)
   rows.append(row)
  j.close()
 out={'unit':'Unicode code points, not tokens','execution':'ARCHIVAL_RECONSTRUCTION_ONLY','limitations':['No model calls; archival same-case effect diagnostic','Current grouping-before-limit can expose extra distinct paths; archived reconstruction cannot restore previously omitted paths','Stored heading used; actual live candidate uses stored ancestor chain','Generation30 historical wire with current candidate, not generation31 E2E'],'rows':rows,'totals':{k:sum(r.get(k,0) for r in rows) for k in ('baseline_wire_chars','presentation_wire_chars','selected-only_wire_chars')}}
 assert len(rows)==39,len(rows)
 (A/'artifacts/reconstructed-payloads.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'totals':out['totals'],'compose':[r for r in rows if r['phase']=='compose']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
