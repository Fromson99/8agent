from pathlib import Path
B=Path('02_BACKEND/lawrag/research/candidates/adr_0694/structured-reading/snapshot/02_BACKEND/semantic_runtime/legal_agent')
p=B/'law_candidates.py';s=p.read_text();s+='''

def scoped_read_unit(session, source_id, selected_unit):
    """Clip a broad structural selection to each article's original boundary."""
    if selected_unit is None:return None
    source=session.tools.sources[source_id];uid=str(source['unit_id']);selected=str(selected_unit);seen=set()
    while uid not in seen:
        if uid==selected:return str(source['unit_id'])
        seen.add(uid);node=session.matcher.units.get((source['document_id'],uid))
        if not node or node.get('parent') is None:break
        uid=str(node['parent'])
    return selected
''';p.write_text(s)
p=B/'law_navigation.py';s=p.read_text().replace("'unit_id':self.p['fulltext_scopes'][did]} if self.policy['structure_first'] and self.p['fulltext_scopes'][did] is not None", "'unit_id':lc.scoped_read_unit(self.s,row['source_id'],self.p['fulltext_scopes'][did])} if self.policy['structure_first'] and self.p['fulltext_scopes'][did] is not None")
s=s.replace("for h in hits:h['requested_unit_id']=self.p['fulltext_scopes'][did]", "for h in hits:h['requested_unit_id']=lc.scoped_read_unit(self.s,sid,self.p['fulltext_scopes'][did])")
# Token/call metrics come from the physical provider ledger, never this page count.
s=s.replace("data['read_batch']={'acquired_pages_presented':len(data['sources'])", "data['read_batch']={'acquired_pages_prepared_for_model':len(data['sources'])")
p.write_text(s)
