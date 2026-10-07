"""Independent original-case assertions against the newly built generation."""
import json,pathlib,sqlite3,sys,hashlib
R=pathlib.Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0527-frame-anchor-identity-repair'
G=R/'01_DATA/TERM_RELEASES/adr0527-frame-anchors-v1/generation'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0527/repaired/revisions/rev-001/snapshot/02_BACKEND';sys.path.insert(0,str(C))
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex
from semantic_runtime.fulltext import FulltextIndex
from semantic_runtime.structure_navigation import stored_units,stored_coordinate
from semantic_runtime.contracts import digest

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
with __import__('contextlib').closing(Store(G)) as store:
 index=TermIndex(G/'navigation',store);ft=FulltextIndex(G/'fulltext',index.manifest)
 db=sqlite3.connect((G/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
 examples={}
 for f in ('audit.json','hierarchy_audit.json'):examples.update(read(R/'07_DOCS/REFERENCE/REPORTS/REFERENCE_CONNECTION_REPAIR_PLAN_20260922'/f)['examples'])
 checks=[];details={}
 def check(name,ok,description):checks.append({'check':name,'passed':bool(ok),'criterion':description})
 def refs(name):
  r=examples[name]['reference']
  return [json.loads(j) for (j,) in db.execute("SELECT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id=? AND json_extract(r.json,'$.source_id')=? AND json_extract(r.json,'$.block_id')=?",(r['source_id'],r['source_id'],r['block_id']))]
 def find(name,needle):
  rows=refs(name);details[name]=rows
  return [r for r in rows if needle in r['mention_text']]
 def paths(rows):return [t['unit_path'] for r in rows for t in r['targets']]
 rows=find('additional_mok_truncation','제1항제2호라목');check('mok_exact',paths(rows)==[['①','2.','라.']],'full 1항2호라목, not the enclosing item')
 rows=find('enumerated_mok_omission','제7항제1호나목');check('mok_list',sorted(p[-1] for p in paths(rows))==['나.','다.'],'both listed letters restored')
 rows=find('range_parent_mismatch','제2항제1호부터');check('range_parent',paths(rows)==[['②','1.'],['②','2.'],['②','3.']],'explicit 2항 retained for all range endpoints')
 rows=refs('annex_branch_and_self_heading');details['annex_branch_and_self_heading']=rows;check('annex_heading',not rows,'own annex title generates no reference')
 rows=find('same_paragraph_mismatch','같은 항 제4호가목');check('same_paragraph',paths(rows)==[['②','4.','가.']],'same paragraph binds to preceding 2항 and full 가목')
 rows=find('inline_mok_child_lost','나목2)');ts=[t for r in rows for t in r['targets']];check('inline_child',len(ts)==1 and ts[0]['block_ids']==['702'] and ts[0]['unit_path'][-1]=='2)' and ts[0]['spans'][0]['start_cp']>0,'inline 2) in original block702 with exact nonzero character start')
 rows=find('separate_blocks_mok_children_lost','가목(2)');ts=[t for r in rows for t in r['targets']];check('separate_child',len(ts)==1 and ts[0]['block_ids']==['1242'] and ts[0]['unit_path'][-1]=='(2)','only original block1242')
 rows=find('head_only_includes_children','각 호 외의 부분 단서');ts=[t for r in rows for t in r['targets']];check('head_proviso',len(ts)==1 and ts[0]['block_ids']==['35'] and ts[0]['spans'][0]['start_cp']>0,'proviso in common head, no child item36/37')
 for name in ('ho_misclassified_as_hang','merged_letter_markers_and_role_gap'):
  rows=find(name,'제1호');check(name,any(r['targets'] and r['targets'][0]['unit_path'][-1]=='1.' for r in rows),'actual first item remains 호 without missing paragraph')
 rows=find('reverse_endpoint_includes_mok_siblings','제80조제5항제1호');check('inverse_endpoint',any(r['source_block_ids']==['1242'] and r['source_unit_path'][-1:]==['(2)'] for r in rows),'inverse origin is only its actual nested unit')
 rows=find('known_mok_truncation','나목 단서');check('known_proviso',any(r['targets'] and r['targets'][0]['unit_path'][-1]=='나.' and r['targets'][0].get('qualifiers')==['단서'] for r in rows),'letter and proviso both retained')
 # Consumer binding and stored query coordinates use the same actual anchors.
 units=stored_units(store);new=[(k,u) for k,u in units.items() if k[1].startswith('scope:')]
 good=0
 for (did,uid),u in new:
  c=stored_coordinate(units,did,uid)
  if c:good+=1
  else:
   cur=uid;seen=set()
   while (did,cur) in units and cur not in seen:
    seen.add(cur);parent=units[(did,cur)]
    if (parent.get('legal_coordinate') or {}).get('unit')=='조':break
    cur=parent['parent']
   else:good+=1 # Non-article namespace anchors use their actual frame path, not a fabricated legal article.
 check('new_structure_coordinates',good==len(new),'new subunits under actual legal articles have inherited coordinates; annex/frame-only anchors remain in their own namespace')
 diagnosis=read(A/'artifacts/collision-diagnosis.json')
 expected={}
 for collision in diagnosis['collisions']:
  for item in (collision['first'],collision['later']):
   targets=item['targets']
   if len(targets)!=1:continue
   endpoint=targets[0]['source_id']
   parts=[item['source_id'],item['block_id'],item['mention_start'],item['mention_end'],item['document_name_hint'],
          'official_delegation_lawgokr',item['locator'],endpoint]
   rid='ref:'+digest(parts)[:24]
   expected[rid]=(item['source_id'],endpoint,item['locator'])
 present={}
 for rid,want in expected.items():
  row=db.execute('SELECT json FROM reference WHERE id=?',(rid,)).fetchone()
  if row:
   item=json.loads(row[0]);actual=(item['source_id'],item['targets'][0]['source_id'],item['locator']) if len(item['targets'])==1 else None
   present[rid]=actual
 check('delegation_collision_recovered',len(present)==len(expected) and all(present[rid]==want for rid,want in expected.items()),
       'each previously overwritten official delegation endpoint exists under its distinct stable reference ID')
 details['delegation_collision_recovery']={'expected_distinct_endpoints':len(expected),'present':len(present),'missing_ids':sorted(set(expected)-set(present))}
 result={'schema_version':'frame-anchor-verification-v1','checks':checks,'all_passed':all(x['passed'] for x in checks),'new_units':len(new),'coordinate_units':good,'counts':index.manifest['counts'],'bindings':{'store':store.manifest['store_sha256'],'navigation':index.manifest['index_sha256'],'fulltext':ft.manifest['fulltext_sha256']},'examples':details,'quality_certified':False}
 (A/'artifacts/generation-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='examples'},ensure_ascii=False,indent=2))
 sys.exit(0 if result['all_passed'] else 1)
