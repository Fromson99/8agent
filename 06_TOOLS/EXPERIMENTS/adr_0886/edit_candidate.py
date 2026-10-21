from pathlib import Path
R=Path(__file__).resolve().parents[3];P=R/'02_BACKEND/lawrag/research/candidates/adr_0886/continuity/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=P/'decision_projection.py';s=p.read_text();s=s.replace("wanted=set(state.get('requested_originals',[]))","wanted=set(state.get('selected',{}))")
s=s.replace("for gid in inv.p.get('requested_originals',[]):","for gid in original_groups(inv.p):")
old='''            # A changed selected scope/page plan must not relabel old spans.
            number=b['page']-1
            if number>=len(group['page_plan']):continue
            page=inv.render_page(group,number)
            if page['id']!=ref:continue
            inventory.check_page(inv.s,inv.p,page)'''
new='''            # Preserve the accepted page's original scope and spans even after
            # another read changes this group's current page plan.
            number=b['page']-1
            page=inv.render_page(group,number) if number<len(group['page_plan']) else None
            if page is None or page['id']!=ref:
                record=inv.p['selected'][gid]
                page={**deepcopy(b),'document_id':record['document_id'],
                    'document_name':record.get('document_name',''),'heading':record.get('heading',''),
                    'text':'\\n'.join(span['text'] for span in b['spans']),
                    'group_complete':None,'selected_scope_complete':None,'retained_historical_scope':True}
            inventory.check_page(inv.s,inv.p,page,current_scope=False)'''
assert old in s;s=s.replace(old,new)
pos=s.index('\ndef retain_requested(')
s=s[:pos]+'''
def original_groups(state):
    """Stable order for all acquired originals; acquisition is not adoption."""
    selected=state.get('selected',{})
    return list(dict.fromkeys([g for g in state.get('requested_originals',[]) if g in selected]+list(selected)))


def bounded_original_refs(state,mandatory,limit):
    """Additional context is whole accepted pages; explicit final choices win."""
    mandatory=list(dict.fromkeys(mandatory));available=requested_refs(state)
    def size(ref):return sum(p['end_cp']-p['start_cp'] for p in state['basis_history'][ref].get('spans',[]))
    used=sum(size(ref) for ref in mandatory if ref in state['basis_history'])
    included=[];omitted=[]
    for gid in original_groups(state):
        for ref in reversed(available):
            if ref in mandatory or state['basis_history'][ref]['branch_id']!=gid:continue
            if used+size(ref)>limit:omitted.append(ref);continue
            included.append(ref);used+=size(ref)
    return included,{'included':included,'omitted_by_context_budget':omitted,'character_limit':limit,
        'mandatory_basis_refs':mandatory,'automatic_adoption':False,'source_absence_proven':False}

''' +s[pos:];p.write_text(s)
p=P/'law_navigation.py';s=p.read_text();old="""            from .decision_projection import requested_refs
            delivered_refs=requested_refs(self.p) if self.modern and sufficient else []
            current=inventory.originals_for(self.s,self.p,list(dict.fromkeys((self.p.get('completion_basis_refs',[]) if sufficient else [])+delivered_refs)))
            if delivered_refs:result['original_delivery_context']={'basis_refs':delivered_refs,'automatic_adoption':False}""";new="""            from .decision_projection import bounded_original_refs
            mandatory=self.p.get('completion_basis_refs',[]) if sufficient else []
            limit=max(self.s.profile['max_read_chars'],(self.s.profile.get('max_context_chars') or 100000)//2)
            delivered_refs,delivery_context=bounded_original_refs(self.p,mandatory,limit) if self.modern and sufficient else ([],None)
            current=inventory.originals_for(self.s,self.p,list(dict.fromkeys(mandatory+delivered_refs)))
            if delivery_context is not None:result['original_delivery_context']={**delivery_context,'basis_refs':delivered_refs}""";assert old in s;s=s.replace(old,new);p.write_text(s)
print('All delivered selected read paths retained; original scope preserved;50kwhole-page extra context bound')
