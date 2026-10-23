from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate'];D=C/'02_BACKEND/semantic_runtime/legal_agent'
p=D/'connection_scope.py';s=p.read_text();old="    data['connection_review'] = {";new="""    if attempted:
        # Persist only verified target identities, not source bodies. Modern
        # FINISH may retain originals without ADOPT; its older reference export
        # can consequently be empty. The directory shown here remains evidence
        # of a stored location, independent of legal adoption.
        targets = {digest(c['target']): deepcopy(c['target']) for c in cards}
        receipt = {'scope_id': selected_id, 'binding': selected['binding'],
            'targets': [targets[k] for k in sorted(targets)],
            'status': attempted['connection_preview']['status']}
        receipt['sha256'] = digest(receipt)
        selected['locator_receipt'] = receipt
    data['connection_review'] = {""";assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
p=D/'request_repair.py';s=p.read_text().replace('def assessment_locator_options(sources, navigation):','def assessment_locator_options(sources, navigation, *, selected_scope=None, binding=None, session=None):')
old="    for name in documents:\n        rows.setdefault(name, {'target': name, 'origin': 'KNOWN_DOCUMENT'})"
new="""    if selected_scope and selected_scope.get('locator_receipt'):
        scope = selected_scope['scope']; receipt = selected_scope['locator_receipt']
        if (scope['id'] != digest({k:v for k,v in scope.items() if k != 'id'})
                or receipt['sha256'] != digest({k:v for k,v in receipt.items() if k != 'sha256'})
                or receipt['scope_id'] != scope['id']
                or receipt['binding'] != digest(binding)
                or selected_scope['binding'] != digest(binding)):
            raise ContractError('assessment connection locator receipt changed')
        for target in receipt['targets']:
            if session is None or target['document_id'] not in session.scope:
                raise ContractError('assessment connection locator outside request scope')
            source = session.tools.sources.get(target['source_id'])
            if not source or any(source.get(k) != target.get(k) for k in ('document_id','document_name','heading')):
                raise ContractError('assessment connection locator source changed')
            add(target, 'PRESENTED_STORED_REFERENCE_TARGET')
    for name in documents:
        rows.setdefault(name, {'target': name, 'origin': 'KNOWN_DOCUMENT'})"""
assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
p=D/'completion_execution.py';s=p.read_text();old="rr.assessment_locator_options(sources, selection.get('reference_navigation', {}))";new="rr.assessment_locator_options(sources, selection.get('reference_navigation', {}), selected_scope=investigation.get('selected_connection_scope'), binding=investigation.get('binding'), session=self.s.sources)";assert s.count(old)==1;p.write_text(s.replace(old,new))
p=C/'05_TESTS/CONTRACTS/test_selected_connection_scope_api.py';s=p.read_text().replace("                elif route == 'gap_repair':\n                    self.assess_repairs += 1", "                elif route == 'gap_repair':\n                    self.assess_repairs += 1\n                    gap['missing_target']=next(r['target'] for r in view['locator_options'] if '제2조' in r['target'])");p.write_text(s)
p=C/'05_TESTS/CONTRACTS/test_scope_first_grounded_navigation.py';s=p.read_text()+'''

@pytest.mark.parametrize('mutation',['none','hash','binding','acl','source'])
def test_persisted_connection_locator_receipt_rechecks_identity(mutation):
    from types import SimpleNamespace as S
    from semantic_runtime.contracts import digest
    from semantic_runtime.legal_agent.errors import ContractError
    scope={'members':[]};scope['id']=digest(scope)
    binding={'generation':'one'}
    target=dict(source_id='s',document_id='d',document_name='모의법',heading='제8조')
    receipt=dict(scope_id=scope['id'],binding=digest(binding),targets=[target],status='COMPLETE')
    receipt['sha256']=digest(receipt)
    selected=dict(scope=scope,binding=digest(binding),locator_receipt=receipt)
    session=S(scope=['d'],tools=S(sources={'s':dict(target)}))
    if mutation=='hash':receipt['targets'][0]['heading']='제99조'
    if mutation=='binding':binding={'generation':'two'}
    if mutation=='acl':session.scope=[]
    if mutation=='source':session.tools.sources['s']['heading']='제99조'
    if mutation=='none':
        rows=rr.assessment_locator_options([],{},selected_scope=selected,binding=binding,session=session)
        assert any(r['target']=='모의법 제8조' for r in rows)
    else:
        with pytest.raises(ContractError):rr.assessment_locator_options([],{},selected_scope=selected,binding=binding,session=session)
''';p.write_text(s)
(ART/'design-freeze.json').rename(ART/'preflight-freeze-r2.json')
save(ART/'preflight-repair-r2.json',{'product_change':'Preserve verified presented connection targets in a scope/binding/hash receipt for the assessment consumer, independently of ADOPT metadata. Recheck source identity and current ACL.','reason':'Synthetic native API injected gap test found modern reference_navigation export empty after FINISH with retained originals; the location selector otherwise lacked a legitimate stored link.', 'baseline':'Six MAIN50 contract failures recur in unchanged working code; no additional failures in candidate except injected location receipt test. Original logs retained.','live_calls_so_far':0})
