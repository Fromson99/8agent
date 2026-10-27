"""Known failed baseline diagnosis, never a new product or quality holdout."""
from common import *
from native_transport import *
import ast

old=ROOT/'04_EXPERIMENTS/ADR/ADR-1075-main104-post-sql-live-check/artifacts/run-001/fsc-hard-005'
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1076-navigation-view-preparation-reuse/artifacts/run-002/baseline'
historical_journal=ROOT/read(old/'result.json')['journal_paths'][0]
current_journal=next((prior/'runtime').rglob('journal.sqlite'))
with gzip.open(old/'wire/038.json.gz','rt') as stream:expected=json.load(stream)
db=sqlite3.connect(current_journal.resolve().as_uri()+'?mode=ro')
try:actual=json.loads(db.execute('SELECT request_json FROM model_attempt ORDER BY rowid DESC LIMIT 1').fetchone()[0])
finally:db.close()
def choice(body):return json.loads(body['messages'][1]['content'])['view']['domain_choice']['choice_id']
proof=validate_domain_records(domain_record(historical_journal,choice(expected)),domain_record(current_journal,choice(actual)))
before=compare_request(expected,actual);after=compare_request(expected,actual,domain_proof=proof)
require(not before['protected_request_exact'] and after['protected_request_exact'],'Known compose difference not exactly isolated')
def nodes(path):
    tree=ast.parse(path.read_text())
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(tree)
            if isinstance(n,ast.FunctionDef) and n.name in ('view','timed')}
old_runner=ROOT/'06_TOOLS/EXPERIMENTS/adr_1076/native_replay.py'
new_runner=ROOT/'06_TOOLS/EXPERIMENTS/adr_1081/native_replay.py'
require(nodes(old_runner)==nodes(new_runner),'Compared view timing wrapper changed')
put(DESIGN/'compose-preflight.json',{'known_in_sample':True,'product_executed':False,
    'old_baseline_result':bound(prior/'result.json'),'old_runner':bound(old_runner),'new_runner':bound(new_runner),
    'expected_journal':bound(historical_journal),'actual_journal':bound(current_journal),
    'proof':proof,'before':before,'after':after,'timing_wrappers_ast_equal':True,
    'interpretation':'The failed1076 result stays failed. This proves one server-generated ID difference is bound to unchanged recorded selection and offer; it is not a new outcome or product quality test.'})
print('Known compose preflight PASS; two native journal IDs verified, no product execution')
