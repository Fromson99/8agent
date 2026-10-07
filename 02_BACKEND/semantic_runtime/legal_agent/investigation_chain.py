"""Durable explicit decisions and immutable menus; returning never rewinds memory."""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError

CONTRACT = 'investigation-action-chain-v1'
STRIP = {'investigation_chain', 'return_points', 'return_context', 'presentation_id'}

def state(p):
    out=p.setdefault('action_chain', {'contract':CONTRACT,'frames':{},'steps':[],'current_frame':None})
    if out.get('contract')!=CONTRACT:raise ContractError('investigation chain contract changed')
    out.setdefault('entry_frame_id', next((f['id'] for f in sorted(out['frames'].values(), key=lambda f:f['number'])), None))
    out.setdefault('arrivals', [])
    return out

def capture(p, kind, data, *, actions=None, location=None, offered=None):
    memory=state(p);raw=deepcopy({k:v for k,v in data.items() if k not in STRIP})
    payload={'kind':kind,'data':raw,'actions':deepcopy(actions or {}),
             'location':deepcopy(location or {}),'offered':deepcopy(offered or {})}
    key='H'+digest(payload)[:28]
    if key not in memory['frames']:
        memory['frames'][key]={'id':key,'number':len(memory['frames'])+1,
            'arrived_after':memory['steps'][-1]['id'] if memory['steps'] else None,**payload}
    memory['current_frame']=key
    if memory['entry_frame_id'] is None:memory['entry_frame_id']=key
    if not memory['arrivals'] or memory['arrivals'][-1]['frame_id']!=key:
        memory['arrivals'].append({'sequence':len(memory['arrivals'])+1,'frame_id':key,
                                  'after_step':memory['steps'][-1]['id'] if memory['steps'] else None})
    return key

def frame(p, key):
    try:return state(p)['frames'][key]
    except KeyError:raise ContractError('unknown historical investigation point')

def begin(p, data, decision, actions=None, *, kind='NAVIGATION'):
    memory=state(p);origin=data.get('chain_frame_id') or memory['current_frame']
    if origin not in memory['frames']:raise ContractError('decision has no bound historical menu')
    key='S'+digest({'origin':origin,'decision':decision,'turn':p.get('turn',0),'kind':kind})[:28]
    receipt=key
    old=next((x for x in reversed(memory['steps']) if x.get('receipt',x['id'])==receipt),None)
    if old and old['status'] in ('ACCEPTED','INTERRUPTED'):return old
    if old:key='S'+digest([key,len(memory['steps'])])[:28]
    targets=decision.get('targets',[])
    row={'id':key,'receipt':receipt,'number':len(memory['steps'])+1,'from_frame':origin,
         'previous_step':memory['steps'][-1]['id'] if memory['steps'] else None,
         'kind':kind,'action':decision.get('next_action','REFERENCE_CHOICES'),
         'reason':decision.get('reason','현재 제시된 연결을 선택') if kind!='REFERENCE' else '각 연결의 명시적 선택 이유를 기록',
         'targets':[deepcopy(actions[t]) for t in targets] if actions else [],
         'law_decisions':deepcopy(decision.get('law_decisions',[])),
         'branch_decisions':deepcopy(decision.get('branch_decisions',[])),
         'reference_decisions':deepcopy(decision.get('decisions',[])),
         'basis_refs':deepcopy(decision.get('basis_refs',[])),
         'queries':deepcopy(decision.get('queries',[])),
         'notes':decision.get('notes',''),'sufficiency_reason':decision.get('sufficiency_reason',''),
         'status':'ACCEPTED'}
    memory['steps'].append(row)
    return row

def context(p):
    memory=state(p)
    steps=deepcopy(memory['steps']);judgments={}
    if p.get('control_contract'):
        for step in steps:
            step['judgment_refs']=[]
            for field in ('law_decisions','branch_decisions','reference_decisions'):
                for row in step.pop(field,[]):
                    key='J'+digest({'kind':field,'decision':row})[:28]
                    judgments.setdefault(key,{'id':key,'kind':field,'decision':row})
                    step['judgment_refs'].append(key)
    # Every explicit action and reason remains visible. No history truncation.
    return {'contract':CONTRACT,'current_frame':memory['current_frame'],
            'steps':steps, 'judgments':list(judgments.values()),
            'entry_frame_id':memory['entry_frame_id'],
            'entry_search':{'queries':memory['frames'][memory['entry_frame_id']]['data'].get('search_queries',[]) if memory['entry_frame_id'] else [],
                'reason':'현재 질문의 원문 근거를 찾기 위한 실행된 검색 계획','reason_origin':'SYSTEM_ENTRY'},
            'memory_rule':'과거 메뉴로 돌아가도 확보 원문·채택·보류·후속 판단을 되돌리지 않는다'}

def points(p):
    rows=[]
    for f in sorted(state(p)['frames'].values(), key=lambda f:f['number']):
        d=f['data'];rows.append({'id':f['id'],'number':f['number'],'kind':f['kind'],
            'arrived_after':f['arrived_after'],'search_queries':d.get('search_queries',[]),
            'laws':[l['name'] for l in d.get('laws',[])],
            'originals':[s.get('heading',s.get('source_id')) for s in d.get('sources',[])],
            'reference_groups':len(d.get('groups',[]))})
    return rows
