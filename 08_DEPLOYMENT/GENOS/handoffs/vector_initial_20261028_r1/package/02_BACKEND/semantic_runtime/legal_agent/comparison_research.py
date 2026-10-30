"""Exact task acquisition inside the existing native investigation and journal."""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError, BudgetExhausted
from .workflow_execution import task_context
OPS=('read_node','locate_provision','lookup_definition','follow_reference','search_structure','search_subtree','search_text')


def validate_task(task):
    keys={'schema_version','task_id','issue_id','target_side','requested_fields','missing_target','anchor_refs','target_locator','operation','allowed_operations','completion_conditions','binding_hash'}
    if (not isinstance(task,dict) or set(task)!=keys or task['schema_version']!='comparison-research-v1' or
        task['target_side'] not in ('internal','external') or task['operation'] not in OPS or task['allowed_operations']!=[task['operation']] or
        not isinstance(task['missing_target'],str) or not 0<len(task['missing_target'])<=500 or
        not isinstance(task['requested_fields'],list) or not task['requested_fields'] or
        not isinstance(task['anchor_refs'],list) or any(a.get('role')!='SEARCH_HINT_ONLY' for a in task['anchor_refs'])):
        raise ContractError('invalid research task contract')
    if task['operation']=='follow_reference' and not (task.get('target_locator') or {}).get('reference_id'):raise ContractError('reference task lacks witnessed reference')
    if task['operation'] in ('read_node','locate_provision','search_subtree','follow_reference') and not isinstance(task['target_locator'],dict):raise ContractError('research operation requires locator')


def recall(recaller):
    task=(task_context() or {}).get('research_task')
    preferred=(task_context() or {}).get('preferred_document_ids',[])
    if not task and not preferred:return None
    if not task:task={'missing_target':recaller.s.context.request.get('question','지정 문서 원문'),'preferred_document_ids':preferred}
    if task.get('schema_version'):validate_task(task)
    from . import law_candidates as lc
    s=recaller.s;idx,_=lc.index(s)
    # No unrelated fulltext expansion before the requested exact operation.
    page={'items':[],'total':0,'next_cursor':None}
    catalogue={'contract':lc.CONTRACT,'terms':[],'queries':[],'route_queries':[task['missing_target']],
        'query_origin':'comparison-research-v1','law_page':page,'query_fingerprint':digest(task),
        'index_sha256':idx.manifest['index_sha256'],'search_policy':'best-own-block-match-v1'}
    return [],{'discovery_mode':'fulltext','law_navigation':catalogue,'unit_hits':[],
        'unit_index_sha256':idx.manifest['index_sha256'],'selected_for_read':[],'discovered':[],
        'routes':{},'queries':[],'parent_selections_preserved':True}


def acquire(inv):
    task=(task_context() or {}).get('research_task')
    if not task:return
    validate_task(task)
    from ..research_state import NativeResearchTasks
    tasks=NativeResearchTasks(inv.p);key=task['task_id']
    created=key not in tasks.tasks
    seed=tasks.begin(task)
    if tasks.terminal(seed):return
    if created:inv.save()
    src=inv.s.source;loc=task['target_locator'];op=task['operation']
    if loc and loc['document_id'] not in inv.s.scope:raise ContractError('native research target outside child scope')
    if seed['lookup'] is None:
        if op in ('read_node','follow_reference'):
            nodes=[{'document_id':loc['document_id'],'unit_id':loc['unit_id'],'source_id':loc['source_id']}]
            seed['lookup']={'status':'OK','direct_verified_locator':loc,'next_cursor':None}
        else:
            args={'query':task['missing_target'],'cursor':None}
            if op=='locate_provision':args={'document':src.handle('D',loc['document_id']),'coordinate':task['missing_target'],'cursor':None}
            elif op=='search_subtree':args={'node':src.node(loc['document_id'],loc['unit_id'],loc['source_id']),'query':task['missing_target'],'cursor':None}
            elif op in ('search_text','search_structure'):args['document']=src.handle('D',loc['document_id']) if loc else None
            from ..workflow_bridge import SourcePort
            result=SourcePort(src).execute({'operation':op,'side':task['target_side'],'args':args,'reason':'지정 비교 항목의 부족 원문 조사'})
            seed['lookup']=result
            nodes=[src.resolve(item['node'],'U') for item in result.get('items',[]) if item.get('node')]
            if result.get('status') not in ('OK','NOT_FOUND','UNRESOLVED'):
                tasks.finish(seed,'FAILED');inv.save();return
        for node in nodes:
            did=node['document_id'];uid=node['unit_id']
            if did not in inv.s.scope:raise ContractError('research lookup returned foreign side')
            ids=inv.s.matcher._unit_sources(did,str(uid)) if uid is not None else [node['source_id']]
            for sid in ids:
                identity={'document_id':did,'unit_id':str(uid) if uid is not None else str(inv.s.tools.sources[sid]['unit_id']),'source_id':sid}
                ident='SYSTASK:'+digest([key,identity]);seed['actions'][ident]={'id':ident,'action':'READ_ARTICLES','identity':identity,'label':'비교 항목의 지정 원문 읽기'}
        inv.save()
    from .law_candidates import token
    from .definition_entry import acquired_receipt
    for ident,action in seed['actions'].items():
        if ident in seed['completed']:continue
        did=action['identity']['document_id'];law=token(inv.s,'L',did)
        if law not in inv.p['laws']:inv.add_laws([{'document_id':did,'article_count':None,'unit_count':None}])
        if inv.left()<=max(1,inv.s.profile['selection_time_reserve_seconds']):tasks.finish(seed,'PARTIAL');inv.save();return
        decision={'next_action':'READ_ARTICLES','targets':[ident],'issue_refs':[],'basis_refs':[],
            'law_decisions':[],'branch_decisions':[],'notes':'','reason':'시스템: 지정 항목의 정확 원문 우선 확보; 채택은 별도 판단'}
        try:
            inv.execute_tool(decision,{'sources':[]},seed['actions'])
            receipt=acquired_receipt(inv,ident,action['identity'])
        except BudgetExhausted:
            tasks.finish(seed,'PARTIAL');inv.save();raise
        seed.setdefault('receipts',{})[ident]=receipt;seed['completed'].append(ident);inv.save()
    tasks.finish(seed,'COMPLETE' if seed['completed'] and not seed['lookup'].get('next_cursor') else 'PARTIAL')
    inv.s.repo.event('COMPARISON_TASK_ACQUIRED',{'task_id':key,'status':seed['status'],'completed':seed['completed'],
        'lookup_status':seed['lookup'].get('status'),'adopted':False,'absence_proven':False})
    inv.save()
