"""Independent original-case assertions against the newly built generation."""
import json,pathlib,sqlite3,sys,hashlib
R=pathlib.Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0531-reference-overlay-storage'
G=R/'01_DATA/TERM_RELEASES/adr0531-reference-overlay-v1/generation'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0530/repaired/revisions/rev-003/snapshot/02_BACKEND';sys.path.insert(0,str(C))
from semantic_runtime.storage import Store
from types import SimpleNamespace
from bootstrap import load_candidate
from semantic_runtime.fulltext import FulltextIndex
from semantic_runtime.structure_navigation import stored_units,stored_coordinate
from semantic_runtime.contracts import digest

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
with __import__('contextlib').closing(Store(G)) as store:
 index=SimpleNamespace(manifest=read(G/'navigation/manifest.json'));ft=FulltextIndex(G/'fulltext',index.manifest)
 db=load_candidate().open_research_overlay(G)
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
 diagnosis=read(R/'04_EXPERIMENTS/ADR/ADR-0527-frame-anchor-identity-repair/artifacts/collision-diagnosis.json')
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
 previously_missing=read(R/'04_EXPERIMENTS/ADR/ADR-0527-frame-anchor-identity-repair/artifacts/missing-extended-mok.json')['items']
 restored=[]
 for item in previously_missing:
  coordinate=stored_coordinate(units,item['document_id'],item['unit_id'])
  restored.append({'unit_id':item['unit_id'],'coordinate':coordinate.canonical_surface() if coordinate else None})
 check('extended_mok_coordinates',all(item['coordinate'] and '제12조제3호' in item['coordinate']
                                       for item in restored),'all six previously missing 소득세법 descendant coordinates inherit actual article 12 item 3')
 details['extended_mok_coordinates']=restored
 old_screen=read(R/'04_EXPERIMENTS/ADR/ADR-0527-frame-anchor-identity-repair/artifacts/coordinate-screen.json')
 exact_annex=[item for item in old_screen['samples']['following_mok'] if item['coordinate_status']=='EXACT' and item['targets']]
 annex_rechecks=[]
 for item in exact_annex:
  rows=[json.loads(raw) for (raw,) in db.execute(
      "SELECT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id "
      "WHERE e.source_id=? AND json_extract(r.json,'$.source_id')=? "
      "AND json_extract(r.json,'$.block_id')=?",
      (item['source_id'],item['source_id'],item['block_id']))]
  label=item['tail'].lstrip()[:2]
  hits=[row for row in rows if row['origins']==['raw_explicit_annex_hint'] and label in row['mention_text']]
  annex_rechecks.append({'old_id':item['id'],'hits':len(hits),'statuses':[row['coordinate_status'] for row in hits],
                         'inspection':[len(row['inspection_targets']) for row in hits],
                         'canonical_targets':[len(row['targets']) for row in hits]})
 check('annex_prefix_no_exact',len(annex_rechecks)==3 and all(x['hits']==1 and x['canonical_targets']==[0]
                     and x['inspection'][0]>0 for x in annex_rechecks),'three previously exact annex-prefix rows now retain witness-bound inspection without a false canonical edge')
 details['annex_prefix_rechecks']=annex_rechecks
 # Independent real-source regression: the article's parenthetical sentence and
 # trailing amendment note are outside the requested second main-body sentence.
 from_id='article:b2cf38efbc915bd830523655'
 to_id='article:dcc3960aeaf3291934ac57bf'
 q=[json.loads(raw) for (raw,) in db.execute(
     "SELECT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id "
     "WHERE e.source_id=? AND json_extract(r.json,'$.source_id')=?",(from_id,from_id))]
 hits=[row for row in q if row['mention_text']=='제69조 후단']
 target_source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(to_id,)).fetchone()[0])
 expected_sentence='이 경우 취득한 자기주식은 대통령령으로 정하는 기간 이내에 처분하여야 한다.'
 actual=[]
 for row in hits:
  for t in row['targets']:
   for p in t.get('spans',[]):
    block=next((b for b in target_source['blocks'] if str(b['block_id'])==str(p['block_id'])),None)
    actual.append(block['text'][p['start_cp']:p['end_cp']] if block else None)
 exact=(len(hits)==1 and hits[0]['coordinate_status']=='EXACT' and
        len(hits[0]['targets'])==1 and hits[0]['targets'][0]['source_id']==to_id and
        actual==[expected_sentence] and
        db.execute('SELECT 1 FROM reference_end WHERE source_id=? AND reference_id=?',
                   (to_id,hits[0]['id'])).fetchone() is not None)
 check('real_article69_second_sentence',exact,
       '제69조 후단 is only the actual second main-body sentence, excluding parenthetical sentence and amendment note, with forward and inverse endpoint')
 details['real_article69_second_sentence']={'reference_ids':[row['id'] for row in hits],
                                             'statuses':[row['coordinate_status'] for row in hits],
                                             'target_text':actual,'expected_text':expected_sentence}
 from lawrag.core.legal_coordinate import MOK_LETTERS,parse_label
 from lawrag.core.structure.lawxml import _mok_unit,_match_line
 from lawrag.core.structure.lexicon import default
 from lawrag.core.structure.model import Block
 from lawrag.core.structure.proposers.hangul_jamo import propose
 import xml.etree.ElementTree as ET
 lex=default();matching=[]
 for n,label in enumerate(MOK_LETTERS,1):
  unit=_mok_unit(ET.fromstring(f'<목><목번호>{label}.</목번호><목내용>{label}. 본문</목내용></목>'))
  flat=_match_line(f'{label}. 본문',False)
  candidates=propose(Block(idx=0,text=f'{label}. 본문'),lex)
  matching.append(unit.ordinal==(n,) and flat and flat.ordinal==(n,) and
                  lex.numerals.read(label)==n and candidates and
                  candidates[0].ordinal==(n,) and parse_label(f'{label}.').n==n)
 check('future_long_mok_ingestion',len(MOK_LETTERS)==48 and all(matching),
       'all 48 observed mok glyphs agree across legal coordinate, raw law XML, flat reader, and generic proposer lexicon')
 details['future_long_mok_ingestion']={'observed_letters':MOK_LETTERS,'matching_count':sum(bool(x) for x in matching)}
 # The original law ends its first main sentence in 가액., while an earlier
 # 포함한다. sits inside parentheses. Neither may be confused with the mok label.
 preface=read(R/'04_EXPERIMENTS/ADR/ADR-0529-complete-qualifier-ingestion/artifacts/new-preface-regression.json')
 from_id=preface['source_id'];to_id=preface['target_id']
 q=[json.loads(raw) for (raw,) in db.execute(
     "SELECT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id "
     "WHERE e.source_id=? AND json_extract(r.json,'$.source_id')=?",(from_id,from_id))]
 hits=[row for row in q if row['mention_text']=='제58조의2제2항제1호가목 전단']
 target_source=json.loads(db.execute('SELECT json FROM source WHERE id=?',(to_id,)).fetchone()[0])
 block=next(b for b in target_source['blocks'] if str(b['block_id'])==preface['target_block_id'])
 end=preface['actual_first_main_sentence_ends_at']
 spans=[p for row in hits for t in row['targets'] for p in t.get('spans',[])]
 exact=(len(hits)==1 and hits[0]['coordinate_status']=='EXACT' and
        len(hits[0]['targets'])==1 and hits[0]['targets'][0]['source_id']==to_id and
        hits[0]['targets'][0]['unit_path'][-1:] == ['가.'] and
        hits[0]['targets'][0].get('qualifiers')==['전단'] and
        len(spans)==1 and spans[0]['block_id']==preface['target_block_id'] and
        spans[0]['start_cp']==0 and spans[0]['end_cp']==end and
        block['text']==preface['target_block_text'] and
        block['text'][0:end].endswith('가액.') and
        db.execute('SELECT 1 FROM reference_end WHERE source_id=? AND reference_id=?',
                   (to_id,hits[0]['id'])).fetchone() is not None)
 check('real_mok_preface_non_da_sentence',exact,
       'actual 제58조의2제2항제1호가목 전단 ends exactly at its top-level 가액. and retains a reverse endpoint')
 details['real_mok_preface_non_da_sentence']={'reference_ids':[row['id'] for row in hits],
                                              'statuses':[row['coordinate_status'] for row in hits],
                                              'spans':spans,'expected_end_cp':end}
 extra=read(R/'04_EXPERIMENTS/ADR/ADR-0530-main-sentence-scope/artifacts/additional-boundary-evidence.json')['rows']
 for item in extra:
  row=db.execute('SELECT json FROM reference WHERE id=?',(item['reference_id'],)).fetchone()
  reference=json.loads(row[0]) if row else None
  targets=reference['targets'] if reference else []
  spans=[p for t in targets for p in t.get('spans',[])]
  raw=item['raw_text']
  if item['name']=='mok_label_ends_da':
   start,end=0,raw.index('한다). 이 경우')+len('한다).')
   name='real_da_mok_preface_closed_parenthesis'
  else:
   start,end=raw.index('이 경우 투자액은'),len(raw)
   name='real_formula_table_second_sentence'
  valid=(reference is not None and reference['coordinate_status']=='EXACT' and
         len(targets)==1 and targets[0]['source_id']==item['source_id'] and
         len(spans)==1 and spans[0]['start_cp']==start and spans[0]['end_cp']==end and
         db.execute('SELECT 1 FROM reference_end WHERE source_id=? AND reference_id=?',
                    (item['source_id'],item['reference_id'])).fetchone() is not None)
  check(name,valid,'actual source boundary excludes mok heading/internal parenthesis or embedded formula sentence while retaining inverse endpoint')
  details[name]={'reference_id':item['reference_id'],'status':reference['coordinate_status'] if reference else None,
                 'spans':spans,'expected_span':[start,end]}
 result={'schema_version':'frame-anchor-verification-v1','checks':checks,'all_passed':all(x['passed'] for x in checks),'new_units':len(new),'coordinate_units':good,'counts':index.manifest['counts'],'bindings':{'store':store.manifest['store_sha256'],'navigation':index.manifest['index_sha256'],'fulltext':ft.manifest['fulltext_sha256']},'examples':details,'quality_certified':False}
 (A/'artifacts/generation-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='examples'},ensure_ascii=False,indent=2))
 sys.exit(0 if result['all_passed'] else 1)
