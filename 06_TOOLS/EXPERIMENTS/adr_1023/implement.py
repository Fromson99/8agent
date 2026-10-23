from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate'];base=C/'02_BACKEND/semantic_runtime/legal_agent'
def edit(name,old,new):
 p=base/name;t=p.read_text();assert old in t,(name,old[:120]);p.write_text(t.replace(old,new,1))
helper='''def directory_key(scope):
    # Equal delivered bytes share a directory even through different UI scopes.
    return digest(scope['members'])


def directory_receipt(inv, scope):
    receipt = inv.p.get('connection_directories', {}).get(directory_key(scope))
    if receipt is None:
        return None
    if receipt.get('sha256') != digest({k:v for k,v in receipt.items() if k != 'sha256'}):
        raise ContractError('connection directory receipt hash mismatch')
    if (receipt['binding'] != digest(inv.p['binding']) or
            receipt['authorized_scope'] != sorted(inv.s.scope) or
            receipt['members_hash'] != directory_key(scope)):
        raise ContractError('connection directory receipt binding mismatch')
    for member in scope['members']:
        source = inv.s.tools.sources.get(member['source_id'])
        if not source or source['document_id'] != member['document_id'] or source['document_id'] not in inv.s.scope:
            raise ContractError('connection directory anchor outside authorized original')
    return receipt


def reject_repeated_follow(inv, scope):
    from .errors import ProposalError
    if directory_receipt(inv, scope) is not None:
        raise ProposalError('connection directory already inspected for unchanged original scope; use saved targets or finish')


def directory_operation(inv):
    accepted = inv.p.get('accepted')
    return digest([accepted['input_hash'], accepted['decision']]) if accepted else None


def inspect_directory(inv, scope):
    """Durable request-local catalog; rendering never repeats its lookup.

    PARTIAL/FAILED are attempts, never evidence of absence. This directory path
    has no advancing cursor; retrying its unchanged request cannot add results.
    Target acquisition flags are derived afresh, without reopening the directory.
    """
    receipt = directory_receipt(inv, scope)
    if receipt is None:
        result = preview(inv, scope)
        receipt = {'scope_id':scope['id'], 'label':scope['label'],
            'members_hash':directory_key(scope), 'binding':digest(inv.p['binding']),
            'authorized_scope':sorted(inv.s.scope), 'operation':directory_operation(inv),
            'reason':(inv.p.get('selected_connection_scope') or {}).get('reason',''),
            'turn':inv.p.get('turn',0), 'result':deepcopy(result)}
        receipt['sha256'] = digest(receipt)
        inv.p.setdefault('connection_directories', {})[directory_key(scope)] = receipt
        inv.s.repo.event('CONNECTION_DIRECTORY_RECORDED', {
            'scope_id':scope['id'], 'members_hash':directory_key(scope),
            'status':result['status'], 'receipt_sha256':receipt['sha256'],
            'absence_proven':False})
        inv.save()
    result = deepcopy(receipt['result'])
    if result['groups']:
        from . import unit_relations as rel
        acquired, _ = rel.acquired_blocks(inv.s, inv.read_records())
        for group in result['groups']:
            for endpoint in ('anchor','target'):
                row=group[endpoint]; source=inv.s.tools.sources.get(row['source_id'])
                if not source or source['document_id'] != row['document_id'] or row['document_id'] not in inv.s.scope:
                    raise ContractError('connection directory endpoint outside authorized original')
            known = acquired.get(group['target']['source_id'],set())
            group['read_blocks'] = sorted(known)
            for connection in group['connections']:
                connection['already_read'] = rel.blocks_covered(connection['endpoint_block_ids'], known)
    return result


'''
edit('connection_scope.py','def offer_choices(inv, data, actions):',helper+'def offer_choices(inv, data, actions):')
edit('connection_scope.py',"choices = []; previews = {}; cards = []; seen = set()","choices = []; previews = {}; cards = []; seen = set(); history = []; historical_cards = []")
edit('connection_scope.py',"if scope['id'] == selected_id:\n            result = previews[scope['id']] = preview(inv, scope)","reviewed = directory_receipt(inv, scope)\n        if scope['id'] == selected_id or reviewed is not None:\n            result = previews[scope['id']] = inspect_directory(inv, scope)\n            reviewed = directory_receipt(inv, scope)")
edit('connection_scope.py',"if not inline and result['status'] != 'FAILED' and not blocked:","if reviewed is None and not inline and result['status'] != 'FAILED' and not blocked:")
edit('connection_scope.py',"if card.get('requires_scope_menu') and not blocked:","if card.get('requires_scope_menu') and not blocked and reviewed is None:")
edit('connection_scope.py',"            cards.extend(shown)\n        choices.append", "            if scope['id'] == selected_id:cards.extend(shown)\n            else:historical_cards.extend(shown)\n        if reviewed is not None:\n            history.append({'scope_id':scope['id'], 'label':scope['label'],\n                'status':result['status'], 'connection_count':result.get('connection_count'),\n                'reason':reviewed['reason'], 'first_turn':reviewed['turn'],\n                'receipt_sha256':reviewed['sha256'], 'repeat_available':False,\n                'unread_target_count':sum(not c['already_read'] for c in shown) if visible else 0,\n                'absence_proven':False})\n        choices.append")
edit('connection_scope.py',"'selected': scope['id'] == selected_id,", "'selected': scope['id'] == selected_id, 'previously_inspected': reviewed is not None,")
edit('connection_scope.py',"references['dependency_cards'] = cards", "references['dependency_cards'] = cards\n    references['previously_inspected_cards'] = historical_cards\n    data['connection_action_history'] = history")
edit('connection_scope.py',"'더 많은 연결은 해당 범위의 연결 메뉴로 확인한다.')", "'previously_inspected_cards는 전에 명시적으로 선택해 확인한 범위의 저장된 연결이다. '\n        'connection_action_history의 실제 결과와 미확보 대상을 확인하고, 필요한 원문은 read_action으로 바로 읽는다. '\n        '이미 확인한 범위는 다시 FOLLOW_CONNECTION할 수 없다. 동일 조회로 추가 확보되지 않는 PARTIAL/FAILED는 구조 검색으로 조사하거나 미확인을 남긴다.')")
edit('connection_scope.py',"if c['selected'] and\n        c['connection_preview']['status'] != 'NOT_SELECTED'", "if c['connection_preview']['status'] != 'NOT_SELECTED'")
edit('connection_scope.py',"targets = {digest(c['target']): deepcopy(c['target']) for c in cards}","targets = {digest(c['target']): deepcopy(c['target']) for c in cards + historical_cards}")
# Existing locator receipt remains current-scope bound, with stored prior targets also presented.
edit('connection_scope.py',"'더 많은 연결 또는 다른 범위는 해당 범위의 FOLLOW_CONNECTION을 고른다. '","'미확인 범위만 FOLLOW_CONNECTION을 고른다. 확인한 범위의 목록과 결과는 보존되므로 재조회하지 않는다. '")
# Historical cards are presentation authority; the exact witness is still revalidated against storage.
edit('connection_scope.py',"    if selected is None or selected['scope']['id'] != link['scope_id']:\n        raise ContractError('inline connection is outside the final selected scope')", "    prior = any(c.get('connection_scope_id') == link['scope_id'] and\n        c.get('reference_id') == link['reference_id'] and c.get('target',{}).get('source_id') == identity['source_id']\n        for c in data.get('references',{}).get('previously_inspected_cards',[]))\n    if not prior and (selected is None or selected['scope']['id'] != link['scope_id']):\n        raise ContractError('inline connection is outside the final selected scope')")
edit('connection_scope.py',"    if scope is None:\n        raise ContractError('stale inline connection scope')", "    if scope is None:\n        raise ContractError('stale inline connection scope')\n    if prior and directory_receipt(inv,scope) is None:\n        raise ContractError('historical connection directory receipt missing')")
# Both the proposal validator and execution boundary guard against unchanged scope repeats.
edit('law_navigation.py',"        if targets and kind not in ('FOLLOW_CONNECTION', 'READ_PARENT', 'READ_SCOPE', 'RETURN_TO',", "        if targets and kind == 'FOLLOW_CONNECTION':\n            from . import connection_scope as cs\n            scope = actions[targets[0]]['identity'].get('connection_scope')\n            if cs.enabled(self) and scope:cs.reject_repeated_follow(self,scope)\n        if targets and kind not in ('FOLLOW_CONNECTION', 'READ_PARENT', 'READ_SCOPE', 'RETURN_TO',")
edit('law_navigation.py',"                else:\n                    scope_choice = cs.accept(self,identity.get('connection_scope',{}),data,decision['reason'])", "                else:\n                    scope = identity.get('connection_scope',{})\n                    receipt = cs.directory_receipt(self,scope)\n                    operation = cs.directory_operation(self)\n                    if receipt is not None and (operation is None or receipt.get('operation') != operation):\n                        cs.reject_repeated_follow(self,scope)\n                    scope_choice = cs.accept(self,scope,data,decision['reason'])")
edit('law_navigation.py',"directory = cs.preview(self, scope_choice['scope'])","directory = cs.inspect_directory(self, scope_choice['scope'])")
edit('law_navigation.py',"                if self.modern and accepted['decision']['next_action']=='READ_ARTICLES':", "                if self.modern:\n                    for key in ('connection_directories','selected_connection_scope','connection_scope_history'):\n                        if key in self.p:progressed[key]=deepcopy(self.p[key])\n                if self.modern and accepted['decision']['next_action']=='READ_ARTICLES':")
edit('decision_projection.py',"'connection_scope_choices':deepcopy(data.get('connection_scope_choices',[])),", "'connection_scope_choices':deepcopy(data.get('connection_scope_choices',[])),\n        'connection_action_history':deepcopy(data.get('connection_action_history',[])),")
# Options for saved links keep their source context, not only their opaque handle.
edit('decision_projection.py',"'references':data.get('references',{})", "'references':data.get('references',{})")
print('Implemented durable directories, history, repeat guards and resume preservation')
