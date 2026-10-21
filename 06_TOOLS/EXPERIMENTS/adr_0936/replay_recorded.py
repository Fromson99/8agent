"""Deterministic contract checks of captured failures, no model/search replay."""
from pathlib import Path
import sys,json,gzip,tarfile,sqlite3,tempfile,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0936-durable-research-review-patch'
binding=json.loads((A/'artifacts/design/fixed-binding.json').read_text());sys.path.insert(0,str(R/binding['code_root']/'02_BACKEND'))
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board as tb
import jsonschema
checks=[]
for case,pairs in [('pf-downgrade',[(9,10),(10,11)]),('leverage',[(17,17),(18,18)])]:
 P=R/'04_EXPERIMENTS/ADR/ADR-0935-lossless-review-wire/artifacts/run-001/fixed'/case
 with tempfile.TemporaryDirectory(prefix='adr0936-recorded-') as temporary,tarfile.open(P/'raw-runtime.tar.gz','r:gz') as tar:
  name=next(n for n in tar.getnames() if n.endswith('/journal.sqlite') and '/children/' not in n)
  for member in tar.getnames():
   if member.startswith(name):
    with tar.extractfile(member) as source,(Path(temporary)/Path(member).name).open('wb') as target:shutil.copyfileobj(source,target)
  db=sqlite3.connect('file:'+str(Path(temporary)/'journal.sqlite')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  for number,physical in pairs:
   data=json.load(gzip.open(P/'canonical'/f'{number:03}.json.gz','rt'))['view'];options=[s['citation_options'] for s in data['sources']]
   for source in data['sources']:
    source.pop('citation_options');source['spans']=[dict(r) for r in db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal',(source['evidence_id'],))]
   schema=tb.review_contract(list(data['fields']),data['new_evidence_ids'],True)
   shown,wire,expand,receipt=projection.prepare('ITEMS',data,schema)
   assert options==[s['citation_options'] for s in shown['sources']]
   assert shown['citation_catalogue_hash']==data['citation_catalogue_hash']
   name=next(n for n in tar.getnames() if n.startswith(f'raw/call-{physical:03}-') and n.endswith('/response.json'))
   response=json.load(tar.extractfile(name));raw=json.loads(response['choices'][0]['message']['content'])
   value=expand(raw);jsonschema.validate(value,schema)
   tb.checked_update(value,data['sources'],list(data['fields']),data['locators'],data['new_evidence_ids'],True)
   checks.append({'case':case,'logical_call':number,'physical_call':physical,'same_exact_citation_catalogue':True,'canonical_checks_pass':True,
    'new_originals':len(data['new_evidence_ids']),'returned_fields':[v['field'] for v in value['items']],
    'normalizations':receipt['normalizations'],'scope':'Recorded response contract only; no new source search, model call or end-to-end replay.'})
  db.close()
(A/'artifacts/recorded-shape-check.json').write_text(json.dumps({'checks':checks,'external_model_calls':0},ensure_ascii=False,indent=2)+'\n')
print([(c['case'],c['physical_call'],c['canonical_checks_pass']) for c in checks])
