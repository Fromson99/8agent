"""Read-only contract reproduction on the actual stored endpoint from ADR0999."""
from common import *
import sys,sqlite3
from types import SimpleNamespace as S
s=read(ART/'stage.json');C=ROOT/s['roots']['candidate']
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
from semantic_runtime.legal_agent import unit_relations as rel
G=ROOT/s['base_release']['data_path']
db=sqlite3.connect((G/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-0999-original-context-inline-live-rerun/artifacts'
d=read(prior/'article-endpoint-diagnosis.json')
reference=json.loads(db.execute('select json from reference where id=?',(d['reference']['id'],)).fetchone()[0])
endpoint=reference['targets'][0];sid=endpoint['source_id']
source=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0])
session=S(tools=S(sources={sid:source}),scope=[source['document_id']])
blocks=rel.endpoint_blocks(session,endpoint)
assert blocks==d['canonical_target_block_ids']
assert rel.blocks_covered(blocks,d['acquired_target_block_ids'])
assert not rel.blocks_covered(blocks,d['acquired_target_block_ids'][:-1])
empty_count=db.execute("select count(*) from reference,json_each(reference.json,'$.targets') where json_array_length(value,'$.block_ids')=0 and json_extract(value,'$.target_level')='article'").fetchone()[0]
save(ART/'real-data-contract.json',{'status':'PASS','stored_reference_id':reference['id'],
 'stored_endpoint':endpoint,'canonical_blocks':blocks,'acquired_blocks':d['acquired_target_block_ids'],
 'whole_read_is_covered':True,'partial_read_is_covered':False,'empty_article_endpoint_count':empty_count,
 'prior_failure_path':str((prior/'article-endpoint-diagnosis.json').relative_to(ROOT)),
 'prior_failure_sha256':sha(prior/'article-endpoint-diagnosis.json'),'model_calls':0})
print('Real stored endpoint:',len(blocks),'blocks; complete/partial PASS; empty article endpoints',empty_count)
db.close()
