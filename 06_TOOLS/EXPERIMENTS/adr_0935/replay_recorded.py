"""Offline contract check of two recorded failures; never a product/model input."""
from pathlib import Path
from copy import deepcopy
import sys,json,gzip,tarfile,sqlite3,tempfile,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0935-lossless-review-wire'
binding=json.loads((A/'artifacts/design/fixed-binding.json').read_text())
sys.path.insert(0,str(R/binding['code_root']/'02_BACKEND'))
from workflow.adapters import projection
from workflow.risk_team_compare_workflow import task_board as tb
import jsonschema
P=R/'04_EXPERIMENTS/ADR/ADR-0934-host-source-links-priority/artifacts/run-001/fixed/leverage'
audit=json.loads((P/'audit.json').read_text())
by={e['evidence_id']:e for c in audit['children'].values() for e in c['all_read_evidence']}
checks=[]
with tempfile.TemporaryDirectory(prefix='adr0935-recorded-') as temporary,tarfile.open(P/'raw-runtime.tar.gz','r:gz') as tar:
    name=next(n for n in tar.getnames() if n.endswith('/journal.sqlite') and '/children/' not in n)
    for member in tar.getnames():
        if member.startswith(name):
            with tar.extractfile(member) as source,(Path(temporary)/Path(member).name).open('wb') as target:shutil.copyfileobj(source,target)
    db=sqlite3.connect('file:'+str(Path(temporary)/'journal.sqlite')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    for number in (13,14):
        data=json.load(gzip.open(P/'canonical'/f'{number:03d}.json.gz','rt'))['view']
        old_options=[s['citation_options'] for s in data['sources']]
        for source in data['sources']:
            source.pop('citation_options');source['spans']=[dict(r) for r in db.execute('SELECT * FROM evidence_span WHERE evidence_id=? ORDER BY ordinal',(source['evidence_id'],))]
        schema=tb.review_contract(list(data['fields']),data['new_evidence_ids'],True)
        shown,wire,expand,receipt=projection.prepare('ITEMS',data,schema)
        assert old_options==[s['citation_options'] for s in shown['sources']]
        assert shown['citation_catalogue_hash']==data['citation_catalogue_hash']
        name=next(n for n in tar.getnames() if n.startswith(f'raw/call-{number:03d}-') and n.endswith('/response.json'))
        response=json.load(tar.extractfile(name));raw=json.loads(response['choices'][0]['message']['content'])
        value=expand(raw);jsonschema.validate(value,schema)
        tb.checked_update(value,data['sources'],list(data['fields']),data['locators'],data['new_evidence_ids'],True)
        checks.append({'parent_call':number,'same_exact_citation_catalogue':True,'canonical_checks_pass':True,
            'new_originals':len(data['new_evidence_ids']),'returned_fields':[v['field'] for v in value['items']],
            'normalizations':receipt['normalizations'],'scope':'Recorded response contract only; no new source search, model call or claim of end-to-end replay.'})
    db.close()
(A/'artifacts/recorded-shape-check.json').write_text(json.dumps({'checks':checks,'external_model_calls':0},ensure_ascii=False,indent=2)+'\n')
print([(c['parent_call'],len(c['normalizations']),c['canonical_checks_pass']) for c in checks])
