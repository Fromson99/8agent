from copy import deepcopy
import pytest
from test_domain_profile_workflow import env, add_observation, proposal
from semantic_runtime.ontology_work import observations as obs, recorded_fields as roles, authoring_semantics as sem, accumulation as acc
from semantic_runtime.ontology_work.profile import validate
from semantic_runtime.legal_agent.errors import ContractError

def wire_normalization(value, raw):
    value=deepcopy(value)
    if not isinstance(value,dict) or 'observations' not in value:return value
    if any('recorded_reason' in o for o in value['observations']):return value
    for o in value['observations']:
        for k in ('reason','purpose'):
            field=o.pop(k);assert field['state']!='PRESENT'
            o['recorded_'+k]=None
    if isinstance(value.get('coverage'),list) and value['coverage']:
        value['coverage']={r['pointer']:{k:v for k,v in r.items() if k!='pointer'} for r in value['coverage']}
    segments={r['pointer']:r['text'] for r in raw['index']}
    def walk(x):
        if isinstance(x,dict):
            if set(x)=={'payload_hash','pointer','start','end','quote'}:
                obs.check_locator(x,raw)
                starts=[];i=-1
                while True:
                    i=segments[x['pointer']].find(x['quote'],i+1)
                    if i<0:break
                    starts.append(i)
                return {'pointer':x['pointer'],'quote':x['quote'],'occurrence':starts.index(x['start'])}
            return {k:walk(v) for k,v in x.items()}
        if isinstance(x,list):return [walk(v) for v in x]
        return x
    return walk(value)

def source_plan(e):
    return {'S1':{'norms':[{'quote':e.source['text'],'modality':'OBLIGATION',
       'regulated_actions':[{'text':'물건을 제출한다','quote':'물건을 제출한다'}],'applicability_conditions':[],
       'performance_requirements':[]}],'unresolved':[]}}

def fixtures(e):
    o=add_observation(e);p=e.w.selected_profile(e.profile_id,e.profile_work_hash)
    n=e.w.load(o['bundle_id'])['normalized'];analysis=source_plan(e)
    canonical=proposal(e,o);wire=deepcopy(canonical)
    for node in wire['graph']['nodes']:
        for k in ('action','modality'):node['slots'].pop(k,None)
    wire.update(norm_links=[{'node_id':'N1','source':'S1','norm_index':0}],condition_links=[])
    for row in wire['comparisons']:row['semantic_check']={k:'MATCH' for k in sem.AXES}
    schema=sem.request_schema(acc.accumulation_schema(p,[n],originals=[e.source]),analysis)
    return o,p,analysis,wire,schema

@pytest.mark.parametrize('field',['reason','purpose'])
def test_absent_remains_absent(env,field):
    o=add_observation(env,payload={'text':'나는 가상 규칙이 맞다고 판단했다.','id':'S1'})
    saved=env.w.load(o['bundle_id'])['normalized']
    assert saved['proposal']['observations'][0][field]=={'state':'NOT_RECORDED','value':None,'locators':[]}
    assert saved['model_receipt']['normalization_assembly']['recorded_roles']==[]

@pytest.mark.parametrize('field,label',[('reason','판단한 까닭'),('purpose','달성하려는 일'),('reason','grounds'),('purpose','aim')])
def test_explicit_labeled_record(env,field,label):
    raw=env.w.import_payload({label:'명시된 가상 설명','text':'원래 판단'},run_id='labeled',event_id=label)
    r=env.w.load(raw['bundle_id'])['raw'];p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
    from test_domain_profile_workflow import normalized_output
    wire=wire_normalization(normalized_output({'raw':r}),r);quote='명시된 가상 설명'
    loc={'pointer':'/'+label,'quote':quote,'occurrence':0}
    wire['observations'][0]['recorded_'+field]={'value':quote,'locators':[loc],'role_evidence':{'mode':'LABELED_FIELD','label':label,'locator':loc}}
    canonical,receipt=roles.restore(wire,r,roles.request_schema(obs.normalization_schema(r,p),r),obs.restore_normalization)
    assert canonical['observations'][0][field]['value']==quote
    assert receipt['recorded_roles'][0]['field']==field

@pytest.mark.parametrize('field,cue,value',[('reason','때문에','자료가 없기 때문에 보류했다'),('purpose','위해','기록을 남기기 위해 보류했다')])
def test_explicit_text_role(env,field,cue,value):
    r=obs.envelope(value+'. 판단: 보류.',namespace='n',run_id='r',event_id='e',sequence=0,source_snapshot='s',producer_binding='b',acl_ref='a',document_ids=[])
    p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
    from test_domain_profile_workflow import normalized_output
    wire=wire_normalization(normalized_output({'raw':r}),r)
    loc=lambda q:{'pointer':'','quote':q,'occurrence':0}
    wire['observations'][0]['recorded_'+field]={'value':value,'locators':[loc(value)],'role_evidence':{'mode':'EXPLICIT_TEXT','label':None,'locator':loc(cue)}}
    canonical,_=roles.restore(wire,r,roles.request_schema(obs.normalization_schema(r,p),r),obs.restore_normalization)
    assert canonical['observations'][0][field]['state']=='PRESENT'

@pytest.mark.parametrize('fault',['copied_statement','fake_label','fake_cue','wrong_occurrence','missing_wire_fields'])
def test_invented_role_rejected(env,fault):
    r=obs.envelope({'text':'판단을 보류했다. 이유 기록은 없다.'},namespace='n',run_id='r',event_id='e',sequence=0,source_snapshot='s',producer_binding='b',acl_ref='a',document_ids=[])
    p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
    from test_domain_profile_workflow import normalized_output
    wire=wire_normalization(normalized_output({'raw':r}),r);q=r['index'][0]['text']
    loc=lambda v:{'pointer':'/text','quote':v,'occurrence':0}
    v=q if fault=='copied_statement' else '판단을 보류했다.'
    proof=loc(v if fault=='fake_label' else '판단')
    if fault=='fake_cue':proof=loc('때문에')
    if fault=='wrong_occurrence':proof['occurrence']=8
    wire['observations'][0]['recorded_reason']={'value':v,'locators':[loc(v)],'role_evidence':{'mode':'LABELED_FIELD' if fault=='fake_label' else 'EXPLICIT_TEXT','label':'없는 필드' if fault=='fake_label' else None,'locator':proof}}
    if fault=='missing_wire_fields':wire['observations'][0].pop('recorded_purpose')
    with pytest.raises(ContractError):roles.restore(wire,r,roles.request_schema(obs.normalization_schema(r,p),r),obs.restore_normalization)

def test_source_exactness_and_schema(env):
    p=env.w.selected_profile(env.profile_id,env.profile_work_hash);a=source_plan(env);schema=sem.source_schema(p,[env.source])
    sem.validate_source(a,schema,[env.source]);validate(a,schema)
    a['S1']['norms'][0]['regulated_actions']=[{'text':'없는 행위','quote':'없는 행위'}]
    with pytest.raises(ContractError,match='quote'):sem.validate_source(a,schema,[env.source])

@pytest.mark.parametrize('fault',['missing_source','quote','duplicate','action_is_condition'])
def test_invalid_source_analysis(env,fault):
    p=env.w.selected_profile(env.profile_id,env.profile_work_hash);a=source_plan(env)
    n=a['S1']['norms'][0]
    if fault=='missing_source':a={}
    elif fault=='quote':n['quote']='없는 규정'
    elif fault=='duplicate':n['regulated_actions']*=2
    else:n['applicability_conditions']=n['regulated_actions'][:]
    with pytest.raises(ContractError):sem.validate_source(a,sem.source_schema(p,[env.source]),[env.source])

def test_action_modality_assembly_preserves_all_actions(env):
    o,p,a,w,s=fixtures(env);a['S1']['norms'][0]['regulated_actions']=[{'text':v,'quote':v} for v in ('물건을','제출한다')]
    c,r=sem.restore(w,s,a,[env.source]);acc.validate_proposal(c,p,[env.source],[env.w.load(o['bundle_id'])['normalized']])
    assert c['graph']['nodes'][0]['slots']['action']['value']=='물건을 / 제출한다'
    assert c['graph']['nodes'][0]['slots']['modality']['value']=='OBLIGATION'
    assert r['canonical_sha256']!=r['proposal_sha256'] and 'action' not in w['graph']['nodes'][0]['slots']

@pytest.mark.parametrize('axis',sem.AXES)
@pytest.mark.parametrize('state',['MISMATCH','UNCLEAR'])
def test_unsupported_verdict_rejected(env,axis,state):
    _,_,a,w,s=fixtures(env);w['comparisons'][0]['semantic_check'][axis]=state
    with pytest.raises(ContractError,match='SUPPORTED'):sem.restore(w,s,a,[env.source])

@pytest.mark.parametrize('fault',['missing_link','duplicate_link','invalid_index','action_in_wire','wrong_basis','false_contradiction'])
def test_binding_failures(env,fault):
    _,_,a,w,s=fixtures(env)
    if fault=='missing_link':w['norm_links']=[]
    elif fault=='duplicate_link':w['norm_links']*=2
    elif fault=='invalid_index':w['norm_links'][0]['norm_index']=10
    elif fault=='action_in_wire':w['graph']['nodes'][0]['slots']['action']={'state':'PRESENT','value':'새 행위'}
    elif fault=='wrong_basis':w['graph']['nodes'][0]['basis'][0]['quote']='물건'
    else:w['comparisons'][0]['verdict']='CONTRADICTED'
    with pytest.raises(ContractError):sem.restore(w,s,a,[env.source])

@pytest.mark.parametrize('part',['applicability_conditions','performance_requirements'])
def test_real_condition_allowed_and_unlinked_action_rejected(env,part):
    _,_,a,w,s=fixtures(env);phrase='가상 예외에는';a['S1']['norms'][0][part]=[{'text':phrase,'quote':phrase}]
    effect=w['graph']['nodes'][0];condition=deepcopy(effect);condition.update(id='C1',kind='CONDITION',text=phrase)
    condition['slots']={'statement':{'state':'PRESENT','value':phrase},'expression':{'state':'PRESENT','value':phrase},'scope':{'state':'NOT_RECORDED','value':None}}
    # Condition schema has additional mandatory slots: derive them from its variant.
    variant=next(v for v in s['properties']['graph']['properties']['nodes']['items']['anyOf'] if v['properties']['kind']['const']=='CONDITION')
    for key in variant['properties']['slots']['required']:condition['slots'].setdefault(key,{'state':'NOT_RECORDED','value':None})
    effect['slots']['conditions']={'state':'PRESENT','value':['C1']};w['graph']['nodes'].append(condition)
    w['condition_links']=[{'node_id':'C1','source':'S1','norm_index':0,'part':part,'item_index':0}]
    c,_=sem.restore(w,s,a,[env.source]);assert c['graph']['nodes'][1]['text']==phrase
    w['graph']['nodes'][1]['text']='물건을 제출한다'
    with pytest.raises(ContractError,match='CONDITION'):sem.restore(w,s,a,[env.source])

def test_workflow_source_blind_reuse_and_receipts(env):
    o,p,a,w,s=fixtures(env);calls=[]
    def generate(prompt,ctx,schema):
        calls.append(deepcopy(ctx))
        if ctx.get('operation')=='SOURCE_ANALYSIS':
            assert set(ctx)=={'operation','originals','profile_hash','call_budget'}
            return deepcopy(a),{'call':'source'}
        assert ctx['source_analysis']==a and ctx['observations']
        return deepcopy(w),{'call':'accumulation'}
    env.w.generate=generate
    kw=dict(bundle_id='cb-kb-source',expected_revision=0,profile_id=env.profile_id,profile_work_hash=env.profile_work_hash,observation_ids=[o['bundle_id']],originals=[env.source])
    saved=env.w.accumulate(**kw);loaded=env.w.load(saved['bundle_id'])
    assert len(calls)==2 and loaded['model_receipt']['source_analysis']==a
    assert loaded['model_receipt']['semantic_assembly']['semantic_checks']
    env.w.accumulate(**{**kw,'bundle_id':'cb-kb-second'})
    # Matching changes after saving the first knowledge bundle; source-only
    # context stays identical and reuses its result, accumulation is new.
    assert len(calls)==3 and sum(c.get('operation')=='SOURCE_ANALYSIS' for c in calls)==1
    assert env.w.preview(saved['bundle_id'])

def test_source_failure_repair_once_and_no_accumulation(env):
    o,_,a,_,_=fixtures(env);calls=[]
    def generate(prompt,ctx,schema):
        calls.append(ctx);assert ctx.get('operation')=='SOURCE_ANALYSIS'
        return {},{'call':len(calls)}
    env.w.generate=generate
    with pytest.raises(ContractError):env.w.accumulate(bundle_id='cb-kb-fail',expected_revision=0,profile_id=env.profile_id,profile_work_hash=env.profile_work_hash,observation_ids=[o['bundle_id']],originals=[env.source])
    assert len(calls)==2 and 'observations' not in calls[-1]

def test_no_base_schema_excludes_same(env):
    o=add_observation(env);p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
    n=env.w.load(o['bundle_id'])['normalized']
    schema=acc.accumulation_schema(p,[n],originals=[env.source])
    assert 'SAME' not in schema['properties']['comparisons']['items']['properties']['relation']['enum']
    value=proposal(env,o,relation='SAME')
    with pytest.raises(ContractError):validate(value,schema)

def test_existing_base_schema_retains_exact_same(env):
    o=add_observation(env);p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
    n=env.w.load(o['bundle_id'])['normalized'];value=proposal(env,o)
    base={'proposal':value,'observation_ledger':{}}
    schema=acc.accumulation_schema(p,[n],base,originals=[env.source])
    assert 'SAME' in schema['properties']['comparisons']['items']['properties']['relation']['enum']
    value['comparisons'][0]['relation']='SAME';validate(value,schema)
    acc.validate_proposal(value,p,[env.source],[n],base)
