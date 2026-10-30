"""Shared pure Qwen FP8 routing policy. Network/retry ownership stays with callers."""
from copy import deepcopy
import json
from ..contracts import digest
from .errors import ContractError

VERSION='qwen38-request-provider-v1'
EVENT='MODEL_PROVIDER_STATE'

def validate_policy(cfg,model='qwen/qwen3.8-27b'):
    allowed={'parasail/fp8':'Parasail','chutes/fp8':'Chutes','near-ai/fp8':'Near AI'}
    providers=cfg.get('providers',[]);auth=cfg.get('authorization',{})
    if (cfg.get('schema_version')!='qwen38-provider-routing-v1' or cfg.get('model')!=model
        or not 1<=len(providers)<=3 or any(not isinstance(p,dict) or set(p)!={'tag','name'} or allowed.get(p.get('tag'))!=p.get('name') for p in providers)
        or len({p['tag'] for p in providers})!=len(providers)
        or cfg.get('switch_http_status')!=[429] or cfg.get('max_provider_switches')!=1
        or cfg.get('model_fallback') is not False or cfg.get('quantizations')!=['fp8']
        or cfg.get('reasoning')!={'effort':'none'} or auth.get('source')!='user_message'
        or not str(auth.get('text','')).strip() or not auth.get('session_id')):
        raise ValueError('Invalid explicit Qwen3.8 provider routing policy')
    return deepcopy(cfg)

def route(provider):
    return {'only':[provider['tag']],'order':[provider['tag']],'quantizations':['fp8'],
        'allow_fallbacks':False,'require_parameters':True}

def validate_response(body,provider,model):
    if body.get('provider')!=provider['name'] or body.get('model')!=model:
        raise ValueError('Qwen response model/provider mismatch')
    if ((body.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or any(
        c.get('message',{}).get('reasoning') for c in body.get('choices',[])):
        raise ValueError('Qwen reasoning was not disabled')

def current(repo,policy,policy_hash,binding_hash):
    state={'version':VERSION,'policy_sha256':policy_hash,'binding_hash':binding_hash,'index':0,'switches':0}
    previous=None
    for kind,text,hashed in repo.db.execute('SELECT kind,payload_json,payload_hash FROM event WHERE kind IN (?,?) ORDER BY seq',(EVENT,EVENT+'_RESUMED')):
        row=json.loads(text)
        if digest(row)!=hashed or row['policy_sha256']!=policy_hash or row['binding_hash']!=binding_hash:
            raise ContractError('request provider state binding/hash mismatch')
        resumed=kind==EVENT+'_RESUMED' and previous is None and row.get('prior_run_id') and row.get('prior_state_hash')
        if not resumed and (row.get('previous')!=previous or row['switches']!=state['switches']+1 or row['index']!=state['index']+1):
            raise ContractError('request provider transition history mismatch')
        if type(row['switches']) is not int or row['switches'] not in (0,1) or row['index']!=row['switches'] or row['switches']>policy['max_provider_switches'] or row['index']>=len(policy['providers']):
            raise ContractError('request provider transition limit violated')
        previous=hashed;state=row
    return state,previous

def switch(repo,policy,policy_hash,binding_hash,attempt_id,response):
    state,previous=current(repo,policy,policy_hash,binding_hash)
    if response.get('status_code')!=429 or response.get('acceptance')!='KNOWN_REJECTED':return False
    if state['switches']>=policy['max_provider_switches'] or state['index']+1>=len(policy['providers']):return False
    row={**state,'index':state['index']+1,'switches':state['switches']+1,'previous':previous,
        'after_attempt_id':attempt_id,'http_status':429,'response_sha256':response.get('body_sha256')}
    repo.event(EVENT,row)
    return True
