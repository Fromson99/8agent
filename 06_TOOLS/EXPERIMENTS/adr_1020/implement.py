from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate']
D=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=D/name;t=p.read_text();assert t.count(old)==1,(name,t.count(old));p.write_text(t.replace(old,new))
edit('connection_scope.py',"selected = current(inv)\n    selected_id", "selected = current(inv, allow_acquired_change=True)\n    selected_id")
edit('connection_scope.py',"inline = result['status'] == 'COMPLETE' and endpoint_count <= INLINE_CONNECTION_LIMIT", "inline = result['status'] == 'COMPLETE'")
edit('connection_scope.py',"visible = visible_connections(result, INLINE_CONNECTION_LIMIT, inv.policy.get('delegation_frontier',False))", "visible = visible_connections(result, endpoint_count, inv.policy.get('delegation_frontier',False))")
edit('connection_scope.py',"references['inline_connection_limit'] = INLINE_CONNECTION_LIMIT", "references['inline_connection_limit'] = None  # Every verified endpoint, within the existing context bound.")
edit('connection_scope.py',"references['omitted_dependency_cards'] = sum(max(0,\n        len({endpoint_key(g,c) for g in p['groups'] for c in g['connections']})-INLINE_CONNECTION_LIMIT)\n        for p in previews.values())", "references['omitted_dependency_cards'] = 0")
edit('connection_scope.py',"'선택한 범위의 연결 읽기 대상을 최대 5개씩 dependency_cards에 제시한다. '", "'선택한 범위에서 조회한 모든 연결 읽기 대상을 dependency_cards에 제시한다. '")
edit('connection_scope.py',"max_connections=None if inv.policy.get('delegation_frontier') else INLINE_CONNECTION_LIMIT+1", "max_connections=None")
edit('connection_scope.py',"if len(additional)<rel.LIMITS['witnesses_per_group']-1:", "if True:  # All verified witnesses; total context limits still apply.")
edit('connection_scope.py',"value = current(inv)\n    result = value.get", "value = current(inv, allow_acquired_change=True)\n    result = value.get")
# All groups are handed directly to parent selection. No target is automatically followed or skipped.
edit('law_navigation.py',"""                    nav = rel.navigate(self.question, self.s, selected, self.invoke, read_state=self.p['read_state'],
                        seconds_left=self.left, max_context_chars=self.s.profile['max_context_chars'],
                        state=self.p['reference_state'], on_checkpoint=reference_checkpoint,
                        phase_prefix='source-reference-law-'+str(self.p['turn'])+'-', max_model_batches=1,
                        context_reads=all_reads,
                        replay_menu={'data':replay['data'],'offered':replay['offered']} if replay else None)""", """                    if scope_choice:
                        directory = cs.preview(self, scope_choice['scope'])
                        # A selected scope opens a directory, not a second model
                        # decision. The next parent action chooses READ or FINISH.
                        nav = {'contract':'batch-reference-navigation-v2',
                            'reading_policy_revision':rel.REVISION,
                            'batches':[{'data':{'groups':[{'id':g['id']} for g in directory['groups']]},
                                        'decision':None, 'model_called':False}],
                            'actions':[], 'seen_target_ids':[], 'limits':directory.get('limits',[]),
                            'unresolved':directory.get('unresolved',[]),
                            'pending':directory['status']!='COMPLETE',
                            'scanned_anchors':[m['source_id'] for m in scope_choice['scope']['members']],
                            'state':self.p['reference_state'], 'pending_group_keys':[],
                            'diagnostics':{'directory_status':directory['status'], 'model_batches':0}}
                        self.s.repo.event('REFERENCE_DIRECTORY_OPENED',{
                            'scope_id':scope_choice['scope']['id'],'groups':len(directory['groups']),
                            'status':directory['status'],'model_called':False,'absence_proven':False})
                    else:
                        nav = rel.navigate(self.question, self.s, selected, self.invoke, read_state=self.p['read_state'],
                            seconds_left=self.left, max_context_chars=self.s.profile['max_context_chars'],
                            state=self.p['reference_state'], on_checkpoint=reference_checkpoint,
                            phase_prefix='source-reference-law-'+str(self.p['turn'])+'-', max_model_batches=1,
                            context_reads=all_reads,
                            replay_menu={'data':replay['data'],'offered':replay['offered']} if replay else None)""")
# Typed output termination metadata survives both adapter and gateway decoding.
edit('gateway.py',"""            except ProposalError as exc:
                self.repo.finish_attempt(ident, 'FAILED', getattr(exc, 'response', None),""", """            except ProposalError as exc:
                failed_response = getattr(exc, 'response', None)
                failed_body = failed_response.get('body', failed_response) if isinstance(failed_response, dict) else {}
                if _response_diagnostics(failed_body).get('finish_reason') == 'length':
                    exc.generation_failure = 'OUTPUT_LENGTH_LIMIT'
                self.repo.finish_attempt(ident, 'FAILED', getattr(exc, 'response', None),""")
edit('gateway.py',"""            except (ProposalError, ValidationError) as exc:
                repair_scheduled =""", """            except (ProposalError, ValidationError) as exc:
                if _response_diagnostics(body).get('finish_reason') == 'length':
                    exc.generation_failure = 'OUTPUT_LENGTH_LIMIT'
                repair_scheduled =""")
edit('gateway.py',"""                    error.format_error = True
                    raise error from exc""", """                    error.format_error = True
                    if hasattr(exc, 'generation_failure'):
                        error.generation_failure = exc.generation_failure
                    raise error from exc""")
# Existing strict source-only output contract; no partially decoded legal claim is promoted.
edit('completion_execution.py',"if profile.get('candidate_navigation',{}).get('bounded_judgment_notes'):\n            schema=bounded_judgment_notes(schema)","if modern or profile.get('candidate_navigation',{}).get('bounded_judgment_notes'):\n            schema=bounded_judgment_notes(schema)")
edit('completion_execution.py',"if profile.get('candidate_navigation',{}).get('bounded_judgment_notes') else '')", "if modern or profile.get('candidate_navigation',{}).get('bounded_judgment_notes') else '')")
edit('completion_execution.py',"""                if not cached:decision_journal.reject(attempt,exc,value)
                self.s.work.event('COMPLETION_ASSESSMENT_REJECTED', {""", """                truncated = modern and getattr(exc, 'generation_failure', None) == 'OUTPUT_LENGTH_LIMIT'
                if not cached:decision_journal.reject(attempt,exc,value,can_retry=False if truncated else None)
                self.s.work.event('COMPLETION_ASSESSMENT_REJECTED', {""")
edit('completion_execution.py',"""                if not attempt and output.repairable(exc):
                    feedback =""", """                if truncated and options:
                    # Failed generation stays REJECTED. This is a separate host
                    # source-delivery outcome, with no inferred legal judgment.
                    result = {'claims':[], 'gaps':[], 'disposition':'LIMITED_ANSWER',
                        'issue_assessments':[{'issue_id':i['id'], 'status':'INSUFFICIENT',
                            'reason':'원문은 확보했으나 답변 검토가 출력 한도에서 끝나 완료하지 못했습니다.'}
                            for i in self.issues],
                        'completion_contract':contract,
                        'model_proposal':{'review_status':'INCOMPLETE',
                            'failure_code':'OUTPUT_LENGTH_LIMIT', 'decision_key':decision_journal.key}}
                    self.s.work.event('ASSESSMENT_GENERATION_STOPPED',{
                        'cause_code':'OUTPUT_LENGTH_LIMIT','attempt':attempt,
                        'decision_key':decision_journal.key,'legal_conclusion_confirmed':False,
                        'source_ids':[s['source_id'] for s in sources], 'retry':False})
                    normalized=True
                    break
                if not attempt and output.repairable(exc) and not truncated:
                    feedback =""")
edit('completion_execution.py',"""        stop_reason = selection.get('stop_reason')
        if fresh:""", """        stop_reason = ('ASSESSMENT_OUTPUT_LIMIT' if result.get('model_proposal',{}).get('failure_code')=='OUTPUT_LENGTH_LIMIT'
                       else selection.get('stop_reason'))
        if fresh:""")
edit('completion_contracts.py',"""    if stop_reason and not items:
        items.append({'id': 'L-stop', 'kind': 'EXECUTION_LIMIT', 'issue_id': None,
                      'text': '확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.'})""", """    if stop_reason == 'ASSESSMENT_OUTPUT_LIMIT':
        items.append({'id':'L-review-incomplete', 'kind':'EXECUTION_LIMIT', 'issue_id':None,
            'text':'원문은 확보했으나 답변 검토가 출력 한도에서 끝나 완료하지 못했습니다. 아래 원문은 확정된 법률 판단이 아닙니다.'})
    elif stop_reason and not items:
        items.append({'id': 'L-stop', 'kind': 'EXECUTION_LIMIT', 'issue_id': None,
                      'text': '확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.'})""")
edit('completion_contracts.py',"""    blocks = ['확보한 자료만으로 질문의 결론을 확정하기는 어렵습니다. '
              '확인한 원문과 아직 확인하지 못한 범위를 정리합니다.']""", """    blocks = (['원문은 확보했으나 답변 검토를 완료하지 못했습니다. 확인한 원문을 제공합니다.']
              if assessment.get('stop_reason') == 'ASSESSMENT_OUTPUT_LIMIT' else
              ['확보한 자료만으로 질문의 결론을 확정하기는 어렵습니다. 확인한 원문과 아직 확인하지 못한 범위를 정리합니다.'])""")
print('Changed candidate modules only')
