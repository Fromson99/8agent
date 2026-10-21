"""Question-bound definition/reference locations; hints never adopt source evidence."""
from copy import deepcopy
import json
from ..contracts import digest
from ..navigation_match import SurfaceIndex, norm
from ..term_references import reference_targets
from .errors import ContractError, BudgetExhausted
from .repository import text_hash
from .law_candidates import token

PAGE_SIZE = 8
VERSION = 'definition-entry-v1'


def matches(session):
    index = SurfaceIndex()
    # Use the existing generation-bound document definitions. No answer labels,
    # source-name guesses, glossary synonyms or generated legal relationships.
    summaries=(session.tools.definition_summaries_for(question=session.context.request['question'])
               if hasattr(session.tools,'definition_summaries_for') else getattr(session.tools,'definition_summaries',None))
    if summaries is not None:
        for ident,source_id,key,*_ in summaries:
            if session.tools.sources[source_id]['document_id'] in session.scope:index.add(key,ident)
    else:
        for ident, definition in session.tools.definitions.items():
            if definition['document_id'] in session.scope:index.add(definition.get('label') or definition['key'],ident)
    question = session.context.request['question']
    found = index.match(question)
    rows = {ident: {'definition_id': ident, 'question_span':
        {'start': hit['start'], 'end': hit['end'], 'text': hit['text']}}
        for hit in found for ident in hit['values']}
    from . import query_scope as qs
    if qs.active(session):
        rows={k:v for k,v in rows.items() if qs.direct(session,session.tools.definitions[k]['document_id'],session.tools.definitions[k]['unit_id'])}
    return sorted(rows.values(), key=lambda r:(r['question_span']['start'],r['definition_id']))


def location(session, source_id, unit_id):
    source = session.tools.sources.get(source_id)
    if not source or source['document_id'] not in session.scope:
        raise ContractError('definition entry source outside request scope')
    did = source['document_id']; uid = str(unit_id)
    if (did,uid) not in session.matcher.units or source_id not in session.matcher._unit_sources(did,uid):
        raise ContractError('definition entry unit/source mismatch')
    return {'document_id':did,'source_id':source_id,'unit_id':uid,
            'document_name':source['document_name'],'heading':source.get('heading',''),
            'coordinate':session.matcher.units[(did,uid)].get('surface','')}


def verified(session, match):
    d = session.tools.definitions[match['definition_id']]
    origin = location(session,d['source_id'],d['unit_id'])
    source = session.tools.sources[d['source_id']]
    raw = session.store.source(d['document_id'],str(d['block_id']))
    original = raw['text']
    if (d.get('source_text') != original or d.get('source_text_sha256') != text_hash(original)
            or d.get('source_artifact_sha256') != source['source_artifact_sha256']
            or str(raw['unit_id']) != str(d['unit_id'])
            or str(d['block_id']) not in {str(b['block_id']) for b in source['blocks']}):
        raise ContractError('definition entry original/hash mismatch')
    start,end=d.get('term_start'),d.get('term_end')
    if (type(start) is not int or type(end) is not int or not 0<=start<end<=len(original)
            or norm(original[start:end]) != norm(d.get('label') or d['key'])):
        raise ContractError('definition entry term span mismatch')
    result={**deepcopy(match),'label':d.get('label') or d['key'],'definition':origin,
        'scope_status':d.get('scope_status','UNRESOLVED'),'scope_hint':deepcopy(d.get('scope_hint',[])),
        'verification':'EXACT_ORIGINAL_LOCATION','citation_eligible':False,'connections':[]}
    # IndexTools.references is a request-local cache populated only after READ.
    # Initial entry must use the immutable index, without fabricating a seen source.
    db=session.tools.db
    linked=(db.execute('SELECT l.reference_id,r.json FROM definition_reference l LEFT JOIN reference r ON r.id=l.reference_id WHERE l.definition_id=? ORDER BY l.reference_id',(d['id'],))
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='definition_reference' AND type='table'").fetchone() else ())
    for row in linked:
        if row[1] is None:raise ContractError('definition entry linked reference missing')
        ref=json.loads(row[1])
        if ref.get('id')!=row[0]:raise ContractError('definition entry reference identity mismatch')
        if (ref['source_id'] != d['source_id'] or ref['document_id'] != d['document_id']
                or str(ref['block_id']) != str(d['block_id'])
                or not ref.get('source_text') or ref['source_text'] not in original
                or ref.get('source_text_sha256') != text_hash(ref['source_text'])):
            raise ContractError('definition entry reference witness mismatch')
        mention=original[ref['mention_start']:ref['mention_end']]
        if mention != ref.get('mention_text',ref['locator']):
            raise ContractError('definition entry reference span mismatch')
        refs={'reference_id':ref['id'],'locator':ref['locator'],'resolution':ref['resolution'],'targets':[]}
        if str(ref['resolution']).startswith('EXACT_'):
            for target in reference_targets(ref):
                src=session.tools.sources.get(target.get('source_id'))
                if not src:raise ContractError('definition entry reference source missing')
                if src['document_id'] not in session.scope:
                    refs['scope_limited']=True
                    continue
                uid=target.get('unit_id') or src['unit_id']
                where=location(session,target['source_id'],uid)
                if set(map(str,target.get('block_ids',[])))-{str(b['block_id']) for b in src['blocks']}:
                    raise ContractError('definition entry reference blocks mismatch')
                from . import query_scope as qs
                if not qs.direct(session,where['document_id'],where['unit_id']):
                    refs['scope_limited']=True
                    continue  # The acquired definition's references are handled by unit_relations.
                refs['targets'].append(where)
        result['connections'].append(refs)
    return result


def page(session, rows, offset=0):
    if type(offset) is not int or offset<0 or offset%PAGE_SIZE or (offset>=len(rows) and offset!=0):
        raise ContractError('invalid definition entry cursor')
    items=[verified(session,row) for row in rows[offset:offset+PAGE_SIZE]]
    return {'contract':VERSION,'items':items,'total':len(rows),'offset':offset,
            'next_offset':offset+len(items) if offset+len(items)<len(rows) else None,
            'binding':digest([session.context.request['question'],sorted(session.scope),rows]),
            'rule':'Definitions and explicit reference destinations are navigation hints. Read originals and check applicability before adoption.'}


def render(inv, offer):
    if not inv.policy.get('definition_entry'):return None
    if 'definition_matches' not in inv.p:
        inv.p['definition_matches']=matches(inv.s)
        inv.p['definition_offset']=0
    if not inv.p['definition_matches']:return None
    value=page(inv.s,inv.p['definition_matches'],inv.p.get('definition_offset',0))
    inv.p['definition_visible_ids']=list(dict.fromkeys(inv.p.get('definition_visible_ids',[])+[r['definition_id'] for r in value['items']]))
    # All source/target locations are checked before any action becomes offered.
    for item in value['items']:
        for node in [item['definition'],*[t for c in item['connections'] for t in c['targets']]]:
            node['law_id']=token(inv.s,'L',node['document_id'])
            if node['law_id'] not in inv.p['laws']:
                inv.add_laws([{'document_id':node['document_id'],'article_count':None,'unit_count':None}])
            identity={k:node[k] for k in ('document_id','source_id','unit_id')}
            node['read_action']=offer('READ_ARTICLES',identity,node['document_name']+' '+node['heading']+' '+node['coordinate']+' 정의 연결 원문 읽기')
    if value['next_offset'] is not None:
        value['next_action']=offer('NEXT_DEFINITIONS',{'offset':value['next_offset'],'binding':value['binding']},'질문 용어의 다른 정의·명시 참조 위치 계속 보기')
    inv.p['definition_page']={k:value[k] for k in ('offset','next_offset','binding','total')}
    return value


def acquired_receipt(inv, target, identity):
    """A returned tool call alone does not prove that its original was acquired."""
    receipts=[]
    for plan_id, plan in inv.p.get('read_plans',{}).items():
        if plan.get('status')!='ACQUIRED' or identity not in plan.get('targets',[]):continue
        gid=plan.get('completed',{}).get(target)
        record=inv.p.get('selected',{}).get(gid)
        if (record and record.get('complete') is True and record.get('source_id')==identity['source_id']
                and record.get('document_id')==identity['document_id']):
            receipts.append({'plan_id':plan_id,'group_id':gid,'source_id':record['source_id']})
    if len(receipts)!=1:
        raise ContractError('definition original lacks one completed acquisition receipt')
    return receipts[0]


def acquire_initial(inv):
    """Acquire the complete exact-location queue under the existing read budget.

    A presentation page is not a retrieval cutoff. Each successful target is
    checkpointed independently; failed or budget-blocked targets remain pending.
    """
    if not inv.policy.get('definition_entry') or inv.p.get('accepted'):
        return
    seed=inv.p.get('system_definition_seed')
    if seed:
        check_navigation_origin(seed)
        expected=digest([inv.s.context.request['question'],sorted(inv.s.scope),inv.p.get('definition_matches',[])])
        if seed.get('binding')!=expected or set(seed.get('completed',[]))-set(seed['targets']):
            raise ContractError('definition acquisition binding changed')
        for target in seed['targets']:
            action=seed.get('actions',{}).get(target)
            if not action or target!='SYSDEF:'+digest(action['identity']) or action['action']!='READ_ARTICLES':
                raise ContractError('definition acquisition target changed')
        if seed['status']=='COMPLETE':
            if set(seed['targets'])!=set(seed.get('completed',[])):
                raise ContractError('definition acquisition completion is incomplete')
            return
    if seed is None:
        actions={}
        rows=inv.p.setdefault('definition_matches',matches(inv.s))
        inv.p.setdefault('definition_offset',0)
        for match in rows:
            item=verified(inv.s,match)
            for node in [item['definition'],*[t for c in item['connections'] for t in c['targets']]]:
                law=token(inv.s,'L',node['document_id'])
                if law not in inv.p['laws']:
                    inv.add_laws([{'document_id':node['document_id'],'article_count':None,'unit_count':None}])
                identity={k:node[k] for k in ('document_id','source_id','unit_id')}
                ident='SYSDEF:'+digest(identity)
                actions[ident]={'id':ident,'action':'READ_ARTICLES','identity':identity,
                    'label':node['document_name']+' '+node['heading']+' '+node['coordinate']+' 정의 연결 원문 읽기'}
        seed={'status':'STARTED','targets':list(actions),'actions':actions,'completed':[],
              'binding':digest([inv.s.context.request['question'],sorted(inv.s.scope),rows]),
              'pending_reasons':{},'acquired_groups':[],'omitted_targets':0}
        if getattr(inv,'modern',False):
            origin={k:deepcopy(inv.p[k]) for k in NAVIGATION_KEYS if k in inv.p}
            seed.update(navigation_policy='restore-automatic-definition-v1',
                        navigation_origin=origin,navigation_origin_hash=digest(origin))
        inv.p['system_definition_seed']=seed;inv.save()
    completed=seed.setdefault('completed',[])
    pending_reasons=seed.setdefault('pending_reasons',{})
    acquired=seed.setdefault('acquired_groups',[])
    for target in seed['targets']:
        if target in completed:continue
        if inv.left()<=max(1,inv.s.profile['selection_time_reserve_seconds']):
            pending_reasons[target]='FINALIZATION_TIME_RESERVE'
            break
        seed['status']='STARTED';seed['current_target']=target;inv.save()
        decision={'next_action':'READ_ARTICLES','targets':[target],'issue_refs':[],'basis_refs':[],
                  'law_decisions':[],'branch_decisions':[],'notes':'',
                  'reason':'시스템: 질문의 정의 원문과 검증된 명시 참조 원문 우선 확보 (채택 전)'}
        try:
            inv.execute_tool(decision,{'sources':[]},seed['actions'])
            receipt=acquired_receipt(inv,target,seed['actions'][target]['identity'])
        except BudgetExhausted as error:
            pending_reasons[target]=str(error);seed['status']='PARTIAL';inv.save()
            break
        except BaseException as error:
            # Preserve the interruption and original exception; no failure is
            # converted to a completed read or retried by a second owner.
            seed['status']='INTERRUPTED';pending_reasons[target]=type(error).__name__
            inv.save();raise
        finally:
            if restore_navigation_origin(inv,seed):inv.save()
        completed.append(target);pending_reasons.pop(target,None)
        seed.setdefault('completed_receipts',{})[target]=receipt
        if seed.get('navigation_policy')=='restore-automatic-definition-v1':
            if receipt['group_id'] not in acquired:acquired.append(receipt['group_id'])
        else:
            acquired.extend(g for g in inv.p.get('window_groups',[]) if g not in acquired)
            inv.p['window_groups']=list(acquired)
        inv.save()
    seed.pop('current_target',None)
    pending=[target for target in seed['targets'] if target not in completed]
    seed['status']='PARTIAL' if pending else 'COMPLETE'
    inv.s.repo.event('SYSTEM_DEFINITION_ORIGINALS_PENDING' if pending else 'SYSTEM_DEFINITION_ORIGINALS_ACQUIRED',{
        'targets':seed['targets'],'completed':list(completed),'pending':pending,
        'binding':seed.get('binding'),'omitted_targets':0,
        'model_calls':0,'adopted':False})
    inv.save()


NAVIGATION_KEYS = ('window','window_groups','focus','structure_location')


def check_navigation_origin(seed):
    policy=seed.get('navigation_policy')
    if policy is None:return
    origin=seed.get('navigation_origin')
    if (policy!='restore-automatic-definition-v1' or not isinstance(origin,dict)
            or set(origin)-set(NAVIGATION_KEYS)
            or digest(origin)!=seed.get('navigation_origin_hash')):
        raise ContractError('definition navigation origin changed')


def restore_navigation_origin(inv,seed):
    """Restore only automatic reading focus; acquired originals are permanent."""
    check_navigation_origin(seed)
    if not seed.get('navigation_policy'):return False
    origin=seed['navigation_origin']
    for name in NAVIGATION_KEYS:
        if name in origin:inv.p[name]=deepcopy(origin[name])
        else:inv.p.pop(name,None)
    return True
