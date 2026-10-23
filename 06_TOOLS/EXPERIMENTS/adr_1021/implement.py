from common import *
C=ROOT/read(ART/'stage.json')['roots']['candidate'];D=C/'02_BACKEND/semantic_runtime/legal_agent'
p=D/'connection_scope.py';s=p.read_text();a=s.index('\ndef offer_choices(')
s=s[:a]+'''
def refresh_selected_delivery(inv, choices, selected):
    """New delivered bytes may extend the same already chosen structure.

    Candidates are rebuilt from verified model-visible pages. Their changing
    span hash must not erase the user's/model's structural choice. A different
    structure, exclusion, or loss/change of previously bound bytes is not a
    refresh. Keep host refreshes distinct from model selections in the journal.
    """
    if selected is None:
        return None
    old = selected['scope']
    if any(s['id'] == old['id'] for s, _ in choices):
        return selected
    matches = [s for s, _ in choices if s['structural_selection'] == old['structural_selection']]
    if len(matches) != 1:
        return selected
    new = matches[0]
    pieces = lambda scope: {(m['document_id'], m['source_id'], digest(p))
        for m in scope['members'] for p in m['spans']}
    if not pieces(old) < pieces(new):
        return selected
    if new['id'] != digest({k:v for k,v in new.items() if k != 'id'}):
        raise ContractError('refreshed connection scope hash mismatch')
    value = {**deepcopy(selected), 'scope':deepcopy(new),
        'acquired_signature':acquired_signature(inv), 'status':'SELECTED',
        'refresh_origin':'ACQUIRED_WITHIN_SELECTED_STRUCTURE', 'previous_scope_id':old['id']}
    value.pop('result', None)
    inv.p['selected_connection_scope'] = value
    inv.p.setdefault('connection_scope_history', []).append(deepcopy(value))
    inv.s.repo.event('CONNECTION_SCOPE_REFRESHED', {
        'previous_scope_id':old['id'], 'scope_id':new['id'],
        'structural_selection':deepcopy(new['structural_selection']),
        'model_selected_again':False, 'previous_spans':len(pieces(old)),
        'current_spans':len(pieces(new)), 'automatic_target_read':False})
    inv.save()
    return value

''' + s[a:]
s=s.replace("    selected = current(inv, allow_acquired_change=True)\n    selected_id", "    scope_choices = candidates(inv, data)\n    selected = refresh_selected_delivery(inv, scope_choices, current(inv, allow_acquired_change=True))\n    selected_id",1)
s=s.replace('    for scope, refs in candidates(inv, data):','    for scope, refs in scope_choices:',1)
p.write_text(s)
p=D/'decision_projection.py';s=p.read_text();old="if budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']<3:return None";assert s.count(old)==1;s=s.replace(old,"if budget['model_limit']-budget['finalization_reserve']-budget['model_reserved']<2:return None");p.write_text(s)
p=C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';m=read(p);m['candidate_navigation']['answer_progress_control']=True;save(p,m)
p=Path(__file__).with_name('repin.py');s=p.read_text().replace('pins = {}',"changed.append('00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')\npins = {}") ;p.write_text(s)
print('Selected-scope refresh, last-budget narrow choice, existing answer progress enabled')
