from pathlib import Path
import json,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop';P=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
base=(R/'06_TOOLS/EXPERIMENTS/adr_0517/run_selection.py').read_text().replace('ADR-0517-bounded-provenance-protocol','ADR-0518-five-source-replacement-loop').replace('adr_0517','adr_0518').replace('max_calls=2','max_calls=3')
base=base.replace("raw = read(parent)","raw = read(parent)\n        raw['reference_witnesses'] = read(A/'artifacts/reference-witnesses.json')['references']")
base=base.replace("write(out/'result.json',answer)","write(out/'result.json',answer)\n        if answer.get('source_appendix'): (out/'sources-and-relations.md').write_text(answer['source_appendix']['markdown']+'\\n')")
(R/'06_TOOLS/EXPERIMENTS/adr_0518/run_selection.py').write_text(base)
refs=set()
for p in (P/'artifacts/run-001').glob('*/result.json'):
 d=json.loads(p.read_text())
 for routes in d['routes'].values():
  for route in routes:
   if route.get('reference_id'):refs.add(route['reference_id'])
scope=set(json.loads((A/'product-cases.json').read_text())['public_scope_document_ids'])
db=R/'01_DATA/TERM/relation-subtree-main-serving-20260920-v1/generation/navigation/navigation.sqlite'
c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True);out={}
for ref in sorted(refs):
 r=c.execute('SELECT json FROM reference WHERE id=?',(ref,)).fetchone()
 if not r:continue
 d=json.loads(r[0])
 if d.get('document_id') in scope:out[ref]=d
(A/'artifacts/reference-witnesses.json').write_text(json.dumps({'source_database':str(db.relative_to(R)),'extraction':'exact reference rows for recorded513 routes;public documents only;runtime checks original containment and hash','references':out},ensure_ascii=False,indent=2)+'\n')
print('Witness records',len(out))
