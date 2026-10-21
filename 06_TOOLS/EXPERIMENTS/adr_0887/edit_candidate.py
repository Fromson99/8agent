from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0887/retained/snapshot/02_BACKEND/semantic_runtime/legal_agent'
def change(name,old,new):
 p=C/name;s=p.read_text();assert old in s,(name,old[:60]);p.write_text(s.replace(old,new))
change('decision_projection.py',"and state['groups'][b['branch_id']]['status'] not in ('DEFERRED','EXCLUDED')", "and state['groups'][b['branch_id']]['status'] != 'EXCLUDED'")
change('decision_projection.py',"'previous_searches':deepcopy(inv.p.get('query_surface_history',[])),", "'previous_searches':deepcopy(inv.p.get('query_surface_history',[])),\n        'previous_choices':deepcopy(inv.p.get('executed_compact_choices',[])[-8:]),")
change('decision_projection.py',"decision=expand(value)\n    inv.s.repo.event", "decision=expand(value)\n    inv.p.setdefault('executed_compact_choices',[]).append(deepcopy(value))\n    inv.save()\n    inv.s.repo.event")
change('decision_projection.py','FINISH는 필요한 내용을 실제 sources에서 확인한 경우다.', '연결 메뉴는 원하는 이름의 조문이 있다는 보장이 없다. previous_choices와 현재 원문을 대조하여 같은 missing_need로 연결 메뉴를 반복했는데 대상이 없으면 CATALOG_SEARCH로 정식 법령명·조문번호를 찾고 LOCATE/READ로 읽는다. 약칭인 법·영·규칙의 실제 이름은 해당 문서의 정의나 제공된 catalogue로 확인한다. 제목을 추측해 번호와 동시에 필터링하지 않는다. 번호를 알면 title은 빈 문자열로 조회한다.\nFINISH는 필요한 내용을 실제 sources에서 확인한 경우다.')
# Exact cached decisions survive changing the focus window. Conflicts are never resolved by the host.
p=C/'decision_projection.py';s=p.read_text();s+='''\n\ndef shared_reference_decisions(states,current,binding):\n    """Reuse closed identical signatures only; current/replay choices take precedence."""\n    from .errors import ContractError\n    if current.get('binding') not in (None,binding):raise ContractError('reference decision binding changed')\n    values={};conflicts=set()\n    for state in states.values():\n        if state is current or state.get('binding')!=binding:continue\n        for key,value in state.get('decisions',{}).items():\n            if value.get('action') not in ('SKIP','FOLLOW'):continue\n            if key in values and values[key]!=value:conflicts.add(key)\n            else:values[key]=value\n    own=current.setdefault('decisions',{});added=[]\n    for key,value in values.items():\n        if key in conflicts or key in own:continue\n        own[key]=deepcopy(value);added.append(key)\n    return added\n''';p.write_text(s)
change('evidence_inventory.py','def originals_for(session, state, selected_refs=()):','def originals_for(session, state, selected_refs=(), *, context_refs=()):')
old="    return _pack(session, state, sources, gathered)\n\n\ndef delivered_originals_for"
new="""    explicit_sources=set(sources)
    for ref in dict.fromkeys(context_refs):
        page=state['basis_history'].get(ref)
        if not page or not page.get('accepted') or not page.get('spans'):
            raise ContractError('context original lacks an accepted delivery receipt')
        gid=page['branch_id'];group=state['groups'][gid]
        if gid not in state['selected'] or group['status']=='EXCLUDED':
            raise ContractError('context selected an excluded or missing original')
        record=state['selected'][gid]
        check_page(session,state,{**page,'document_id':record['document_id']},current_scope=False)
        gathered[group['source_id']].extend(page['spans']);sources[group['source_id']]=record
    result=_pack(session,state,sources,gathered)
    for original in result:
        original['delivered_context_only']=original['source_id'] not in explicit_sources
    return result


def delivered_originals_for"""
change('evidence_inventory.py',old,new)
change('law_navigation.py',"if any(updates.get(g) in ('DEFER','EXCLUDE') or (g not in updates and self.p['groups'][g]['status'] in ('DEFERRED','EXCLUDED')) for g in explicit):\n                    raise ProposalError('FINISH selects an explicitly deferred or excluded original')", "if any(updates.get(g)=='EXCLUDE' or (g not in updates and self.p['groups'][g]['status']=='EXCLUDED') for g in explicit):\n                    raise ProposalError('FINISH selects an explicitly excluded original')")
change('law_navigation.py',"self.p['reference_state']=self.p.setdefault('reference_states',{}).setdefault(reference_key,{})", """self.p['reference_state']=self.p.setdefault('reference_states',{}).setdefault(reference_key,{})
            if self.modern:
                from .decision_projection import shared_reference_decisions
                binding=digest({'question':self.question,'scope':sorted(self.s.scope),'generation':self.s.context.query['generation_id']})
                reused=shared_reference_decisions(self.p['reference_states'],self.p['reference_state'],binding)
                if reused:self.s.repo.event('REFERENCE_CLOSED_CHOICES_SHARED',{'signatures':reused,'binding':binding})""")
change('law_navigation.py',"current=inventory.originals_for(self.s,self.p,list(dict.fromkeys(mandatory+delivered_refs)))", "current=inventory.originals_for(self.s,self.p,context_refs=list(dict.fromkeys(mandatory+delivered_refs))) if self.modern else inventory.originals_for(self.s,self.p,mandatory)")
change('law_navigation.py',"if self.modern and self.p.get('completion_basis_refs') and sufficient:\n                selected_ids", "if self.modern and current and sufficient:\n                selected_ids")
change('law_navigation.py',"fallback=[] if current or not self.control else inventory.delivered_originals_for(self.s,self.p)", """if self.modern and not current:
            from .decision_projection import bounded_original_refs
            limit=max(self.s.profile['max_read_chars'],(self.s.profile.get('max_context_chars') or 100000)//2)
            refs,_=bounded_original_refs(self.p,[],limit)
            fallback=inventory.originals_for(self.s,self.p,context_refs=refs)
        else:fallback=[] if current or not self.control else inventory.delivered_originals_for(self.s,self.p)""")
print('Deferred exact context remains separate from adoption; repeated closed reference decisions reused with exact binding/signature validation')
