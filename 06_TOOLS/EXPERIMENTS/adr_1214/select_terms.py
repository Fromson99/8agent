"""Scope the serving lexicon by witnessed corpus links and direct lexical bridges."""
from pathlib import Path
import json,sqlite3,hashlib,collections,time,csv
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1214-gold-main120-engine-implementation';D=A/'artifacts/design';O=A/'artifacts/term-scope';O.mkdir(exist_ok=True)
DATA=R/'01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ro(p):
 c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA cache_size=-16384');return c
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
criteria=read(D/'criteria.json')
if not (D/'criteria-before-connected-only.json').exists():put(D/'criteria-before-connected-only.json',criteria)
criteria['scope']='User steering: serving glossary connects everyday expressions to legal terms and selected original sources. Retain selected source definitions, witnessed dictionary/official term occurrences and direct official lexical bridges. External FIBO/Wikidata/library concepts require REVIEWED_SAME mapping to a retained dictionary entry; mere word occurrence or unreviewed label matching does not establish legal relevance. Preserve relation types/provenance/status; no whole external graph closure. Original dictionaries remain unchanged.'
criteria['user_scope_change']={'request':'용어집우리 연결된것만 남기고 고아 용어는 빼버리는게 어때 ... 일상용어랑 법률용어의 연결','selection':'Corpus link + direct official lexical bridge, explicit external direct mappings; orphan/global unrelated concept exclusion','prior_export':'Interrupted before DB import; raw partial evidence retained','semantic_identity':'No synonym or meaning approval inferred from label match'}
put(D/'criteria.json',criteria)
ids=[x['document_id'] for x in read(D/'documents.json')['documents']]
nav=ro(DATA/'navigation/navigation.sqlite');dictionary=ro(DATA/'glossary/dictionary.sqlite');identity=ro(DATA/'glossary/bundle/identity.sqlite');lookup=ro(DATA/'glossary/cache/c9b659444abbf59fa56ea155820aab5f2cce774250cb7442591a639fcd032055.sqlite')
nav.execute('CREATE TEMP TABLE allowed_doc(id TEXT PRIMARY KEY)');nav.executemany('INSERT INTO allowed_doc VALUES(?)',[(x,) for x in ids])
anchors={r[0] for r in nav.execute('SELECT DISTINCT t.id FROM occurrence_keys o JOIN term t ON t.rowid=o.term_key JOIN source s ON s.rowid=o.source_key WHERE s.document_id IN (SELECT id FROM allowed_doc)')}
definitions={r[0] for r in dictionary.execute('SELECT id FROM corpus_definition WHERE document_id IN ('+','.join('?' for _ in ids)+')',ids)}
entries={r['id']:dict(r) for r in dictionary.execute('SELECT id,source,label,key FROM entry')}
keep=set(anchors)&entries.keys();keep|=definitions
reasons=collections.defaultdict(set)
for x in keep:reasons[x].add('SELECTED_SOURCE_DEFINITION' if x in definitions else 'SELECTED_TERM_OCCURRENCE')
# Official direct witnesses may keep an intermediate term absent from source text.
# No recursive component closure; relation type and direction remain unchanged.
relations=[]
for db,table in ((identity,'official_relation'),(nav,'moleg_relation')):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():continue
 columns=[r[1] for r in db.execute('PRAGMA table_info('+table+')')]
 for r in db.execute('SELECT source_id,target_id,code FROM '+table):
  left,right,code=tuple(r)
  if left in anchors or right in anchors:
   relations.append((left,right,code))
   for x in (left,right):
    if x in entries:keep.add(x);reasons[x].add('DIRECT_OFFICIAL_RELATION:'+code)
# Keep direct external nodes only when an existing admissible mapping reaches a
# retained dictionary entry, or that external concept itself occurs in sources.
external=set();mapping_counts=collections.Counter()
for r in identity.execute('SELECT entry_id,source,node_id,status FROM concept_mapping'):
 if r['entry_id'] in keep and r['status']=='REVIEWED_SAME':
  external.add((r['source'],r['node_id']));mapping_counts[r['status']]+=1
# Generic external concepts occurring as strings (e.g. company-name substrings)
# do not become legal glossary dependencies without an approved mapping.
# Ensure alias resolution can still reach the canonical source node.
alias_pairs=[]
for r in identity.execute("SELECT source,alias_uri,canonical_uri,status FROM uri_alias"):
 if (r['source'],r['alias_uri']) in external or (r['source'],r['canonical_uri']) in external:
  alias_pairs.append(tuple(r))
  if r['status']=='SOURCE_URI_ALIAS':external.add((r['source'],r['canonical_uri']))
keep=sorted(keep);external=sorted(external)
put(O/'selection.json',{'documents':ids,'entry_ids':keep,'external_nodes':[list(x) for x in external],'anchor_term_ids':sorted(anchors),'selected_definition_ids':sorted(definitions),'policy':criteria['scope']})
ks=set(keep);ek=set(external)
retained=collections.Counter(entries[x]['source'] for x in keep if x in entries);removed=collections.Counter(v['source'] for k,v in entries.items() if k not in ks);lookup_keep=0;lookup_sources=collections.Counter()
for r in lookup.execute('SELECT source,node_id,COUNT(*) n FROM label GROUP BY source,node_id'):
 if (r['source']=='dictionary' and r['node_id'] in ks) or (r['source'],r['node_id']) in ek:lookup_keep+=r['n'];lookup_sources[r['source']]+=r['n']
lookup_all=lookup.execute('SELECT COUNT(*) FROM label').fetchone()[0]
report={'document_count':len(ids),'entry_before':len(entries),'entry_after':len(keep),'entry_excluded':len(entries)-len(keep),'retained_sources':dict(retained),'excluded_sources':dict(removed),'source_anchored_term_ids':len(anchors),'source_definitions':len(definitions),'direct_official_relation_witnesses':len(set(relations)),'external_nodes_kept':len(external),'mapping_statuses':dict(mapping_counts),'lookup_rows_before':lookup_all,'lookup_rows_after':lookup_keep,'lookup_rows_excluded':lookup_all-lookup_keep,'lookup_retained_sources':dict(lookup_sources),'original_data_changed':False,'selection_sha256':sha(O/'selection.json'),'no_semantic_equivalence_claim':True}
put(O/'counts.json',report)
with (O/'retained-entries.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['id','source','label','retention_evidence'])
 for k in keep:w.writerow([k,entries.get(k,{}).get('source'),entries.get(k,{}).get('label'),';'.join(sorted(reasons[k]))])
with (O/'excluded-entry-candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['id','source','label','reason'])
 for k,v in entries.items():
  if k not in ks:w.writerow([k,v['source'],v['label'],'No selected source anchor or direct official bridge under frozen rule; exclude serving, retain original'])
for db in (nav,dictionary,identity,lookup):db.close()
m=read(A/'실험/manifest.json');m['design']['execution']=criteria;m['design']['criteria_freeze_evidence']['sha256']=sha(D/'criteria.json');put(A/'실험/manifest.json',m)
print(json.dumps(report,ensure_ascii=False,indent=2))
