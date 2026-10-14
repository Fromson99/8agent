from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0723/integrated/snapshot';L=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=L/name;s=p.read_text();assert old in s,(name,old[:100]);p.write_text(s.replace(old,new))
edit('request_repair.py',"'expected': [], 'absence_proven': False}","'expected': [], 'absence_proven': False,\n              'document_candidates': sorted({d for h in sq.document_hits(target_text, session.matcher)\n                                             for d in h['values'] if d in session.scope})}")
edit('request_repair.py',"        result.append({'gap_id': gap['gap_id']", """        navigation = []
        # A known document can still have an unresolved coordinate or title.
        # Offer scoped tools without changing the model's requested target.
        for did in target.get('document_candidates', []):
            for kind in ('SEARCH_STRUCTURE', 'OPEN_STRUCTURE', 'SEARCH_BODY'):
                identity = {'document_id': did}
                if kind == 'SEARCH_BODY': identity['unit_id'] = None
                ident = lc.token(investigation.s, 'T', [kind, identity])
                actions.setdefault(ident, {'id': ident, 'action': kind, 'identity': identity,
                    'label': investigation.s.matcher.documents[did] + ' 부족 대상 확인: ' + kind})
                navigation.append(ident)
        result.append({'navigation_actions': navigation, 'gap_id': gap['gap_id']""")
edit('request_repair.py',"('READ_SCOPE', 'READ_PARENT', 'READ_ARTICLES'): continue", "('READ_SCOPE', 'READ_PARENT', 'READ_ARTICLES', 'VIEW_SAVED_SOURCE'): continue")
edit('request_repair.py',"group['offer'] if action['action'] == 'READ_PARENT' else next(","group['offer'] if action['action'] in ('READ_PARENT', 'VIEW_SAVED_SOURCE') else next(")
# One reference cannot imply that every original page of the same document covers a target.
edit('request_repair.py',"refs = [p['id'] for p in data['sources'] if p['document_id'] == did]", "refs = [p['id'] for p in data['sources'] if p['document_id'] == did\n                and any(str(s['block_id']) == str(w['block_id']) and s['start'] < w['end'] and w['start'] < s['end']\n                        for s in p['spans'] for w in wanted)]")
p=L/'request_repair.py';p.write_text(p.read_text()+'''


def operation_key(decision, actions):
    return digest({'kind': decision['next_action'],
                   'targets': [actions[t]['identity'] for t in decision['targets']],
                   'queries': decision.get('queries', []),
                   'structure_filter': decision.get('structure_filter')})


def recoverable_tool_failure(error):
    """Only known rejected actions and transient reads can choose another route.

    Hash/ACL/schema errors and unknown model transmission outcomes remain fatal.
    Inspect wrapped causes because relation tools preserve their original error.
    """
    import errno
    import sqlite3
    from .errors import BudgetExhausted, TransportError
    seen = set(); current = error; transient = False; rejected = False
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ContractError, BudgetExhausted, TransportError, PermissionError)):
            return None
        if isinstance(current, ProposalError): rejected = True
        if isinstance(current, TimeoutError): transient = True
        if isinstance(current, OSError) and current.errno in (errno.EAGAIN, errno.ETIMEDOUT, errno.ECONNRESET):
            transient = True
        if isinstance(current, sqlite3.OperationalError) and getattr(current, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            transient = True
        current = current.__cause__
    return 'ACTION_REJECTED' if rejected else 'SOURCE_TEMPORARILY_UNAVAILABLE' if transient else None


def record_tool_failure(investigation, decision, actions, step, error):
    code = recoverable_tool_failure(error)
    if code is None: return False
    row = {'operation_key': operation_key(decision, actions), 'code': code,
           'action': decision['next_action'], 'targets': deepcopy([actions[t]['identity'] for t in decision['targets']]),
           'queries': list(decision.get('queries', [])), 'step_id': step['id'],
           'status': 'UNRESOLVED', 'absence_proven': False}
    investigation.p.setdefault('tool_failures', []).append(row)
    investigation.p['no_progress'] += 1
    step.update(status='FAILED', outcome={'failure_code': code, 'absence_proven': False, 'changed': False})
    # Raw exceptions stay in the server journal; the model sees typed outcomes.
    investigation.s.repo.event('LAW_TOOL_RECOVERY', {**row, 'error_type': type(error).__name__, 'error': str(error)})
    return True


def recovery_menu(investigation, data, actions):
    failures = investigation.p.get('tool_failures', [])
    blocked = set()
    for ident, action in list(actions.items()):
        if action['action'] in ('SEARCH_BODY', 'SEARCH_STRUCTURE', 'RESEARCH'): continue
        if any(f['action'] == action['action'] and f['targets'] == [action['identity']] for f in failures):
            blocked.add(ident); del actions[ident]
    # Search handles stay usable with a changed expression; validate the exact
    # operation separately. Read/cursor handles cannot immediately repeat a failure.
    if failures:
        data['tool_recovery'] = [{k: f[k] for k in ('code', 'action', 'targets', 'queries', 'status', 'absence_proven')}
                                 for f in failures[-3:]]
        data['tool_recovery_rule'] = ('실패한 동일 요청은 반복하지 않는다. 허용된 다른 구조·범위 조회를 선택하거나 '
            '확인한 원문으로 판단하고 부족은 UNRESOLVED로 남긴다. 실패는 원문 부재 증명이 아니다.')
    lookup = data.get('structure', {})
    if not isinstance(lookup, dict): lookup = {}
    failure = lookup.get('failure') or investigation.p.get('structure_page', {}).get('failure')
    if failure:
        suggested = failure['suggested_action']
        equivalents = {'CHOOSE_VERSION': ('OPEN_STRUCTURE', 'SEARCH_STRUCTURE'),
                      'OPEN_STRUCTURE': ('OPEN_STRUCTURE', 'BROWSE_STRUCTURE'),
                      'SEARCH_STRUCTURE': ('SEARCH_STRUCTURE',), 'BROWSE_STRUCTURE': ('BROWSE_STRUCTURE',)}
        data['lookup_recovery'] = {'failure_code': failure['code'], 'absence_proven': False,
            'action_ids': [k for k, a in actions.items() if a['action'] in equivalents.get(suggested, ())],
            'automatic_fulltext_fallback': False}
    if blocked:
        def clean(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, str) and v in blocked and k.endswith('action'): value[k] = None
                    elif isinstance(v, list) and k.endswith('actions'): value[k] = [x for x in v if not isinstance(x, str) or x not in blocked]
                    elif isinstance(v, (dict, list)): clean(v)
            elif isinstance(value, list):
                for v in value: clean(v)
        clean(data)
    data['actions'] = [a for a in data['actions'] if a['id'] in actions]


def validate_failed_operation(investigation, decision, actions):
    if not decision.get('targets'): return
    key = operation_key(decision, actions)
    if any(f['operation_key'] == key for f in investigation.p.get('tool_failures', [])):
        raise ProposalError('same failed operation in this request; select a different offered target/query or leave UNRESOLVED')
''')
edit('law_navigation.py',"self.p.pop('request_progress',None)","self.p.pop('request_progress',None)\n                if self.p.get('tool_failures'):\n                    self.p.setdefault('prior_tool_failures',[]).extend(self.p.pop('tool_failures'))")
edit('law_navigation.py',"            rr.annotate_reused_reads(self,data,actions)","            rr.annotate_reused_reads(self,data,actions)\n            rr.recovery_menu(self,data,actions)")
edit('law_navigation.py',"        except Exception:\n            if gap_action is not None:gap_action['status']='INTERRUPTED'\n            step['status']='INTERRUPTED';self.save();raise", """        except Exception as error:
            if self.modern and rr.record_tool_failure(self, decision, actions, step, error):
                if gap_action is not None:gap_action.update(status='FAILED',outcome=deepcopy(step['outcome']))
                self.save()
                return False
            if gap_action is not None:gap_action['status']='INTERRUPTED'
            step['status']='INTERRUPTED';self.save();raise""")
edit('law_navigation.py',"        kind = value['next_action']; targets = value['targets']", "        kind = value['next_action']; targets = value['targets']\n        if self.modern:rr.validate_failed_operation(self,value,actions)")
edit('law_navigation.py',"            self.execute(decision, data, actions)\n            self.p['decisions'].append", """            applied = self.execute(decision, data, actions)
            if applied is False:
                self.p['turn'] += 1; self.p.pop('accepted', None); self.p.pop('decision_retry', None); self.save()
                continue
            self.p['decisions'].append""")
# Correct inherited contradictory v4 advice in v5's actual model view.
edit('law_navigation.py',"            if self.p.get('prior_investigation'):","""                if self.modern:
                    data['gap_rule'] = ('gap_targets의 READ 또는 문서 범위 도구로 부족한 대상을 확인한다. '
                        'RESOLVED는 해당 대상의 실제 전달·채택 span으로 증명한다. 이미 읽은 원문도 사용할 수 있다. '
                        'NOT_AVAILABLE은 정확한 대상의 완료된 부재 조회 receipt만 허용한다. '
                        '오류·부분 조회·미확보·조사 한도는 UNRESOLVED, 불필요한 대상은 NOT_NEEDED와 이유를 쓴다.')
            if self.p.get('prior_investigation'):""")
print('Target routes, source subset reuse and typed bounded tool recovery connected in isolated candidate')
