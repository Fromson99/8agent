from copy import deepcopy
from types import SimpleNamespace as S
import json,gzip
from pathlib import Path
import pytest
from jsonschema import validate, ValidationError
from semantic_runtime.legal_agent import investigation_focus as focus, read_candidate_pages as pages, answer_progress as ap
from semantic_runtime.legal_agent.errors import ContractError
R=Path(__file__).resolve().parents[3]

def test_retention_resume_scope_and_research():
 inv=S(p={'binding':'b','selected':{}},s=S(scope=['D1','D2']))
 original={'laws':[{'id':'L1','document_id':'D1','name':'law','article_matches':[{'read_action':'T1','article':'제13조','deferred_preview':{'query':'q','source_id':'s1'}}]}], 'query_fingerprint':'q','direct_search_scope':{'document_ids':['D1']}}
 actions={'T1':{'action':'READ_ARTICLES','identity':{'document_id':'D1','source_id':'s1'},'label':'제13조 전체 읽기'}}
 focus.retain_search_candidates(inv,original,actions,lambda *x:'T2',True)
 inv.p=json.loads(json.dumps(inv.p))
 d={**deepcopy(original),'laws':[]};focus.retain_search_candidates(inv,d,{},lambda *x:'T2',False)
 assert d['laws'][0]['article_matches'][0]['read_action']=='T2'
 assert d['laws'][0]['article_matches'][0]['origin']=='PREVIOUS_SEARCH_UNREAD'
 assert original['laws'][0]['article_matches'][0]['read_action']=='T1'
 d['laws']=[];focus.retain_search_candidates(inv,d,{},lambda *x:None,False);assert not d['laws']
 inv.p['selected']={'g':{'source_id':'s1'}};d['laws']=[];focus.retain_search_candidates(inv,d,{},lambda *x:'T2',False);assert not d['laws']
 inv.p['selected']={};d['query_fingerprint']='new';focus.retain_search_candidates(inv,d,{},lambda *x:'T2',False);assert not d['laws']


def test_preview_exact_offsets_and_all_hits():
 hits=[{'unit_id':'u1','text':'자문 의무'}, {'unit_id':'u2','text':'가'*220+'의무인수 수량 규정'}, {'unit_id':'u3','text':'적용하지 않을 수 있다'}]
 out=focus.matched_excerpts(hits,['의무인수']);assert len(out)==3
 for row,hit in zip(out,hits):assert row['text']==hit['text'][row['start_cp']:row['end_cp']]
 assert '의무인수' in out[1]['text']
 assert focus.matched_excerpts([],[])==[]


def fixture():
 rows=[{'target':f'R{i}'} for i in range(23)]
 opts=[{'choice':'FOLLOW_CONNECTION','target':f'T{i}','selected_scope':{'id':f'S{i}'}} for i in range(51)]
 opts += [{'choice':'RESEARCH','target':'SEARCH'}]
 def branch(k,ts):return {'type':'object','properties':{'choice':{'const':k},'target':{'enum':ts}},'required':['choice','target'],'additionalProperties':False}
 schema={'anyOf':[branch('FOLLOW_CONNECTION',[f'T{i}' for i in range(51)]),branch('RESEARCH',['SEARCH']),{'type':'object','properties':{'choice':{'const':'READ'},'selections':{'type':'array','minItems':1,'items':{'type':'object','properties':{'target':{'enum':[r['target'] for r in rows]}},'required':['target']}}},'required':['choice','selections']}]}
 data={'read_candidates':rows,'tool_options':opts,'connection_scope_choices':[{'id':f'S{i}'} for i in range(51)]}
 return data,schema


def test_all_targets_reachable_and_hidden_rejected():
 data,schema=fixture();before=deepcopy((data,schema));seen=set();reads=set()
 for n in range(3):
  v,s=pages.page_view(data,schema,n,20)
  assert any(r['choice']=='RESEARCH' for r in v['tool_options'])
  assert len(v['connection_scope_choices'])<=20
  for row in v['tool_options']:validate({'choice':row['choice'],'target':row['target']},s);seen.add(row['target'])
  reads.update(r['target'] for r in v['read_candidates'])
  if n==0:
   with pytest.raises(ValidationError):validate({'choice':'FOLLOW_CONNECTION','target':'T50'},s)
 assert seen=={r['target'] for r in data['tool_options']}
 assert reads=={r['target'] for r in data['read_candidates']}
 assert (data,schema)==before
 with pytest.raises(ContractError):pages.page_view(data,schema,3,20)
 with pytest.raises(ContractError):pages.page_view(data,schema,0,0)


def test_observation_keeps_independent_read_and_durable_streak():
 events=[];inv=S(p={'binding':'b'},policy={'answer_progress_observe':True},question='question',save=lambda:None,s=S(repo=S(event=lambda *a:events.append(a))))
 d={'issues':[{'id':'Q1'}],'sources':[{'id':'E1','text':'source'}],'basis':[{'id':'E1','branch_id':'B'}]}
 v={'choice':'READ','selections':[{'target':'T1','issue_id':'Q1','missing_need':'new independent need'}], 'answer_progress':{'goals':[{'issue_id':'Q1','status':'NO_PROGRESS','answer_so_far':'known','basis_refs':['E1'],'material_need':'missing','next_answer_change':'','previous_effect':'INITIAL'}]}}
 assert ap.enabled(inv)
 for i in range(4):
  v['answer_progress']['goals'][0]['previous_effect']='INITIAL' if i==0 else 'NO_CHANGE'
  ap.validate_review(v,{'E1':d['sources'][0]},d['issues'],data=d,inv=inv)
  assert ap.resolve_action(inv,d,v)==(v,None)
  assert ap.bind_action(v,d,inv)==v
  assert not ap.record(inv,d,v,str(i))
  inv.p=json.loads(json.dumps(inv.p))
 assert ap.state_for(inv,d)['unchanged_steps_by_issue']['Q1']==3
 assert ap.context(inv,d)['handoff_after_unchanged_steps'] is None
 bad=deepcopy(v);bad['answer_progress']['goals'][0]['basis_refs']=['E404']
 with pytest.raises(ContractError):ap.validate_review(bad,{'E1':{}},d['issues'],data=d,inv=inv)


def test_observe_schema_keeps_action_reason_and_accepts_optional_progress():
 inv=S(p={'binding':'b'},policy={'answer_progress_observe':True},question='q')
 _,schema=fixture();schema={'anyOf':[schema['anyOf'][0]]};schema['anyOf'][0]['properties']['missing_need']={'type':'string'};schema['anyOf'][0]['required'].append('missing_need')
 d={'issues':[{'id':'Q1'}]};out=ap.attach(schema,inv,d,{'E1':{}},'k')
 assert 'missing_need' in out['anyOf'][0]['required']
 assert 'answer_progress' in out['anyOf'][0]['properties']
 assert 'answer_progress' not in out['anyOf'][0]['required']


def test_actual_profile_validates():
 from semantic_runtime.legal_agent import law_candidates as lc
 root=Path(focus.__file__).parents[3]
 profile=json.loads((root/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text())
 got=lc.validate_policy(profile['candidate_navigation'])
 assert got['answer_progress_observe'] and got['read_judgment'] and got['independent_read_recovery']
 assert not got['answer_progress_control']
 with pytest.raises(ContractError):lc.validate_policy({**profile['candidate_navigation'],'answer_progress_observe':'yes'})


def test_empty_read_menu_rejects_fabricated_target():
 data,schema=fixture();data['read_candidates']=[]
 view,wire=pages.page_view(data,schema,0,20)
 assert not any(b['properties']['choice']['const']=='READ' for b in wire['anyOf'])
 with pytest.raises(ValidationError):validate({'choice':'READ','selections':[{'target':'R1'}]},wire)
 validate({'choice':'RESEARCH','target':'SEARCH'},wire)


def test_missing_observation_is_not_a_source_read_blocker():
 events=[];inv=S(p={'binding':'b'},policy={'answer_progress_observe':True},question='q',save=lambda:None,s=S(repo=S(event=lambda *a:events.append(a))))
 value={'choice':'READ','selections':[{'target':'T1','issue_id':'Q1','missing_need':'new independent need'}]}
 assert not ap.record(inv,{'issues':[{'id':'Q1'}]},value,'missing')
 assert events[-1][0]=='ANSWER_PROGRESS_NOT_SUBMITTED'
 assert events[-1][1]['semantic_progress']=='UNASSESSED'
 assert 'answer_progress_reviews' not in inv.p
