from common import *
S=ROOT/read(DES/'candidate.json')['snapshot'];p=S/'02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py';s=p.read_text()
helper='''def contained_arrivals(inv,goal):
    """Existing ancestor receipt, not a new read or a semantic exclusion."""
    from . import evidence_inventory as inventory, unit_reading
    did=goal['document_id'];matcher=inv.s.matcher
    if did not in inv.s.scope:raise ContractError('source goal outside current document scope')
    # Resolve one stored coordinate, never guess from the text or a label prefix.
    coordinates=matcher.stored_coordinates
    rows=coordinates.for_document(did) if hasattr(coordinates,'for_document') else coordinates.items()
    candidates=[]
    for (document,uid),coordinate in rows:
        if document!=did or not coordinate or coordinate.canonical_surface()!=goal['coordinate']:continue
        node=matcher.units[(did,str(uid))]
        if node.get('coordinate_scope')==goal['coordinate_scope'] and node.get('coordinate_binding',{}).get('mode')!='unresolved':candidates.append(str(uid))
    if len(candidates)!=1:return []
    target=candidates[0];ancestors=set();current=target
    while current is not None:
        if current in ancestors:raise ContractError('source goal structure parent cycle')
        ancestors.add(current);node=matcher.units.get((did,current))
        if node is None:raise ContractError('source goal structure parent missing')
        parent=node.get('parent');current=str(parent) if parent is not None else None
    expected=None;arrivals=[]
    for plan in inv.p.get('read_plans',{}).values():
        if plan.get('status')!='ACQUIRED':continue
        for identity in plan.get('targets',[]):
            source=matcher.sources.get(identity.get('source_id'))
            if not source or source['document_id']!=did:continue
            if identity.get('document_id',did)!=did:raise ContractError('source goal read identity document mismatch')
            uid=str(identity.get('unit_id') or source.get('unit_id'))
            if uid==target or uid not in ancestors:continue
            if matcher.units[(did,uid)].get('coordinate_scope')!=goal['coordinate_scope']:continue
            for gid in plan.get('completed',{}).values():
                record=inv.p.get('selected',{}).get(gid)
                if not record or record.get('document_id')!=did or record.get('source_id')!=identity.get('source_id'):continue
                if expected is None:
                    expected=inventory.expected(inv.s,did,unit_reading.blocks(inv.s,did,target,'subtree'))
                    expected+=goal.get('expected',[])
                actual=[span for e in record.get('evidence',[]) for span in e.get('spans',[])]
                if not expected or not inventory.covers(expected,actual):continue
                for evidence in record['evidence']:
                    if evidence['document_id']!=did or evidence['source_id']!=record['source_id']:raise ContractError('source goal original identity changed')
                    inv.s.source.verify(evidence)
                arrivals.append(gid)
    if arrivals:
        inv.s.repo.event('SOURCE_GOAL_CONTAINED_ORIGINAL',{'goal_id':goal['goal_id'],'document_id':did,
            'coordinate':goal['coordinate'],'coordinate_scope':goal['coordinate_scope'],
            'unit_id':target,'arrivals':sorted(set(arrivals)),'new_read':False,'legal_judgment_adopted':False})
    return arrivals


'''
assert 'def contained_arrivals' not in s;s=s.replace('def refresh(inv,goals):',helper+'def refresh(inv,goals):');old="        if acquired:\n            goal['status']='ACQUIRED';goal['arrivals']=sorted(set(acquired))";assert old in s;s=s.replace(old,"        if not acquired:acquired=contained_arrivals(inv,goal)\n"+old);p.write_text(s)
# Include the new meaningful receipt faults in the same frozen candidate runner.
p=Path(__file__).parent/'check.py';s=p.read_text();s=s.replace("str(T/'test_fields_native.py'),","str(T/'test_fields_native.py'),str(T/'test_contained_original.py'),");p.write_text(s)
print('Only verified ancestor original proof added; exact completion path preserved')
