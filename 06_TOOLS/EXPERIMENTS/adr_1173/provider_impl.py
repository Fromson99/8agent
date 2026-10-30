from common import *
import sys,shutil
S=ROOT/read(DES/'candidate.json')['snapshot'];B=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(n,a,b):
 p=B/n;s=p.read_text();assert a in s,(n,a[:90]);p.write_text(s.replace(a,b))
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=S.parent
for name in ('00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json','02_BACKEND/lawrag/research/experiment_client.py'):
 p=S/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);ac.register_file(C,name,upstream_state='present')
p=B/'provider_routing.py';p.write_text('''"""Shared pure Qwen FP8 routing policy. Network/retry ownership stays with callers."""
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
    for text,hashed in repo.db.execute('SELECT payload_json,payload_hash FROM event WHERE kind=? ORDER BY seq',(EVENT,)):
        row=json.loads(text)
        if digest(row)!=hashed or row['policy_sha256']!=policy_hash or row['binding_hash']!=binding_hash:
            raise ContractError('request provider state binding/hash mismatch')
        if row.get('previous')!=previous or row['switches']!=state['switches']+1 or row['index']!=state['index']+1:
            raise ContractError('request provider transition history mismatch')
        if row['switches']>policy['max_provider_switches'] or row['index']>=len(policy['providers']):
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
''')
# Policy remains separate from model grant; its digest is part of actual request model binding.
edit('local_gemma.py',"        self.binding = {", "        from .provider_routing import validate_policy\n        self.routing_path=self.code_root/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'\n        self.provider_policy=validate_policy(json.loads(self.routing_path.read_text())) if self.routing_path.exists() else None\n        self.routing_hash=_sha(self.routing_path) if self.provider_policy else None\n        self.binding = {")
edit('local_gemma.py',"'adapter_version': 'openrouter-local-public-v2',", "'adapter_version': 'openrouter-local-public-v3:'+self.routing_hash if self.provider_policy else 'openrouter-local-public-v2',")
edit('local_gemma.py',"        payload['provider'] = copy.deepcopy(self.policy['provider_routing'])", """        selected=None
        if self.provider_policy:
            from .provider_routing import route
            if _sha(self.routing_path)!=self.routing_hash:raise ContractError('serving provider policy changed')
            index=ticket.get('provider_index')
            if type(index) is not int or not 0<=index<len(self.provider_policy['providers']):raise ContractError('gateway provider selection missing')
            selected=self.provider_policy['providers'][index]
            if body.get('provider')!=route(selected):raise ContractError('provider request differs from reserved physical attempt')
        payload['provider'] = route(selected) if selected else copy.deepcopy(self.policy['provider_routing'])""")
edit('local_gemma.py',"        if data.get('provider') != 'Parasail' or data.get('model') != self.binding['model']:", "        if selected:\n            from .provider_routing import validate_response\n            try:validate_response(data,selected,self.binding['model'])\n            except ValueError as exc:raise ContractError(str(exc)) from exc\n        if data.get('provider') != (selected['name'] if selected else 'Parasail') or data.get('model') != self.binding['model']:")
# Explicit429 classification must not depend on a JSON error body.
a="""        except ValueError as exc:
            raise TransportError('local Qwen3.8 returned non-JSON response', retryable=False) from exc"""
b="""        except ValueError as exc:
            if response.status_code==429:data={}
            else:raise TransportError('local Qwen3.8 returned non-JSON response', retryable=False,unknown=response.status_code>=500) from exc"""
edit('local_gemma.py',a,b)
edit('gateway.py',"        while True:\n            remaining = self.context.remaining()", """        while True:
            routing=getattr(self.transport,'provider_policy',None)
            provider_index=None
            if routing:
                from . import provider_routing
                provider_state,_=provider_routing.current(self.repo,routing,self.transport.routing_hash,self.context.binding_hash)
                provider_index=provider_state['index']
                request={**request,'provider':provider_routing.route(routing['providers'][provider_index]),'reasoning':{'effort':'none'}}
            remaining = self.context.remaining()""")
edit('gateway.py',"                ticket = {'attempt_id': ident, 'remaining_seconds': remaining}", "                ticket = {'attempt_id': ident, 'remaining_seconds': remaining,**({'provider_index':provider_index} if routing else {})}")
edit('gateway.py',"                obs.event(log, 'model.attempt.failed',", """                if routing:
                    budget=self.repo.budget()
                    limit=budget['model_limit']-(budget['finalization_reserve'] if phase=='investigate' else 0)
                    retry_scheduled=(not exc.unknown and response.get('status_code')==429 and response.get('acceptance')=='KNOWN_REJECTED'
                        and not (projection and projection.emitted) and budget['model_reserved']<limit and self.context.remaining()>1)
                    retry_scheduled=retry_scheduled and provider_routing.switch(self.repo,routing,self.transport.routing_hash,self.context.binding_hash,ident,response)
                    retry_delay=0.0
                obs.event(log, 'model.attempt.failed',""")
# Research shares pure policy, while retaining its independent client-lifetime budget.
p=S/'02_BACKEND/lawrag/research/experiment_client.py';s=p.read_text();a=s.index("        allowed={'parasail/fp8'",s.index('    def _configure_provider_policy'));b=s.index('        self.provider_policy=cfg;',a)
s=s[:a]+"        from semantic_runtime.legal_agent.provider_routing import validate_policy\n        validate_policy(cfg,self.model)\n"+s[b:]
s=s.replace("        self.proxy['provider_routing']={'only':[provider['tag']],'order':[provider['tag']],\n            'quantizations':['fp8'],'allow_fallbacks':False,'require_parameters':True}","        from semantic_runtime.legal_agent.provider_routing import route\n        self.proxy['provider_routing']=route(provider)")
p.write_text(s)
print('shared pure provider policy and request-scoped gateway switch connected')
