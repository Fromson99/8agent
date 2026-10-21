from pathlib import Path
S=Path('02_BACKEND/lawrag/research/candidates/adr_0876/scoped/snapshot')
p=S/'02_BACKEND/workflow/presentation.py';s=p.read_text();pos=s.index('\ndef compact_results')
s=s[:pos]+'''
def source_context(ctx, state, ids, issue_id):
    """Keep active originals from the exact selected source, not model adoption.

    Identity, side and issue boundaries are preserved. Selection does not fetch
    another document, restore an inactive bundle or invent a semantic relation.
    """
    selected=evidence(ctx,state,ids)
    roots={(e['side'],e['document_id'],e['source_id']) for e in selected}
    return set(ids)|{e['evidence_id'] for e in evidence(ctx,state)
        if (e['side'],e['document_id'],e['source_id']) in roots
        and (not e['parent_issue_refs'] or issue_id in e['parent_issue_refs'])}

''' + s[pos:]
s=s.replace("'budget':ctx.repo.work.budget(),'deadline_at':ctx.context.deadline_at}","'budget':ctx.repo.work.budget(),'deadline_at':ctx.context.deadline_at,\n        **state.get('_presentation_extra',{})}")
s=s.replace('def packets(ctx,state,stage,*,ids=None,basis=None):','def packets(ctx,state,stage,*,ids=None,basis=None,extra=None):')
s=s.replace("local={**state, **({'basis':basis} if basis is not None else {})}","local={**state, **({'basis':basis} if basis is not None else {}), '_presentation_extra':extra or {}}")
p.write_text(s)
p=S/'02_BACKEND/workflow/risk_team_compare_workflow/basis.py';s=p.read_text();s=s.replace('from ..presentation import evidence\n    from ..contracts import digest','from ..presentation import evidence,source_context\n    from ..contracts import digest')
s=s.replace('sources=evidence(ctx,state,ids=ids);by=evidence_map(sources);pairs=[];gaps=[]','sources=evidence(ctx,state);by=evidence_map(sources);pairs=[];gaps=[]')
s=s.replace("**{side:list(dict.fromkeys(c['evidence'] for c in selected[side])) for side in selected},","**{side:sorted(source_context(ctx,state,{c['evidence'] for c in selected[side]},issue['id'])) for side in selected},")
p.write_text(s)
p=S/'02_BACKEND/workflow/risk_team_compare_workflow/compare.py';s=p.read_text()
s=s.replace("binding=digest([basis,state['scope'],", "field_reviews=[{'issue_id':r['issue_id'],'field':r['field'],'observation':r['current']}\n                   for r in state.get('task_board',{}).get('rows',{}).values() if r.get('current')]\n    binding=digest([basis,state['scope'],field_reviews,")
s=s.replace("for data,evidence in packets(ctx,state,'COMPARE:'+pair['pair_id'],ids=ids,basis=one):", "focus={'issue':next(i for i in state['scope']['issues'] if i['id']==pair['issue_id']),\n               'field_reviews':[r for r in field_reviews if r['issue_id']==pair['issue_id']]}\n        for data,evidence in packets(ctx,state,'COMPARE:'+pair['pair_id'],ids=ids,basis=one,extra={'comparison_focus':focus}):")
s=s.replace("'양쪽 원문을 비교해 사용자가 검토할 수 있는 판단과 이유를 작성하라. '","'comparison_focus.issue의 요청 항목을 양쪽 원문으로 비교하라. item은 그 쟁점을 유지하며, 도입부의 설치·정의 설명으로 다른 요청 항목을 대신하지 않는다. '\n                        'field_reviews와 gaps는 이전 의견이다. 현재 sources에 이미 확보된 내용이면 미확보 의견을 바로잡고 그 원문을 직접 검토한다. '\n                        '단서·예외가 수식하는 주체·행위·항·호를 구분하라. 일부 항목에만 붙은 제한을 조 전체나 다른 항목에 확대하지 않는다. 적용 사실 미확인은 조건부 설명으로 남긴다. '")
p.write_text(s)
p=S/'02_BACKEND/workflow/risk_team_compare_workflow/task_board.py';s=p.read_text();s=s.replace("'이전 확인은 previous에 있다. 문장 표현만 달라진 것은 충돌이 아니다.","'단서·예외가 한정하는 정확한 항목과 그 밖의 항목을 나누어 판단한다. 일부 항목의 주체 제한을 조문 전체로 확대하지 않는다. '\n                '이전 확인은 previous에 있다. 현재 sources에서 확보된 원문은 이전 missing보다 우선하며, 이미 확보된 내용을 다시 미확보로 옮기지 않는다. 문장 표현만 달라진 것은 충돌이 아니다.")
p.write_text(s)
p=S/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';s=p.read_text()
s=s.replace("if value.get('control_contract'):\n", "value['reading_progress']={\n            'offered_read_actions':sum(a['action'] in ('READ_ARTICLES','READ_PARENT','READ_SCOPE') for a in data.get('actions',[])),\n            'presented_original_pages':len(data.get('sources',[])),\n            'saved_original_ranges':len(data.get('saved_inventory',[])),\n            'candidate_is_original':False,'unread_is_absent':False}\n        if value.get('control_contract'):\n",1)
s=s.replace("from . import investigation_scope\n        if investigation_scope.enabled", "system+='\\nreading_progress는 시스템이 센 현재 읽기 선택지와 전달 원문 수다. 후보를 아직 읽지 않았다는 사실은 그 원문의 부재나 조사 종료 이유가 아니다. 질문에 필요한 후보의 read_action이 있으면 먼저 읽는다. PENDING을 고르면 남은 후보가 필요한 내용을 확인하는 데 도움이 안 되는 구체 이유 또는 실행 한계를 reason에 짧게 남긴다. 후보 전체 순회나 억지 채택은 필요 없다. 단서가 한정하는 항·호의 범위는 다른 항목에 확대하지 않는다.'\n        from . import investigation_scope\n        if investigation_scope.enabled")
s=s.replace("if decision['next_action'] == 'PENDING' and self.completion:\n", "if decision['next_action'] == 'PENDING' and self.completion:\n                self.s.repo.event('INVESTIGATION_PENDING_READING',{'presentation_id':data['presentation_id'],\n                    'reading_progress':self.model_view(data)['reading_progress'],\n                    'reason':decision['reason'],'absence_proven':False,'forced_retry':False})\n")
p.write_text(s)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
print('Scoped original closure, bounded issue focus, current-source precedence, precise proviso scope and navigation inventory patched in isolated candidate')
