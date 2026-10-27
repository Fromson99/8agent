"""Prove the recorded alias-only failure without executing a product request."""
from common import *
from native_transport import *
from handle_proof import prove_aliases
import sys

code=ROOT/'08_DEPLOYMENT/RELEASES/navigation-sql-20261027-r1/code'
sys.path.insert(0,str(code/'02_BACKEND'))
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
require(Path(sys.modules[NavigationReferences.__module__].__file__).resolve()==code/'02_BACKEND/semantic_runtime/legal_agent/navigation_input.py','Unexpected alias codec')
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1075-main104-post-sql-live-check/artifacts/run-001/fsc-hard-005'
failed=ROOT/'04_EXPERIMENTS/ADR/ADR-1078-navigation-bound-replay/artifacts/run-002/optimized'
old_journal=ROOT/read(old/'result.json')['journal_paths'][0]
new_journal=next((failed/'runtime').rglob('journal.sqlite'))
with gzip.open(old/'wire/036.json.gz','rt') as stream:expected=json.load(stream)
db=sqlite3.connect(new_journal.resolve().as_uri()+'?mode=ro')
try:actual=json.loads(db.execute('SELECT request_json FROM model_attempt ORDER BY rowid LIMIT 1 OFFSET 35').fetchone()[0])
finally:db.close()
response=read(next((old/'raw').glob('call-036-*'))/'response.json')
before=compare_request(expected,actual)
left,right,proof=prove_aliases(expected,actual,response,old_journal,new_journal,NavigationReferences)
after=compare_request(left,right)
require(not before['schema_exact'] and not before['protected_request_exact'] and after['schema_exact'] and after['protected_request_exact'], 'Known alias mismatch not exactly isolated')
put(DESIGN/'alias-preflight.json',{'known_in_sample':True,'product_executed':False,'failed_source':bound(failed/'result.json'),
    'old_journal':bound(old_journal),'new_journal':bound(new_journal),'alias_codec':bound(code/'02_BACKEND/semantic_runtime/legal_agent/navigation_input.py'),
    'before':before,'after':after,'proof':proof,'request_rewritten':False,'response_rewritten':False,
    'interpretation':'1078 remains failed under its original raw-schema criterion. This establishes a new prospective comparison rule only: canonical body/preview exact, each domain identity journal-bound, V aliases native-reconstructed, unchanged literal response references no changed alias and validates under current schema.'})
print('Known V alias preflight PASS; full canonical content and native reversible mappings verified')
