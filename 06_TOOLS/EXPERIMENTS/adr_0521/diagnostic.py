"""Small hash-selected historical replay. Product path never reads gold or uses an LLM."""
import json,hashlib,sqlite3,sys,time,gc
from bootstrap import R,A,C,pin
from pathlib import Path
pin()
from semantic_runtime.contracts import sha,write
P=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
F=A/'artifacts/diagnostic-freeze.json'
def prepare():
 old=R/'04_EXPERIMENTS/ADR/ADR-0520-evidence-bound-relation-exploration/artifacts/replay-freeze.json'
 source=json.loads(old.read_text());cases=sorted(source['cases'],key=lambda c:hashlib.sha256(('521:'+c['case_id']).encode()).hexdigest())[:6]
 prod=json.loads((P/'product-cases.json').read_text());lookup={x['case_id']:x for x in prod['cases']}
 for c in cases:
  c['question_input']=lookup[c['case_id']];c['input_sha256']=sha(R/c['historical_raw'])
 frozen={'schema_version':'adr0521-diagnostic-freeze-v1','cases':cases,'seed':'521','selection':'first six ascending sha256(seed:case_id), without gold','input_manifest_sha256':sha(old),'public_scope_document_ids':json.loads((old.parent.parent/'product-cases.json').read_text())['public_scope_document_ids'],'generation':str(R/'01_DATA/TERM_RELEASES/adr0521-shared-reference-v1/generation'),'candidate_revision':json.loads((C/'candidate.json').read_text())['revisions'][-1],'budget':{'max_states':10000,'max_seconds':30},'gold_visible_to_product':False,'answer_quality_measured':False}
 write(F,frozen)
 m=json.loads((A/'실험/manifest.json').read_text())
 for q,c in zip(m['questions'],cases):q['case_id']=c['case_id']
 m['runs'][0]['case_ids']=[c['case_id'] for c in cases]
 m['runs'][0]['selection_rule']='Eleven scoped contracts plus eleven integrated contracts and migrated v5 regression; descriptive replay of six first ascending SHA256(521:historical case ID), fixed before execution. No gold-guided choices, no live model.'
 m['dataset'].update(name='Hash-selected ADR0513 historical roots',version='adr0521-seed521-six',frozen_source=str(F.relative_to(R)),sha256=sha(F))
 (A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'frozen_cases':m['runs'][0]['case_ids']}),flush=True)
def run():
 from semantic_runtime.reference_exploration import ReferenceNavigator
 f=json.loads(F.read_text());g=Path(f['generation']);generation=json.loads((A/'artifacts/generation-result.json').read_text());assert sha(g/'manifest.json')==generation['manifest_sha256']
 db=sqlite3.connect('file:'+str(g/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
 sources={sid:json.loads(raw) for sid,raw in db.execute('SELECT id,json FROM source')}
 nav=ReferenceNavigator(db,sources,f['public_scope_document_ids'],generation['output_index_sha256']);index={}
 for c in f['cases']:
  assert sha(R/c['historical_raw'])==c['input_sha256']
  roots=[]
  for r in c['roots']:
   root=nav.root(r['source_id'],query=str(c['question_input'].get('question','historical query')),reason='Frozen independent discovery receipt');root['discovery_receipts']=r['receipts'];roots.append(root)
  graph=nav.walk(roots,**f['budget']);path=A/'artifacts/run-001'/c['case_id']/'result.json';path.parent.mkdir(parents=True,exist_ok=True)
  originals=[{'source_id':sid,'document_id':sources[sid]['document_id'],'text_sha256':hashlib.sha256(json.dumps(sources[sid]['blocks'],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'chars':sum(len(b['text']) for b in sources[sid]['blocks'])} for sid in graph['source_ids']]
  result={'case_id':c['case_id'],'graph':graph,'originals':originals,'generation':f['generation'],'full_originals_reference':'Immutable source table in hash-bound complete generation; no excerpt-only replacement','model_delivered':0,'model_adopted':0,'historical_roots_are_not_new_model_decisions':True}
  write(path,result);index[c['case_id']]={'path':str(path.relative_to(R)),'sha256':sha(path)}
  print(json.dumps({'case':c['case_id'],'roots':len(roots),'scopes':len(graph['states']),'sources':len(graph['source_ids']),'seconds':round(graph['seconds'],2),'status':graph['status'],'bytes':path.stat().st_size}),flush=True)
  del graph,result;gc.collect()
 write(A/'artifacts/run-001/results.json',{'cases':index,'completed':True,'freeze_sha256':sha(F)})
if __name__=='__main__':{'prepare':prepare,'run':run}[sys.argv[1]]()
