from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate'];B=C/'02_BACKEND/semantic_runtime/legal_agent'
def change(name,old,new):
 p=B/name;s=p.read_text();assert old in s,(name,old[:80]);p.write_text(s.replace(old,new,1))
change('law_candidates.py',"'definition_entry': False, 'answer_first': False}","'definition_entry': False, 'answer_first': False, 'selected_connection_scope': False}")
change('law_candidates.py',"'compact_input','definition_entry','answer_first')):","'compact_input','definition_entry','answer_first','selected_connection_scope')):")
change('law_candidates.py',"    if result['answer_first'] and not result['compact_input']:","    if result['selected_connection_scope'] and (not result['compact_input'] or result['answer_first']):\n        raise ContractError('selected connection scope requires navigation judgment before assessment')\n    if result['answer_first'] and not result['compact_input']:")
p=C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=read(p);v['candidate_navigation'].update(selected_connection_scope=True,answer_first=False);save(p,v)
change('connected_exploration.py',"    records = inv.read_records()\n    known =", "    from . import connection_scope as cs\n    if cs.enabled(inv):\n        selected = cs.current(inv)\n        return [r['source_id'] for r in selected['scope']['members']] if selected else []\n    records = inv.read_records()\n    known =")
change('connected_exploration.py',"    docs = [r['document_id'] for r in inv.read_records().values()]", "    from . import connection_scope as cs\n    focus = cs.current(inv) if cs.enabled(inv) else None\n    # A speculative definition read no longer starts document-body expansion.\n    docs = ([r['document_id'] for r in focus['scope']['members']] if focus else []\n            ) if cs.enabled(inv) else [r['document_id'] for r in inv.read_records().values()]")
change('law_navigation.py',"    def reference_overview(self, current_pages=()):\n        self.bind_reference_delivery", "    def reference_overview(self, current_pages=()):\n        from . import connection_scope as cs\n        if cs.enabled(self):\n            # The existing FOLLOW_CONNECTION menu is opened only after a model\n            # selects one exact scope. Do not precompute every acquired anchor.\n            return cs.overview(self)\n        self.bind_reference_delivery")
change('law_navigation.py',"        if (self.read_records() and reference_signature not in self.p.get('reference_attempts',[])","        if (not self.policy.get('selected_connection_scope') and self.read_records() and reference_signature not in self.p.get('reference_attempts',[])")
change('law_navigation.py',"            rr.annotate_reused_reads(self,data,actions)\n            rr.recovery_menu", "            rr.annotate_reused_reads(self,data,actions)\n            from .connection_scope import offer_choices\n            offer_choices(self,data,actions)\n            rr.recovery_menu")
old="""            from .connected_exploration import anchors
            focused=set(anchors(self)) if self.modern else {g['source_id'] for gid,g in self.p['groups'].items() if gid in self.p.get('window_groups',[])}
            if replay:focused={g['anchor']['source_id'] for g in replay['offered'].values()}
            all_reads=self.read_records()
            selected={k:r for k,r in all_reads.items() if r['source_id'] in focused}
            if not selected:selected=self.active_records() or all_reads
            reference_key=digest(sorted(focused))"""
new="""            from .connected_exploration import anchors
            from . import connection_scope as cs
            scope_choice = None
            if cs.enabled(self):
                if replay:
                    # Replay uses the immutable scope originally selected for
                    # that reference frame, never the current cumulative reads.
                    scope = replay['data'].get('selected_connection_scope')
                    if not scope:raise ContractError('reference replay lacks selected structural scope')
                    scope_choice = cs.accept(self,scope,data,decision['reason'])
                else:
                    scope_choice = cs.accept(self,identity.get('connection_scope',{}),data,decision['reason'])
            focused=set(anchors(self)) if self.modern else {g['source_id'] for gid,g in self.p['groups'].items() if gid in self.p.get('window_groups',[])}
            if replay and not scope_choice:focused={g['anchor']['source_id'] for g in replay['offered'].values()}
            all_reads=self.read_records()
            selected={k:r for k,r in all_reads.items() if r['source_id'] in focused}
            if not selected:
                if scope_choice:raise ContractError('selected connection scope has no acquired original')
                selected=self.active_records() or all_reads
            reference_key=digest(scope_choice['scope']) if scope_choice else digest(sorted(focused))"""
change('law_navigation.py',old,new)
old="""            nav = rel.navigate(self.question, self.s, selected, self.invoke, read_state=self.p['read_state'],
                seconds_left=self.left, max_context_chars=self.s.profile['max_context_chars'],
                state=self.p['reference_state'], on_checkpoint=reference_checkpoint,
                phase_prefix='source-reference-law-'+str(self.p['turn'])+'-', max_model_batches=1,
                replay_menu={'data':replay['data'],'offered':replay['offered']} if replay else None)"""
new="""            from contextlib import nullcontext
            with cs.bound(self.s,scope_choice['scope']) if scope_choice else nullcontext():
                try:
                    nav = rel.navigate(self.question, self.s, selected, self.invoke, read_state=self.p['read_state'],
                        seconds_left=self.left, max_context_chars=self.s.profile['max_context_chars'],
                        state=self.p['reference_state'], on_checkpoint=reference_checkpoint,
                        phase_prefix='source-reference-law-'+str(self.p['turn'])+'-', max_model_batches=1,
                        replay_menu={'data':replay['data'],'offered':replay['offered']} if replay else None)
                except Exception:
                    if scope_choice:
                        scope_choice['status']='INTERRUPTED';self.save()
                    raise  # Existing request_repair alone classifies and recovers.
            if scope_choice:
                scope_choice['status']='COMPLETE' if any(b['data'].get('groups') for b in nav['batches']) else 'NO_VERIFIED_LINKS_IN_SELECTED_SCOPE_AND_INDEX'
                self.s.repo.event('CONNECTION_SCOPE_RESULT',{'scope_id':scope_choice['scope']['id'],
                    'status':scope_choice['status'],'absence_proven':False,'fallback':'SEARCH_STRUCTURE'})
                self.save()"""
change('law_navigation.py',old,new)
# Attach selected scope to immutable reference frames and pass scope context to the relation model.
change('law_navigation.py',"    def reference_menu(self, data, offered):\n        f=", "    def reference_menu(self, data, offered):\n        from . import connection_scope as cs\n        selected=cs.current(self) if cs.enabled(self) else None\n        if selected:data={**data,'selected_connection_scope':deepcopy(selected['scope'])}\n        f=")
# Relation catalog intersects actual witness spans with the exact chosen frontier.
change('unit_relations.py',"        evidence_blocks = delivered_blocks(s,evidence_spans)\n    for anchor", "        evidence_blocks = delivered_blocks(s,evidence_spans)\n    scoped = getattr(s,'connection_scope_spans',None)\n    if scoped is not None:\n        evidence_spans = scoped\n        evidence_blocks = delivered_blocks(s,scoped)\n        if set(anchors)-set(scoped):raise ContractError('reference anchor escaped selected structure scope')\n    for anchor")
change('unit_relations.py',"        found = 0\n        after=", "        found = 0; broader_incoming = 0\n        after=")
change('unit_relations.py',"                touching = [e for e in reference_targets(ref) if e.get('source_id') == anchor]\n                if touching", "                touching = [e for e in reference_targets(ref) if e.get('source_id') == anchor]\n                if scoped is not None:\n                    anchor_blocks={str(b['block_id']) for b in s.tools.sources[anchor]['blocks']}\n                    if touching and all(not e.get('block_ids') for e in touching) and not anchor_blocks <= evidence_blocks.get(anchor,set()):\n                        broader_incoming += 1\n                        continue  # An article-only reverse link is not a precise child-scope link.\n                if touching")
change('unit_relations.py',"            'verified_connections': found, 'scan_complete'", "            'verified_connections': found, 'broader_incoming_not_in_selected_scope': broader_incoming, 'scan_complete'")
# Native failure feedback was absent from compact projection; keep typed outcome.
change('decision_projection.py',"        row['reference_anchors']=deepcopy(data.get('references',{}).get('current_anchors',[]))", "        row['reference_anchors']=deepcopy(data.get('references',{}).get('current_anchors',[]))\n        if identity.get('connection_scope'):\n            scope=identity['connection_scope']\n            row['selected_scope']={k:deepcopy(scope[k]) for k in ('id','label','structural_selection')}\n            row['reference_anchors']=[{'source_id':m['source_id'],'document_id':m['document_id'],\n                'block_ids':sorted({p['block_id'] for p in m['spans']})} for m in scope['members']]")
change('decision_projection.py',"        'references':data.get('references',{}),'document_term_candidates':data.get('document_term_candidates'),", "        'references':data.get('references',{}),'document_term_candidates':data.get('document_term_candidates'),\n        'connection_scope_choices':deepcopy(data.get('connection_scope_choices',[])),\n        'connection_scope_rule':data.get('connection_scope_rule'),\n        'tool_recovery':deepcopy(data.get('tool_recovery',[])),\n        'lookup_recovery':deepcopy(data.get('lookup_recovery')),\n        'tool_recovery_rule':data.get('tool_recovery_rule'),")
change('decision_projection.py',"        try:return inv.invoke(EXECUTABLE_CHOICE_PROMPT+'\\n'+name_recovery_prompt", """        scope_prompt = ('\\nconnection_scope_choices가 있으면 현재 원문이 요청에 어떤 도움을 주는지 판단하고, '
            '필요한 조건·준용·위임을 확인할 때 그 정확한 구조 범위의 FOLLOW_CONNECTION을 먼저 고른다. '
            '편·장·절·관·조·항·호·목과 복수·제외 선택 모두 동일하며 상위 문맥과 다른 읽은 원문은 합치지 않는다. '
            '연결이 없거나 일부만 확인되거나 실패했으면 필요한 원문이 없다고 하지 않는다. '
            '필요한 법령명·좌표를 알면 LOCATE/CATALOG_SEARCH → READ로 계속한다. '
            '실패한 같은 연결 조회를 반복하지 않는다. 원문을 읽은 다음에는 그 내용으로 다시 다음 행동을 판단한다.'
            if inv.policy.get('selected_connection_scope') else '')\n        try:return inv.invoke(EXECUTABLE_CHOICE_PROMPT+scope_prompt+'\\n'+name_recovery_prompt""")
# Record the diagnosed scope failure without converting integrity failures to success.
change('request_repair.py',"    investigation.p.setdefault('tool_failures', []).append(row)", "    investigation.p.setdefault('tool_failures', []).append(row)\n    if kind=='FOLLOW_CONNECTION' and investigation.p.get('selected_connection_scope'):\n        investigation.p['selected_connection_scope']['status']='FAILED'\n        investigation.p['selected_connection_scope']['failure']={k:row[k] for k in ('code','status','absence_proven')}")
# Dependencies: every existing engine that consumes connected_exploration also binds the new scope module.
new_path='02_BACKEND/semantic_runtime/legal_agent/connection_scope.py'
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if '02_BACKEND/semantic_runtime/legal_agent/connected_exploration.py' in v.get('files',{}):
  v['files'][new_path]=sha(C/new_path);save(p,v)
print('Candidate implementation written; not frozen or executed yet')
