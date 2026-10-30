"""Comparison mode in the existing native investigation: acquire, choose, return."""
from copy import deepcopy
import json
from ..contracts import digest
from .source_handoff import enabled
from .workflow_execution import task_context
from .errors import ContractError, BudgetExhausted, ToolExecutionError
from . import output_contract as output

SYSTEM=('대사 부모에게 전달할 원문을 조사한다. 비교·충분성·부합 판단은 부모가 한다. '
 '원문과 주어진 행동을 보고 더 필요한 조사 행동 target_id 하나를 고르거나 null로 반환한다. '
 '자료가 없거나 불완전해도 종료할 수 있다. 종료는 규정 부재나 검토 완료의 뜻이 아니다. '
 'references와 document_term_candidates의 미확인 연결·용어 사용 조항을 질문의 요구와 함께 검토한다. '
 'A만으로 관련성을 판단하기 어려우면 연결된 B를 읽고 A와 B를 함께 부모에게 전달할 수 있다. '
 'investigation_leads는 실제 읽지 않은 위치를 포함한다. 미리보기의 수치·조건을 확인한 원문으로 세지 않는다. '
 '질문의 남은 내용과 연결된 후보의 원문을 읽을지 선택한다. 반환 시 미열람 단서도 부모에게 전달된다. '
 '후보는 원문 확보나 적용 확정이 아니다. 모든 후보를 읽어야 종료하는 것은 아니다. '
 '이미 확보한 원문을 반복 읽지 말고 필요한 대상만 조사한다. query는 검색 행동에만 쓴다. '
 'research_continuity에는 같은 쟁점의 이전 조사 목적·실행·확보 원문과 부모의 판단이 있다. 이전 실패나 미해결을 새 요청처럼 초기화하지 않는다. '
 '검색 후보 발견은 원문 확보가 아니다. progress에서 새 원문 없이 탐색만 이어졌다면 아직 읽지 않은 관련 후보를 읽거나 다른 조사 경로를 선택하고, 가능한 경로가 없으면 확보 원문과 남은 단서를 반환한다. '
 '반대쪽 내용은 검색 단서일 뿐 이쪽 규정의 증거가 아니다. JSON만 출력한다.')


def choose(inv,data,actions,phase):
    allowed={k:v for k,v in actions.items() if v['action'] not in ('DECIDE','FINISH','PENDING')}
    schema={'type':'object','properties':{'target_id':{'enum':[None,*allowed]},
        'query':{'type':['string','null']},'reason':{'type':'string','minLength':1}},
        'required':['target_id','query','reason'],'additionalProperties':False}
    # Keep navigation menus and actual pages; remove the legal decision ledger.
    from . import investigation_leads as leads
    catalogue=leads.capture(inv,data)
    shown=deepcopy(data)
    shown['investigation_leads']=leads.projection(catalogue)
    continuity=(task_context() or {}).get('research_continuity')
    if continuity is not None:shown['research_continuity']=deepcopy(continuity)
    shown.pop('document_term_candidates',None)
    view=inv.bounded_model_view(shown)
    for k in ('branches','adopted_evidence','completion_contract','reading_rule','gap_resolutions','completion_check'):view.pop(k,None)
    view['source_return_rule']='target_id=null returns originals, including zero. No legal decision required.'
    view['actions']=list(allowed.values())
    view['acquisition']=deepcopy(inv.p.get('source_acquisition',{}))
    # Deterministically acquired short originals have not been shown by native page delivery.
    pref=set((task_context() or {}).get('preferred_document_ids',[]))
    originals=[{'evidence_id':e['evidence_id'],'document_id':e['document_id'],'text':'\n'.join(s['text'] for s in e['spans'])}
        for e in inv.s.repo.evidence() if e['document_id'] in pref]
    if len(json.dumps({**view,'preferred_originals':originals},ensure_ascii=False)) < inv.s.profile['max_context_chars']-4000:
        view['preferred_originals']=originals
    def proposal(raw):
        action=allowed[raw['target_id']]['action'] if raw['target_id'] else 'FINISH'
        return {'next_action':action,'targets':[raw['target_id']] if raw['target_id'] else [],
            'queries':[raw['query']] if action in ('RESEARCH','SEARCH_STRUCTURE','SEARCH_BODY') else [],
            'law_decisions':[],'branch_decisions':[],'issue_refs':[],'basis_refs':[],
            'notes':'','reason':raw['reason'],'sufficiency_reason':'부모 비교에서 판단','evidence_sufficient':False,
            'gap_ids':[],'gap_resolutions':[],'structure_filter':None,
            'state_version':inv.p.get('state_version'),'presentation_id':data['presentation_id']}
    def check(raw):
        output.validate_shape(raw,schema)
        if raw['target_id'] and allowed[raw['target_id']]['action'] in ('RESEARCH','SEARCH_STRUCTURE','SEARCH_BODY') and not (raw['query'] or '').strip():
            raise output.OutputContractError('search requires query',[output.issue('SEARCH_QUERY_REQUIRED')])
        value=proposal(raw)
        from . import tool_availability, request_repair
        tool_availability.require_navigation(inv,value,data,allowed)
        inv.validate_search_operation(value,allowed)
        if inv.modern:request_repair.validate_failed_operation(inv,value,allowed)
    def invoke(payload,attempt):
        try:return inv.invoke(SYSTEM,payload,schema,'source-law-sources-'+phase+('-repair' if attempt else ''),min(180,inv.left()))
        finally:
            if inv.control:
                from . import evidence_inventory as inventory
                if inventory.reconcile_delivery(inv.s,inv.p,data,'source-law-sources-'+phase):inv.save()
    raw=output.bounded_decision(inv.s.repo,'source-investigation',view,schema,invoke,check,
        identity={'binding':inv.p['binding'],'presentation':data['presentation_id'],'turn':inv.p['turn'],'view_hash':digest(view)},
        can_repair=lambda:inv.left()>1)
    if view.get('preferred_originals'):
        for did,entry in inv.p.get('source_acquisition',{}).get('documents',{}).items():
            if did in {e['document_id'] for e in view['preferred_originals']}:entry['delivered']=True
        inv.save()
    return proposal(raw)


def acquire_preferred(inv):
    if not enabled():return
    src=inv.s.source;task=task_context() or {};preferred=task.get('preferred_document_ids',[])
    if not set(preferred)<=set(inv.s.scope):raise ContractError('preferred document outside source scope')
    state=inv.p.setdefault('source_acquisition',{'documents':{},'references':{},'reads':{}})
    from ..workflow_bridge import SourcePort
    port=SourcePort(src)
    def call(op,args):
        return port.execute({'operation':op,'side':task['source_category'],'args':args,'reason':'시스템: 지정 원문과 명시 참조 확인'})
    def read_node(did,uid,sid=None):
        key=digest([did,uid,sid]);saved=state['reads'].setdefault(key,{'document_id':did,'unit_id':uid,'source_id':sid,'cursor':None,'status':'STARTED','evidence_ids':[]})
        if saved['status'] in ('COMPLETE','FAILED'):return saved
        while True:
            inv.save()
            from .unit_reading import POLICY
            if inv.p['read_state'].get('count',0)>=POLICY['read_actions'] or inv.p['read_state'].get('chars',0)>=POLICY['initial_chars']:
                saved.update(status='PARTIAL',reason='READ_BUDGET');inv.save();return saved
            if inv.left()<=max(1,inv.s.profile['selection_time_reserve_seconds']):
                saved['status']='PARTIAL';inv.save();return saved
            try:r=call('read_node',{'node':src.node(did,uid,sid),'cursor':saved['cursor']})
            except BudgetExhausted:
                saved['status']='PARTIAL';inv.save();raise
            except ToolExecutionError as exc:
                saved.update(status='FAILED',error=str(exc));inv.save();return saved
            saved['evidence_ids']=sorted(set(saved['evidence_ids'])|{e['evidence_id'] for e in r.get('items',[]) if e.get('evidence_id')})
            checkpoint=getattr(inv.s,'_unit_read_checkpoint',None)
            current=[src.repo.evidence(e['evidence_id']) for e in r.get('items',[]) if e.get('evidence_id')]
            inv.p['read_state']['count']=inv.p['read_state'].get('count',0)+1
            inv.p['read_state']['chars']=inv.p['read_state'].get('chars',0)+sum(len(s['text']) for e in current for s in e['spans'])
            if checkpoint:checkpoint(current,inv.p['read_state'])
            saved['cursor']=r.get('next_cursor')
            if r['status'] not in ('OK','NOT_FOUND','TRUNCATED'):
                saved.update(status='FAILED',result=r);inv.save();return saved
            saved['status']='PARTIAL' if saved['cursor'] else 'COMPLETE';inv.save()
            if not saved['cursor']:return saved
    for did in preferred:
        inv.add_laws([{'document_id':did,'article_count':None,'unit_count':None}])
        entry=state['documents'].setdefault(did,{'status':'STARTED','structure':[],'cursor':None,'listed':False,'read_keys':[]})
        if entry['status'] in ('COMPLETE','OUTLINE_ONLY'):continue
        while not entry['listed']:
            page=call('list_structure',{'document':src.handle('D',did),'cursor':entry['cursor']})
            entry['structure'].extend(page.get('items',[]));entry['cursor']=page.get('next_cursor');entry['listed']=not entry['cursor'];inv.save()
        blocks=[dict(r) for r in src.store.db.execute('SELECT block_id,text FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,))]
        serialized=len(json.dumps({'question':inv.question,'task':task,'outline':entry['structure'],'blocks':blocks,
            'existing_evidence':inv.s.repo.evidence()},ensure_ascii=False))
        allowance=inv.s.profile['max_context_chars']-8000
        budget=inv.s.repo.budget();available=budget['tool_limit']-budget['tool_used']
        # The per-read page/character limits remain owned by SourceSession.
        estimated=sum(max(1,(len(b['text'])+inv.s.profile['max_read_chars']-1)//inv.s.profile['max_read_chars']) for b in blocks)
        entry.update(serialized_chars=serialized,input_allowance_chars=allowance,estimated_read_calls_upper=estimated,
            read_complete=False,delivered=False)
        from .unit_reading import POLICY
        available=min(available,POLICY['read_actions']-inv.p['read_state'].get('count',0))
        remaining_chars=POLICY['initial_chars']-inv.p['read_state'].get('chars',0)
        if serialized>allowance or estimated>available or sum(len(b['text']) for b in blocks)>remaining_chars:
            entry.update(status='OUTLINE_ONLY',reason='전문이 남은 입력/읽기 예산을 넘습니다. 목차에서 필요한 범위를 선택합니다.');inv.save();continue
        nodes=[src.resolve(item['node'],'U') for item in entry['structure']]
        # Maximal structural intervals cover headings/addenda without overlapping child rereads.
        bounds=sorted([(src.matcher.units[(did,str(n['unit_id']))]['span'],n) for n in nodes],key=lambda x:(x[0][0],-x[0][1]))
        covered=[]
        for span,node in bounds:
            if any(a<=span[0] and span[1]<=b for a,b in covered):continue
            saved=read_node(did,str(node['unit_id']));covered.append(span)
            key=digest([did,str(node['unit_id']),None])
            if key not in entry['read_keys']:entry['read_keys'].append(key)
            if saved['status']!='COMPLETE':break
        # Orphan blocks still belong to their canonical source, not invented structural nodes.
        read_spans={(str(s['block_id']),s['start_cp'],s['end_cp']) for e in inv.s.repo.evidence() if e['document_id']==did for s in e['spans']}
        missing=[b for b in blocks if b['text'] and not any(b['block_id']==k[0] and k[1]==0 and k[2]==len(b['text']) for k in read_spans)]
        for b in missing:
            row=src.store.source(did,str(b['block_id']));ids=src.matcher._unit_sources(did,str(row['unit_id']))
            for sid in ids:
                if str(b['block_id']) in {str(x['block_id']) for x in src.tools.sources[sid]['blocks']}:read_node(did,None,sid)
        spans=[s for e in inv.s.repo.evidence() if e['document_id']==did for s in e['spans']]
        def complete(b):
            intervals=sorted((s['start_cp'],s['end_cp']) for s in spans if str(s['block_id'])==str(b['block_id']))
            end=0
            for a,z in intervals:
                if a>end:return False
                end=max(end,z)
            return end>=len(b['text'])
        entry['missing_blocks']=[b['block_id'] for b in blocks if not complete(b)]
        entry['read_complete']=not entry['missing_blocks'];entry['status']='COMPLETE' if entry['read_complete'] else 'PARTIAL';inv.save()
    # One automatic reference hop from preferred documents; subsequent hops belong to parent tasks.
    from ..term_references import reference_targets
    from .repository import text_hash
    from ..comparison_research_bridge import document_names
    from ..folder_navigation import normalized
    initial=[e for e in inv.s.repo.evidence() if e['document_id'] in preferred]
    for evidence in initial:
        for raw, in src.tools.db.execute('SELECT r.json FROM reference r JOIN reference_end x ON x.reference_id=r.id WHERE x.source_id=? ORDER BY r.id',(evidence['source_id'],)):
            ref=json.loads(raw);witness=ref.get('source_text')
            if ref['source_id']!=evidence['source_id'] or not witness or not any(witness in s['text'] for s in evidence['spans']):continue
            if text_hash(witness)!=ref.get('source_text_sha256'):raise ContractError('reference witness changed')
            if ref['id'] in state['references']:continue
            record={'reference_id':ref['id'],'origin_evidence_id':evidence['evidence_id'],'witness_hash':text_hash(witness),
                'document_name_hint':ref.get('document_name_hint'),'coordinate':ref.get('locator'),'targets':[],'status':'UNRESOLVED','absence_proven':False}
            targets=reference_targets(ref) if str(ref.get('resolution','')).startswith('EXACT_') else []
            record['resolution_path']='EXISTING_REFERENCE' if targets else 'WITNESSED_TITLE_COORDINATE'
            if targets:
                for target in targets:
                    source=src.tools.sources.get(target.get('source_id'))
                    if not source or source['document_id'] not in inv.s.scope:
                        record.setdefault('unresolved',[]).append('기존 참조 대상은 현재 자식의 허용 범위 밖입니다. 부모의 해당 범위 조사가 필요합니다.');continue
                    result=read_node(source['document_id'],target.get('unit_id') or source['unit_id'],target['source_id']);record['targets'].append(deepcopy(result))
            elif ref.get('document_name_hint') and ref.get('locator'):
                name=normalized(ref['document_name_hint'])
                candidates=[d for d in inv.s.scope if name in {normalized(n) for n in document_names(src,d)}]
                record['candidate_document_ids']=candidates
                if len(candidates)==1:
                    page=call('locate_provision',{'document':src.handle('D',candidates[0]),'coordinate':ref['locator'],'cursor':None})
                    record['lookup_status']=page['status']
                    if page['status']=='OK' and len(page.get('items',[]))==1 and not page.get('next_cursor'):
                        node=src.resolve(page['items'][0]['node'],'U');record['targets'].append(deepcopy(read_node(node['document_id'],node['unit_id'],node.get('source_id'))))
                else:record['lookup_status']='DOCUMENT_NOT_IN_ALLOWED_SELECTION' if not candidates else 'AMBIGUOUS_DOCUMENT'
            record['status']='COMPLETE' if record['targets'] and all(t['status']=='COMPLETE' for t in record['targets']) and not record.get('unresolved') else 'UNRESOLVED'
            state['references'][ref['id']]=record;inv.save()
    inv.s.repo.event('COMPARISON_PREFERRED_ACQUIRED',deepcopy(state));inv.save()
