"""Read-only CM mandatory coverage and per-document resource inventory."""
from pathlib import Path
import json,sqlite3,hashlib,collections,csv
ROOT=Path('/home/jin/8-AGENT');ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1208-gold-r12-full-migration-vector';D=ADR/'artifacts/design'
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ro(p):
    d=sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True);d.row_factory=sqlite3.Row;return d
active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());release=json.loads((ROOT/active['manifest_path']).read_text());data=ROOT/release['data_path']
store=ro(data/'store.sqlite');docs={r['document_id']:dict(r) for r in store.execute('SELECT document_id,name,source_artifact_sha256 FROM document')}
by_name=collections.defaultdict(list)
for did,r in docs.items():by_name[r['name'].split(' > ')[-1]].append(did)
registry=ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json';cases=[c for c in json.loads(registry.read_text())['cases'] if c['collection']=='cm']
required=set();targets=[]
for c in cases:
    for t in c['targets']:
        old=t.get('doc_id');law=t['law'];matches=[old] if old in docs else by_name[law]
        if len(matches)!=1:raise ValueError(('CM_DOCUMENT_AMBIGUOUS_OR_MISSING',c['id'],law,matches))
        did=matches[0];required.add(did);coordinate=t.get('coordinate_key');units=[]
        for u in store.execute('SELECT unit_id,json FROM source_unit WHERE document_id=?',(did,)):
            raw=json.loads(u['json'])
            if coordinate and raw.get('coordinate_key')==coordinate:units.append(u['unit_id'])
        targets.append({'case_id':c['id'],'law':law,'registered_document_id':old,'current_document_id':did,'document_binding':'same-id' if old==did else 'unique-exact-law-name-current-version','coordinate_key':coordinate,'registered_node':t.get('node'),'current_coordinate_units':units,'historical_source_hash':t.get('source_text_sha256'),'historical_text_equivalence':'not_asserted','current_document_sha256':docs[did]['source_artifact_sha256']})
counts={d:{'document_id':d,'name':r['name'],'source_artifact_sha256':r['source_artifact_sha256'],'cm_mandatory':d in required,'source_units':0,'source_blocks':0,'source_characters':0,'source_payload_utf8_bytes':0,'navigation_sources':0,'fulltext_units':0,'fulltext_postings':0} for d,r in docs.items()}
for table in ['document','source_unit','block_payload']:
    fields=['json']+(['text'] if table=='block_payload' else [])
    expr='+'.join('COALESCE(length(CAST('+f+' AS BLOB)),0)' for f in fields)
    for r in store.execute('SELECT document_id,count(*) n,sum('+expr+') bytes'+(',sum(length(text)) chars' if table=='block_payload' else '')+' FROM '+table+' GROUP BY document_id'):
        x=counts[r['document_id']];x['source_payload_utf8_bytes']+=r['bytes']
        if table=='source_unit':x['source_units']=r['n']
        if table=='block_payload':x.update(source_blocks=r['n'],source_characters=r['chars'])
nav=ro(data/'navigation/navigation.sqlite')
for r in nav.execute('SELECT document_id,count(*) n FROM source GROUP BY document_id'):counts[r['document_id']]['navigation_sources']=r['n']
fts=ro(data/'fulltext/units.sqlite')
for r in fts.execute('SELECT document_id,count(*) n FROM unit GROUP BY document_id'):counts[r['document_id']]['fulltext_units']=r['n']
base=json.loads((ROOT/'04_EXPERIMENTS/ADR/ADR-1198-main117-live-cm007/artifacts/design/corpus.json').read_text())['document_ids']
initial=set(base)|required
missing=[t for t in targets if t['coordinate_key'] and not t['current_coordinate_units']]
result={'user_instruction':'2026-10-29: Oracle subset; around 80% capacity; all CM question documents mandatory. Then user: 해봐.', 'registry':str(registry.relative_to(ROOT)),'registry_sha256':sha(registry),'case_count':len(cases),'target_count':len(targets),'mandatory_document_count':len(required),'mandatory_document_ids':sorted(required),'initial_candidate_document_ids':sorted(initial),'initial_candidate_documents':len(initial),'current_coordinate_missing_targets':missing,'targets':targets,'documents':[counts[d] for d in sorted(initial)],'oracle_database_budget_bytes':9_600_000_000,'budget_note':'80% of conservative decimal 12GB; includes source/search/relationship/vector/index allocations and existing user schemas. Not a fill requirement.','selection_status':'mandatory set fixed; additional document count awaits measured shared-data and index budget'}
put(D/'cm-scope.json',result);put(D/'all-document-costs.json',list(counts.values()))
with (D/'문서별_선정과_용량.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(next(iter(counts.values()))));w.writeheader();w.writerows(counts.values())
old=json.loads((D/'criteria.json').read_text());put(D/'criteria-before-user-subset.json',old)
old.update(scope='User-directed Oracle experiment subset, mandatory CM51 current documents and dependency closure; native schema 13 tables/60 columns. 80% of Oracle Free limit is a hard planning ceiling.',capacity_rule='All-data import abandoned by explicit user choice before execution. Fit mandatory CM and dependencies plus selected additional documents under 9,600,000,000 bytes total; reserve vector/index growth. Never silently remove mandatory documents.',cm_scope_sha256=sha(D/'cm-scope.json'))
put(D/'criteria.json',old)
m=json.loads((ADR/'실험/manifest.json').read_text());m['design'].update(execution=old,criteria_freeze_evidence={'artifact_path':str((D/'criteria.json').relative_to(ROOT)),'sha256':sha(D/'criteria.json')});m['design']['arms'][1]['changes']='R12 native Oracle scoped migration; CM51 mandatory, approximately 80% capacity ceiling; actual vector creation.';put(ADR/'실험/manifest.json',m)
print(json.dumps({k:result[k] for k in ['case_count','target_count','mandatory_document_count','initial_candidate_documents','current_coordinate_missing_targets']},ensure_ascii=False))
