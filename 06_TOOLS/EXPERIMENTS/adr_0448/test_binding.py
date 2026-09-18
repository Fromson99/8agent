import json,sys,importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from binding_runtime import load,R
spec=importlib.util.spec_from_file_location('fixtures447',R/'06_TOOLS/EXPERIMENTS/adr_0447/fixtures.py');fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
DATA=R/'04_EXPERIMENTS/ADR/ADR-0447-template-bound-tool-handles/artifacts/dataset/synthetic-sources.json'
@pytest.fixture
def factory():
 resources=[];module,mods,root=load(False)
 def make(scope='body',duplicate=False,missing_parent=False):
  store,m,g=fixtures.build(DATA);resources.append(store)
  for row in list(store.db.execute('SELECT * FROM source_unit')):
   raw=json.loads(row['json'])
   if raw['family']=='circled':
    for k in ['legal_coordinate','coordinate_scope','coordinate_key','coordinate_path']:raw.pop(k,None)
   if row['document_id']=='mock-legal-disclosure' and raw['id']==1:
    raw['coordinate_scope']=scope;raw['coordinate_key']=scope+':stored-article-1'
    if missing_parent:raw.pop('coordinate_scope');raw.pop('coordinate_key')
   store.db.execute('UPDATE source_unit SET json=? WHERE document_id=? AND unit_id=?',(json.dumps(raw,ensure_ascii=False),row['document_id'],row['unit_id']))
  if duplicate:
   row=store.db.execute("SELECT * FROM source_unit WHERE document_id='mock-legal-disclosure' AND unit_id='3'").fetchone();raw=json.loads(row['json']);raw['id']=90
   store.db.execute('INSERT INTO source_unit VALUES (?,?,?,?)',(row['document_id'],'90',row['parent_id'],json.dumps(raw)))
  return module,store,m,g,mods,root
 yield make
 for store in resources:store.db.close()
def session(module,store,m,g):
 m=module.bind_structure(m,store)
 return module.InheritedSession(m,m.tools,g,'모의 공시 규정 제6조의2 제2항',list(m.documents),{'max_calls':16,'context_chars':60000,'active_chars':18000})
@pytest.mark.parametrize('scope',['body','addendum','annex','repeated'])
def test_stored_parent_scope_preserved(factory,scope):
 mod,store,m,g,_,_=factory(scope=scope);s=session(mod,store,m,g);r=s.find_article('제6조의2제2항',branch='any');assert len(r['items'])==1
 x=r['items'][0]['structure_match'];assert x['coordinate_scope']==scope;assert x['coordinate_binding']['ancestor_unit_id']=='1';assert x['coordinate_binding']['mode']=='stored_ancestry';assert x['coordinate']['chain']==[{'unit':'항','n':2,'sub':None}]
 if scope=='body':assert x['coordinate_key']=='body:제6조의2제2항'
 else:assert scope+':stored-article-1' in x['coordinate_key'];assert not s.find_article('제6조의2제2항',branch='body')['items']
def test_raw_and_existing_coordinates_preserved(factory):
 mod,store,m,g,_,_=factory();rows=[tuple(r) for r in store.db.execute('SELECT * FROM source_unit')];bound=mod.bind_structure(m,store)
 assert rows==[tuple(r) for r in store.db.execute('SELECT * FROM source_unit')]
 for d,u,p,j in rows:
  raw=json.loads(j);assert bound.units[(d,u)]['raw_structure']==raw
  if raw.get('coordinate_key'):
   for k in ('legal_coordinate','coordinate_scope','coordinate_key'):assert bound.units[(d,u)].get(k)==raw.get(k)
def test_missing_parent_scope_stays_unknown(factory):
 mod,store,m,g,_,_=factory(missing_parent=True);s=session(mod,store,m,g);r=s.find_article('제6조의2제2항');assert not r['items'];assert r['unresolved'][0]['coordinate_binding']['reason']=='NO_COMPATIBLE_STORED_ANCESTOR'
def test_duplicate_body_coordinate_not_silently_merged(factory):
 mod,store,m,g,_,_=factory(duplicate=True);s=session(mod,store,m,g);r=s.find_article('제6조의2제2항');assert not r['items'];assert len(r['unresolved'])==2;assert all(x['coordinate_binding']['reason']=='DUPLICATE_DERIVED_COORDINATE' for x in r['unresolved'])
def test_partial_stored_scope_is_not_overwritten(factory):
 mod,store,m,g,_,_=factory();r=store.db.execute("SELECT json FROM source_unit WHERE document_id='mock-legal-disclosure' AND unit_id='3'").fetchone();raw=json.loads(r[0]);raw['coordinate_scope']='annex';store.db.execute("UPDATE source_unit SET json=? WHERE document_id='mock-legal-disclosure' AND unit_id='3'",(json.dumps(raw),));s=session(mod,store,m,g);r=s.find_article('제6조의2제2항');assert not r['items'];assert r['unresolved'][0]['coordinate_binding']['reason']=='PARTIAL_STORED_SCOPE_KEY'
def test_original_body_and_addendum_still_distinct(factory):
 mod,store,m,g,_,_=factory();s=session(mod,store,m,g);assert {i['id'] for i in s.find_article('제6조의2',branch='body')['items']}=={'article:ko-article'};assert {i['id'] for i in s.find_article('제6조의2',branch='appendix')['items']}=={'article:ko-collision'}
def test_read_binding_and_original_quotes(factory):
 mod,store,m,g,_,_=factory();s=session(mod,store,m,g);item=s.find_article('제6조의2제2항')['items'][0];s.response_schema()
 with pytest.raises(ValueError,match='READ_HANDLE'):s.execute('READ',{'source_id':item['id']})
 r=s.execute('READ',item['read_action']['args']);assert r['source_id']=='article:ko-article';assert r['text']==m.tools.sources[r['source_id']]['text']
def test_nested_legacy_item_uses_actual_parent(factory):
 mod,store,m,g,_,_=factory();raw={'id':91,'parent':3,'family':'dot_number:1','ordinal':[1],'surface':'1.','title':''};store.db.execute("INSERT INTO source_unit VALUES ('mock-legal-disclosure','91','3',?)",(json.dumps(raw),));bound=mod.bind_structure(m,store);n=bound.units[('mock-legal-disclosure','91')];assert n['coordinate_key']=='body:제6조의2제2항제1호';assert n['coordinate_binding']['node_path']==['1','3','91']
def test_no_cross_document_ancestor(factory):
 mod,store,m,g,_,_=factory();store.db.execute("UPDATE source_unit SET parent_id='999' WHERE document_id='mock-legal-disclosure' AND unit_id='3'")
 with pytest.raises(ValueError):mod.bind_structure(m,store)
def test_rebound_methods_use_enriched_units(factory):
 mod,store,m,g,_,_=factory()
 class Matcher:
  def _unit_sources(self,d,u):return self.units[(d,u)].get('coordinate_key')
  def starts(self,q,s):return self.units
 old=Matcher();old.units={};new=mod.bind_structure(old,store);assert new._unit_sources('mock-legal-disclosure','3')=='body:제6조의2제2항';assert old.units=={}
def test_pipeline_consumes_inherited_result(factory):
 mod,store,m,g,mods,root=factory()
 class Provider:
  n=0
  def record_local(self,value):return {'kind':'unit-test','data':value}
  def call(self,role,system,data,schema):
   from jsonschema import Draft202012Validator
   self.n+=1;issues=[{'id':'I','text':'제2항 확인'}] if self.n==1 else []
   if self.n==1:a={'tool':'FIND_ARTICLE','args':{'locator':'제6조의2제2항','branch':'body'}}
   elif self.n==2:a=data['last_results'][0]['result']['items'][0]['read_action']
   elif self.n==3:
    r=data['active_segments'][0];a={'tool':'JUDGE','args':{'segment_id':r['id'],'status':'adopted','issue_id':'I','quote_ref':r['quote_refs'][0]['id'],'claim':'장애가 발생한 경우 서면 제출이 허용된다.'}}
   else:a={'tool':'STOP','args':{'status':'sufficient','unresolved':[]}}
   out={'issues':issues,'actions':[{**a,'reason':'contract verification'}]};Draft202012Validator(schema).validate(out);return out,{'kind':'scripted-unit-test'}
 p=mods['pipeline'].Pipeline(root,store,Provider());p.term_agent=mod.InheritedAgent(p,g,None,mod.bind_structure(m,store),{'max_calls':6});out=p.run('모의 공시 규정 제6조의2 제2항',list(m.documents),True);p.contracts.validate(out,'urn:8-agent:term-runtime-v1','Result');assert out['retrieval']['term_agent']['selected_ids']==['article:ko-article'];assert len(out['assembly']['context'])==1
