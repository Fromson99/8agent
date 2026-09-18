"""Frozen ordinary contracts + read-only selected-generation metadata wiring audit."""
import sys,json,sqlite3,subprocess,os,importlib
from types import SimpleNamespace
from collections import Counter
from runtime import *

def main():
 if (A/'verification-adapter-fix.json').exists():raise ValueError('completed audit output is immutable')
 module,base,mods,root=load();cm=read(C/'candidate.json');rev=cm['revisions'][-1]
 m=read(D/'실험/manifest.json');m['design']['code_isolation']['candidates']=[{'candidate_id':'multi','experiment_id':m['experiment_id'],'arm_id':'multi','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'runtime.py').relative_to(R)),'runner_sha256':sha(T/'runtime.py')}]
 (D/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path']);path=R/release['data_path'];manifest=read(path/'manifest.json');before=sha(path/'store.sqlite');assert before==manifest['store_sha256']
 paths=list(T.glob('*.py'))+[A/'amended-design-before-implementation.json',A/'origin-projection.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',path/'manifest.json',path/'store.sqlite',path/'navigation/navigation.sqlite',C/'candidate.json']+[R/f['frozen_path'] for f in rev['files']]
 lock={str(p.relative_to(R)):sha(p) for p in paths};new(A/'input-lock-adapter-fix.json',lock)
 db=sqlite3.connect((path/'store.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;ndb=sqlite3.connect((path/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True);ndb.row_factory=sqlite3.Row
 store=SimpleNamespace(db=db,manifest=manifest);documents={r['document_id']:r['name'] for r in db.execute('SELECT document_id,name FROM document')}
 index=importlib.import_module(base.__package__+'.term_index');source_map=index.SourceMap(ndb);lookup=sqlite3.connect(':memory:');lookup.execute('CREATE TABLE label(key)')
 def validate(scope):
  if not scope or not set(scope)<=documents.keys():raise ValueError('invalid authorized scope')
  return list(scope)
 tools=SimpleNamespace(sources=source_map,terms={},edges={},db=ndb,validate_scope=validate)
 glossary=SimpleNamespace(dbs={'lookup':lookup},connections=SimpleNamespace(_definitions=lambda *a:[]))
 matchmodule=importlib.import_module(base.__package__+'.navigation_match');matcher=matchmodule.ReverseMatcher(db,tools,glossary)
 matcher=module.bind_structure(matcher,store,read(A/'origin-projection.json'))
 class NoModel:
  def call(self,*a):raise AssertionError('read-only metadata audit cannot call an external model')
  def record_local(self,v):return {'kind':'local-metadata-audit','value':v}
 pipeline=mods['pipeline'].Pipeline(root,store,NoModel());conv=module.Conversation(pipeline,module.MultiAgent(pipeline,glossary,None,matcher),list(documents))
 catalogue=conv.run('외부 문서중에서 ESG채권 관련한 문서들 뭐가 있는지 알려줘');cat=catalogue['retrieval']['term_agent']['catalogue'];assert cat['total']==1 and cat['documents'][0]['id']=='65731d03bd65c441'
 tree=conv.run('해당 문서의 목차 알려줘');outline=tree['retrieval']['term_agent']['navigation_output']['data'];assert any(x['surface']=='제1조' for x in outline['items'])
 missing=conv.run('ESG채권 조문에서 1조 3항 알려줘');assert not missing['retrieval']['term_agent']['read_source_ids'] and '찾지 못했습니다' in missing['answer']['text']
 exact=conv.run('제5조 제3항 알려줘');readout=exact['retrieval']['term_agent']['navigation_output']['data'];assert readout['coordinate_key']=='body:제5조제3항'
 # No private text is persisted in the report; this example is a public kofia rule.
 new(A/'public-navigation-example-adapter-fix.json',{'catalogue':cat,'outline':outline,'missing_coordinate':missing['answer'],'existing_coordinate':{'coordinate_key':readout['coordinate_key'],'source_id':readout['source_id'],'unit_id':readout['unit_id'],'block_ids':[b['block_id'] for b in readout['blocks']],'segment_sha256':readout['segment_sha256']},'external_model_calls':0})
 counts=Counter(x['category'] for x in matcher.document_catalogue.values());providers=Counter(x.get('provider') for x in matcher.document_catalogue.values())
 command=['.venv/bin/python','-B','-m','pytest','-q','-p','no:cacheprovider',str(T.relative_to(R))]
 tests=subprocess.run(command,text=True,capture_output=True,env={**os.environ,'PYTHONPATH':'02_BACKEND','ADR449_TEST_FROZEN':'1'});new(A/'tests-adapter-fix.json',{'command':command,'returncode':tests.returncode,'output':tests.stdout+tests.stderr})
 changed=[p for p,h in lock.items() if sha(R/p)!=h]
 result={'kind':'ordinary contract and read-only storage connection audit, not a retrieval/answer effect comparison','model_calls':0,'external_transmission':False,'active_release':active['release_id'],'active_generation':active['generation'],'source_generation_id':manifest['generation_id'],'source_store_unchanged':sha(path/'store.sqlite')==before,'document_count':len(documents),'classification_counts':dict(counts),'provider_counts':dict(providers),'public_example':{'title_search_results':cat['total'],'document_name':cat['documents'][0]['name'],'origin_folder':cat['documents'][0]['folder'],'outline_count':outline['total'],'article1_paragraph3':'absent in stored tree; no fallback','article5_paragraph3_block_count':len(readout['blocks'])},'contract_tests_passed':tests.returncode==0,'input_drift':changed,'passed':tests.returncode==0 and not changed,'limitations':['No live LLM selection/answer comparison or GENOS execution','Original six-case comparison was not executed; preserved pre-amendment plan','Server-owned navigation context lives in per-conversation adapter; web/API/UI integration and persistence across process restarts not deployed','Unmatched path provenance remains unknown; no document-title classification','Derived outline is stored parser structure, not a guarantee of source parsing accuracy']}
 new(A/'verification-adapter-fix.json',result);print(json.dumps(result,ensure_ascii=False));db.close();ndb.close();lookup.close()
if __name__=='__main__':main()
