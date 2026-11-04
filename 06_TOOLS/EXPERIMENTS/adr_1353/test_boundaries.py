from copy import deepcopy
from pathlib import Path
import importlib.util,gzip,json
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import source_goal_control as sg, evidence_inventory as ei, need_continuity as nc
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work import authoring_semantics as sem
from semantic_runtime.ontology_work.wiki_projection import compile_selection
from test_wiki_workspace import env,ws,seed,projection_generator
ROOT=Path(__file__).resolve().parents[3]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
old=module('goal_history_1353','06_TOOLS/EXPERIMENTS/adr_1347/test_repair.py')
prior=module('reviews_1353','06_TOOLS/EXPERIMENTS/adr_1352/test_contracts.py')

def test_excluded_exact_goal_keeps_decision_but_records_existing_original(monkeypatch):
 inv,goal,full,verified=old.history_fixture(monkeypatch);goal.update(status='EXCLUDED',exclusion={'reason':'추가 탐색은 전체 원문에 포함되어 불필요','scope_quote':'기존 질문'})
 decision=deepcopy(goal['exclusion']);state=deepcopy(inv.p);sg.refresh(inv,[goal])
 assert goal['status']=='EXCLUDED' and goal['exclusion']==decision and goal['arrivals']==['B1']
 assert inv.p==state and full['evidence'][0] in verified and 'claims' not in goal
 first=deepcopy(goal);sg.refresh(inv,[goal]);assert goal==first

@pytest.mark.parametrize('ancestor',[False,True])
def test_excluded_origin_full_coverage_can_reach_unchanged_final_scope_check(monkeypatch,ancestor):
 inv,g,full,verified=old.history_fixture(monkeypatch,ancestor=ancestor);g.update(status='EXCLUDED',exclusion={'reason':'이미 전체 범위에서 읽은 자료'})
 sg.refresh(inv,[g]);assert g['status']=='EXCLUDED' and g['arrivals']==['B1']
 target={'document_id':'d','acquired':bool(g['arrivals'] and g['expected']),'expected':g['expected']}
 options=[dict(span,document_id='d') for span in full['evidence'][0]['spans']]
 assert nc.available(target,options)
 assert not nc.available(target,options[:1])

@pytest.mark.parametrize('fault',['missing','partial','wrong_coordinate','other_branch','bad_key','bad_bytes','foreign_document'])
def test_excluded_does_not_fabricate_missing_or_invalid_arrivals(monkeypatch,fault):
 inv,g,full,verified=old.history_fixture(monkeypatch);g.update(status='EXCLUDED',exclusion={'reason':'모델 제외'})
 if fault=='missing':inv.p['material_history']={}
 if fault=='partial':full['evidence'][0]['spans']=full['evidence'][0]['spans'][:1]
 if fault=='wrong_coordinate':g['coordinate']='제9조'
 if fault=='other_branch':inv.p['read_plans']['P']['completed']={'T':'other'}
 if fault=='bad_key':inv.p['material_history']={'bad':full}
 if fault=='bad_bytes':full['evidence'][0]['spans'][1]['text']='변조'
 if fault=='foreign_document':full['document_id']='other'
 if fault in ('bad_key','bad_bytes','foreign_document'):
  with pytest.raises((ContractError,AssertionError)):sg.refresh(inv,[g])
 else:
  sg.refresh(inv,[g]);assert not g.get('arrivals')
 assert g['status']=='EXCLUDED' and g['exclusion']=={'reason':'모델 제외'}

def to_embedded(value):
 v=deepcopy(value);a=v['accumulation'];links=a.pop('norm_links');by={x['node_id']:x for x in links}
 assert len(by)==len(links)
 for node in a['graph']['nodes']:
  if node['kind']=='EFFECT':node['source_norm']={k:x for k,x in by.pop(node['id']).items() if k!='node_id'}
 assert not by,'fixture must not discard invalid links'
 return v

@pytest.mark.parametrize('fault',[None,'first','twice'])
def test_actual_compiler_receives_effect_selection_repair_and_idempotence(env,ws,fault):
 item=seed(env,ws);calls=[];base=projection_generator(env,item,calls);proposals=[]
 def generate(prompt,ctx,schema):
  v,receipt=base(prompt,ctx,schema)
  if 'statements' in ctx:
   v=to_embedded(v);proposals.append(deepcopy(ctx))
   if fault=='twice' or (fault=='first' and len(proposals)==1):v['accumulation']['graph']['nodes'][0]['source_norm']['source']='foreign'
   if fault is None or (fault=='first' and len(proposals)>1):Draft202012Validator(schema).validate(v)
  return v,receipt
 ws.generate=generate;args=dict(statement_ids=[item.sid],purpose='원문 규칙 재사용',profile_id=env.profile_id,profile_work_hash=env.profile_work_hash,originals=[env.source])
 if fault=='twice':
  with pytest.raises(ContractError):compile_selection(env.w,ws,**args)
  before=len(calls)
  with pytest.raises(ContractError,match='INVALID'):compile_selection(env.w,ws,**args)
  assert len(calls)==before and len(proposals)==2
 else:
  d=compile_selection(env.w,ws,**args);before=len(calls)
  assert compile_selection(env.w,ws,**args)['reused'] and len(calls)==before
  assert env.w.preview(d['bundle_id'])['paths'][0]['body']==ws.item(item.sid)['content']['text']
  assert env.repo.head(d['bundle_id'])['publication_id'] is None
  assert len(proposals)==(2 if fault else 1)
 if fault:
  assert proposals[1]['repair']['previous']['response']['accumulation']['graph']['nodes'][0]['source_norm']['source']=='foreign'


def saved():
 p=ROOT/'04_EXPERIMENTS/ADR/ADR-1352-ontology-content-review-contract/artifacts/build-live/canonical'
 with gzip.open(p/'004.json.gz','rt') as f:inp=json.load(f)
 with gzip.open(p/'004-output.json.gz','rt') as f:raw=json.load(f)
 ctx=inp['context'];old_schema=inp['schema']['properties']['accumulation']
 canonical=deepcopy(old_schema);canonical['properties'].pop('norm_links');canonical['required'].remove('norm_links');canonical['properties'].pop('condition_links');canonical['required'].remove('condition_links')
 # source slots were already removed from this historical wire. The request
 # helper is idempotent for those fields and tests the current offered norms.
 canonical['properties']['comparisons']['items']['properties'].pop('semantic_check');canonical['properties']['comparisons']['items']['required'].remove('semantic_check')
 return ctx,old_schema,sem.request_schema(canonical,ctx['source_analysis']),raw

def test_actual_old_wrong_kind_response_stays_rejected_no_automatic_drop():
 ctx,old_schema,new_schema,raw=saved();before=deepcopy(raw)
 with pytest.raises(ContractError,match='each EFFECT'):sem.restore(raw['accumulation'],old_schema,ctx['source_analysis'],ctx['originals'])
 assert not Draft202012Validator(new_schema).is_valid(raw['accumulation'])
 assert raw==before

@pytest.mark.parametrize('fault',['non_effect','missing_effect','foreign_source','bad_index','bad_quote','legacy_extra'])
def test_node_local_norm_is_exact_and_cannot_attach_to_calculation(fault):
 ctx,old_schema,schema,raw=saved();a=deepcopy(raw['accumulation'])
 old_links=a.pop('norm_links');effects={n['id']:n for n in a['graph']['nodes'] if n['kind']=='EFFECT'}
 for link in old_links:
  if link['node_id'] in effects:effects[link['node_id']]['source_norm']={k:v for k,v in link.items() if k!='node_id'}
 effect=next(iter(effects.values()));other=next(n for n in a['graph']['nodes'] if n['kind']!='EFFECT')
 if fault=='non_effect':other['source_norm']=deepcopy(effect['source_norm'])
 if fault=='missing_effect':effect.pop('source_norm')
 if fault=='foreign_source':effect['source_norm']['source']='missing'
 if fault=='bad_index':effect['source_norm']['norm_index']=999999
 if fault=='bad_quote':effect['basis'][0]['quote']='원문에 없는 인용'
 if fault=='legacy_extra':a['norm_links']=old_links
 with pytest.raises(Exception):sem.restore(a,schema,ctx['source_analysis'],ctx['originals'])

# Exact reviewed API consumer from1352 remains wired to the new projections.
from conftest import term_glossary
@pytest.mark.parametrize('fault',[None,'scope_first','scope_twice'])
def test_api_review_normal_repair_and_stop(tmp_path,term_glossary,monkeypatch,fault):
 prior.test_actual_api_new_review_and_bounded_repair(tmp_path,term_glossary,monkeypatch,fault)

def test_excluded_original_reaches_actual_context_derived_work_and_final_validator(monkeypatch):
 from semantic_runtime.contracts import digest
 from semantic_runtime.legal_agent import answer_progress,investigation_supervisor as sup,source_work_review as work,read_judgment_final as final
 from types import SimpleNamespace as NS
 inv,g,full,verified=old.history_fixture(monkeypatch);g.update(status='EXCLUDED',exclusion={'reason':'전체 읽기와 중복된 탐색'},issue_id='Q1',identity='actual-coordinate',reason='원문 확보')
 sg.refresh(inv,[g]);assert g['status']=='EXCLUDED'
 question='해당 제출 규칙을 알려주세요';issues=[{'id':'Q1'}];inv.p['binding']={'test':'scope-bound'}
 key=digest([answer_progress.REVISION,inv.p['binding'],question,issues]);state={'binding':inv.p['binding'],'source_goals':[g],'material_needs':{},'goals':[]};state['state_hash']=sup.seal(state);inv.p['investigation_supervisor']={key:state}
 spans=full['evidence'][0]['spans'];opts=[dict(s,id='S'+str(i),document_id='d',text_hash=digest(s['text'])) for i,s in enumerate(spans)]
 source={s['block_id']:s['text'] for s in spans};session=NS(store=NS(source=lambda did,bid:{'text':source[bid]}))
 ctx={'needs':[],'judgments':[{'id':'J','available_evidence_refs':['S0','S1']}],'conflicts':[],'change_review':False}
 nc.extend_context(ctx,inv.p,question,issues,opts,{'d'},session=session)
 t=ctx['need_continuity']['targets'][0];assert t['acquisition_status']=='EXCLUDED' and t['available_complete'] and t['available_evidence_refs']==['S0','S1']
 assert len(work.eligible(ctx,opts))==1
 def group(ref,dis,claims):return {'basis_refs':[ref],'disposition':dis,'claim_refs':claims,'issue_refs':['Q1'],'gap_indices':[],'scope_quote':'','reason':'확보한 본문과 표제를 구분'}
 v={'claims':[{'claim_id':'C','issue_refs':['Q1'],'evidence_refs':['S1']}],'gaps':[],'issue_assessments':[{'issue_id':'Q1','status':'COVERED'}],
 'read_judgment_review':{'judgments':[{'id':'J','disposition':'USE','basis_refs':['S1'],'claim_refs':['C'],'reason':'본문 원문 채택'}],'needs':[],'conflicts':[],
 'scope_reviews':[{'target_id':t['id'],'groups':[group('S0','EXCLUDE',[]),group('S1','USE',['C'])]}]}}
 v['read_judgment_review']['needs']=work.derived(v,ctx,opts);final.validate_review(v,ctx,opts)
 assert v['read_judgment_review']['needs'][0]['status']=='RESOLVED' and g['status']=='EXCLUDED'
 assert v['claims']==[{'claim_id':'C','issue_refs':['Q1'],'evidence_refs':['S1']}]

def test_empty_source_analysis_cannot_generate_an_effect():
 ctx,old_schema,schema,raw=saved();analysis={key:{'norms':[],'unresolved':[]} for key in ctx['source_analysis']}
 # Reconstructing a request with no norms must remove an impossible EFFECT
 # branch, not offer invented indices or call unsupported provider grammar.
 canonical=deepcopy(old_schema)
 for key in ('norm_links','condition_links'):
  canonical['properties'].pop(key);canonical['required'].remove(key)
 comparisons=canonical['properties']['comparisons']['items'];comparisons['properties'].pop('semantic_check');comparisons['required'].remove('semantic_check')
 schema=sem.request_schema(canonical,analysis)
 Draft202012Validator.check_schema(schema)
 assert all(n['properties']['kind']['const']!='EFFECT' for n in schema['properties']['graph']['properties']['nodes']['items']['anyOf'])

def test_shared_contract_also_reaches_direct_domain_accumulation(env,ws):
 item=seed(env,ws);observed=env.w.normalize(item.raw['bundle_id'],profile_id=env.profile_id,profile_work_hash=env.profile_work_hash)
 calls=[];base=projection_generator(env,item,calls)
 def generate(prompt,ctx,schema):
  prepared=deepcopy(ctx)
  if ctx.get('operation')!='SOURCE_ANALYSIS':prepared['statements']=[ws.item(item.sid)]
  value,receipt=base(prompt,prepared,schema)
  if 'accumulation' in value:value=to_embedded(value)['accumulation']
  Draft202012Validator(schema).validate(value)
  return value,receipt
 env.w.generate=generate
 d=env.w.accumulate(bundle_id='cb-kb-direct-effect-selection',expected_revision=0,profile_id=env.profile_id,
  profile_work_hash=env.profile_work_hash,observation_ids=[observed['bundle_id']],originals=[env.source])
 assert len(calls)==2 and env.w.preview(d['bundle_id'])['paths'][0]['body']==ws.item(item.sid)['content']['text']
 assert env.repo.head(d['bundle_id'])['publication_id'] is None
 assert 'source-first-assembly-v2' in json.dumps(env.w.load(d['bundle_id']))
