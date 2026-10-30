from types import SimpleNamespace as NS
from copy import deepcopy
import json,sqlite3,re
import pytest
from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.navigation_match import SurfaceIndex
from semantic_runtime.legal_agent import scope_completion as sc, source_goal_control as sg, investigation_supervisor as su
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from semantic_runtime.legal_agent.answer_progress import ProgressHandoff
from test_supervisor import fixture
from common import ROOT,ART,DES,read,put

def setup(number=47,title='전자자료의 보관',doc='renamed-doc'):
 inv,d,*_=fixture();inv.question=title+'기간은 어떻게 되는가?';inv.record={'current_request':inv.question};d['issues']=[{'id':'Q1','request_quote':inv.question}];inv.p['issues']=deepcopy(d['issues'])
 inv.policy.update(source_goal_control=True,scope_completion=True)
 m=NS(structures=SurfaceIndex(),units={(doc,'node'):{'coordinate_scope':'body','parent':None,'title':title}},stored_coordinates={(doc,'node'):find_coordinates(f'제{number}조')[0].coordinate},sources={'src':{'document_id':doc,'unit_id':'node'}},documents={doc:'바뀐 문서명'})
 m.structures.add(title,{'kind':'TITLE','document_id':doc,'unit_id':'node'});m._unit_sources=lambda did,uid:['src'];inv.s.matcher=m;inv.s.scope={doc};d['laws']=[{'document_id':doc,'name':m.documents[doc]}]
 a={'LOC':{'action':'SEARCH_STRUCTURE','identity':{'document_id':doc}},'READ':{'action':'READ_ARTICLES','identity':{'document_id':doc,'unit_id':'node','source_id':'src'}}}
 return inv,d,a

def discover(inv,d):
 st=su.state_for(inv,d);sc.discover(inv,d,st);return st

@pytest.mark.parametrize('number',[3,42,86,201])
@pytest.mark.parametrize('title',['전자자료의 보관','검사업무의 승인','보증인의 책임'])
def test_discovery_independent_of_article_doc_name_and_ids(number,title):
 inv,d,a=setup(number,title,'opaque-'+str(number));st=discover(inv,d)
 assert len(st['source_goals'])==1
 g=st['source_goals'][0];assert g['coordinate']==f'제{number}조' and g['origin_heading']['request_quote']==title
 assert g['status']=='REQUIRED' and st['calls']==0
 sc.discover(inv,d,st);assert len(st['source_goals'])==1 and len(inv.s.repo.events)==1
 assert sg.pending_before_selection(inv)

@pytest.mark.parametrize('fault',['unauthorized','user_doc_scope','user_unit_scope','excluded','locator','short','model_summary','other_branch','unresolved_binding'])
def test_non_source_or_outside_user_request_not_forced(fault):
 inv,d,a=setup();m=inv.s.matcher
 if fault=='unauthorized':inv.s.scope=set()
 if fault=='user_doc_scope':inv.s.direct_search_scope={'targets':[{'document_id':'other','unit_id':None}]}
 if fault=='user_unit_scope':inv.s.direct_search_scope={'targets':[{'document_id':'renamed-doc','unit_id':'another'}]}
 if fault=='excluded':inv.s.direct_search_scope={'targets':[{'document_id':'renamed-doc','unit_id':None}],'selections':[{'document_id':'renamed-doc','excluded_unit_ids':['node']}]}
 if fault=='locator':next(iter(m.structures.values.values()))[0]['kind']='LOCATOR'
 if fault=='short':inv,d,a=setup(title='정의')
 if fault=='model_summary':d['issues'][0]['request_quote']='모델이 만든 '+inv.question
 if fault=='other_branch':m.units[('renamed-doc','node')]['coordinate_scope']='addendum'
 if fault=='unresolved_binding':m.units[('renamed-doc','node')]['coordinate_binding']={'mode':'unresolved'}
 assert discover(inv,d)['source_goals']==[]

@pytest.mark.parametrize('fault',['duplicate_coordinate','missing_source'])
def test_unavailable_or_ambiguous_original_stays_blocked(fault):
 inv,d,a=setup();m=inv.s.matcher
 if fault=='duplicate_coordinate':m.units[('renamed-doc','copy')]=deepcopy(m.units[('renamed-doc','node')]);m.stored_coordinates[('renamed-doc','copy')]=m.stored_coordinates[('renamed-doc','node')]
 else:m._unit_sources=lambda *a:[]
 st=discover(inv,d);assert st['source_goals'][0]['status']=='BLOCKED'
 result={'disposition':'ANSWER','answer_coverage':'COVERED','claims':[],'limitation_items':[]};sg.limit_assessment(result,sg.unresolved(inv.p,d['issues']));assert result['answer_coverage']=='PARTIAL'

@pytest.mark.parametrize('refs',[['E1'],['preview'],[]])
def test_unrelated_original_or_reason_cannot_exclude(refs):
 inv,d,a=setup();st=discover(inv,d);g=st['source_goals'][0]
 value={'source_goal_exclusions':[{'goal_id':g['goal_id'],'reason':'다른 문서의 정의를 읽어서 충분함','basis_refs':refs}]}
 with pytest.raises(ProposalError):sg.record(value,inv,d,a,st)
 assert st['source_goals'][0]['status']=='REQUIRED'


def test_verified_original_still_allows_legal_exclusion(monkeypatch):
 inv,d,a=setup();st=discover(inv,d);g=st['source_goals'][0]
 def acquired(_inv,goals):
  for goal in goals:
   if goal['status'] in ('REQUIRED','BLOCKED'):goal['status']='ACQUIRED'
 monkeypatch.setattr(sg,'refresh',acquired)
 sg.record({'source_goal_exclusions':[{'goal_id':g['goal_id'],'reason':'원문 확인 결과 다른 적용 대상','basis_refs':['E1']}]},inv,d,a,st)
 assert st['source_goals'][0]['status']=='EXCLUDED'


def test_priority_and_resume_before_early_handoff(monkeypatch):
 inv,d,a=setup();sc.before_handoff(inv);st=su.state_for(inv,d);assert sg.pending_before_selection(inv)
 before=deepcopy(inv.p);inv.p=json.loads(json.dumps(before));sc.before_handoff(inv);assert inv.p==before
 inv.s.scope.add('changed')
 with pytest.raises(ContractError):sc.before_handoff(inv)


def test_discovery_overflow_remains_visible_to_final_assessment():
 inv,d,a=setup();m=inv.s.matcher
 for i in range(20):
  did='extra-'+str(i);m.documents[did]=did;inv.s.scope.add(did);m.units[(did,'node')]=deepcopy(m.units[('renamed-doc','node')]);m.stored_coordinates[(did,'node')]=find_coordinates(f'제{i+100}조')[0].coordinate;m.sources[did]={'document_id':did,'unit_id':'node'};m.structures.add('전자자료의 보관',{'kind':'TITLE','document_id':did,'unit_id':'node'})
 m._unit_sources=lambda did,uid:['src' if did=='renamed-doc' else did]
 st=discover(inv,d);assert len(st['source_goals'])==16 and len(st['scope_discovery']['overflow'])==5
 assert len(sg.unresolved(inv.p,d['issues']))==21


def test_saved007_false_finish_cannot_skip_actual_heading_sources():
 from semantic_runtime.structure_navigation import stored_coordinate
 P=ROOT/'04_EXPERIMENTS/ADR/ADR-1177-response-recovery-followup/artifacts/live/cm-007';D=ROOT/read(DES/'baseline.json')['manifest']['data_path'];case=read(DES/'cases.json')[0]
 inv,d,a=setup();inv.question=case['request']['json']['question'];inv.record={'current_request':inv.question};d['issues']=[{'id':'Q1','request_quote':inv.question}];inv.s.scope=set(case['request']['json']['document_ids']);inv.p['issues']=deepcopy(d['issues'])
 db=sqlite3.connect((D/'store.sqlite').as_uri()+'?mode=ro',uri=True);nav=sqlite3.connect((D/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True);m=inv.s.matcher;m.units={};m.stored_coordinates={};m.sources={};m.structures=SurfaceIndex();m.documents={}
 for did,uid,parent,raw in db.execute('select document_id,unit_id,parent_id,json from source_unit'):
  if did not in inv.s.scope:continue
  unit=json.loads(raw);m.units[(did,str(uid))]={**unit,'parent':str(parent) if parent is not None else None,'raw_structure':unit}
 for key in m.units:m.stored_coordinates[key]=stored_coordinate(m.units,*key)
 for (did,uid),unit in m.units.items():
  title=re.sub(r'^제\s*\d+(?:-\d+)?\s*[편장절관조항호](?:의\s*\d+)?\s*','',unit.get('title','')).strip(' ()')
  if title:m.structures.add(title,{'kind':'TITLE','document_id':did,'unit_id':uid})
 for sid,raw in nav.execute('select id,json from source'):
  src=json.loads(raw)
  if src['document_id'] in inv.s.scope:m.sources[sid]=src;m.documents[src['document_id']]=src.get('document_title',src['document_id'])
 m.documents={did:name for did,name in db.execute('select document_id,name from document') if did in inv.s.scope}
 m._unit_sources=lambda did,uid:[sid for sid,x in m.sources.items() if x['document_id']==did and str(x.get('unit_id'))==uid]
 st=discover(inv,d);gold=next(c for c in read(ART/'evaluation-only/cases.json') if c['id']=='cm-007');required={(x['doc_id'],str(x['node'])) for x in gold['targets'] if x.get('role')=='required'}
 found={(g['document_id'],g['origin_heading']['unit_id']) for g in st['source_goals']};assert required<=found
 a={'GLOBAL':{'action':'SEARCH_STRUCTURE','identity':{'document_id':None}}};d['laws']=[]
 raw=read(P/'raw/call-009/response.json');old=json.loads(raw['choices'][0]['message']['content']);assert old['choice']=='FINISH' and old['source_targets']==[]
 def expand(v):return {'next_action':'SEARCH_STRUCTURE','targets':[v['target']],'queries':v['queries'],'issue_refs':['Q1']}
 accepted=sg.resolve(inv,d,a,{}, {},{'next_action':'FINISH','reason':old.get('reason','')},expand,st);assert accepted['next_action']=='SEARCH_STRUCTURE'
 assert st['calls']==0 and all(g['status']=='REQUIRED' for g in st['source_goals'])
 result={'disposition':'ANSWER','answer_coverage':'COVERED','claims':[],'limitation_items':[]};sg.limit_assessment(result,sg.unresolved(inv.p,d['issues']));assert result['disposition']=='LIMITED_ANSWER'
 put(ART/('scope-replay-'+read(DES/'freeze.json').get('execution_id',read(DES/'freeze.json')['candidate_revision']['revision_id'])+'.json'),{'passed':True,'scope':'Actual stored title metadata, actual saved FINISH, resolver and final limiter; not a replay of every old HTTP/model stage','discovered':st['source_goals'],'replacement':accepted,'final_unread':result,'new_model_calls':0})
 db.close();nav.close()
