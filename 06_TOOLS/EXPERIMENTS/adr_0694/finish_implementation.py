exec(open('06_TOOLS/EXPERIMENTS/adr_0694/implement.py').read().split("p=B/'legal_agent/law_candidates.py'")[0])
p=B/'legal_agent/law_candidates.py';edit(p,"db.execute('SELECT key,source_id FROM unit WHERE document_id=? AND json_extract(json,'$.unit_id') IN (SELECT value FROM json_each(?))',",'db.execute("SELECT key,source_id FROM unit WHERE document_id=? AND json_extract(json,\'$.unit_id\') IN (SELECT value FROM json_each(?))",')
p=B/'legal_agent/law_navigation.py'
edit(p,"'OPEN_STRUCTURE', 'BROWSE_STRUCTURE') and signature", "'OPEN_STRUCTURE', 'BROWSE_STRUCTURE', 'SEARCH_BODY') and signature")
edit(p,"        elif kind == 'SEARCH_STRUCTURE':\n            filters = value.get('structure_filter')", "        elif kind == 'SEARCH_BODY':\n            identity=actions[targets[0]]['identity']\n            key=digest([identity,search_key(value['queries'])])\n            if not self.policy['structure_first'] or not value['queries'] or any(not q.strip() for q in value['queries']):\n                raise ProposalError('scoped body search requires nonempty queries')\n            if key in self.p.get('body_search_history',[]):raise ProposalError('unchanged body search in the same structure scope')\n            if len(self.p.get('body_search_history',[]))>=self.policy['search_rounds']:raise ProposalError('body search rounds exhausted')\n        elif kind == 'SEARCH_STRUCTURE':\n            filters = value.get('structure_filter')")
edit(p,"                    self.p['fulltext_scopes'][did]=uid", "                    if kind=='SEARCH_BODY':self.p.setdefault('body_search_history',[]).append(digest([identity,search_key(decision['queries'])]))\n                    self.p['fulltext_scopes'][did]=uid")
# Keep body result reads within the explicitly selected subtree. An empty metadata
# container's children remain addressable without expanding to an outside parent.
edit(p,"hits = [lc.hit_shape(h, self.p['catalogue']['terms']) for h in page['items']]", "hits = [lc.hit_shape(h, self.fulltext_terms(did)) for h in page['items']]\n        if self.policy['structure_first'] and self.p['fulltext_scopes'][did] is not None:\n            for h in hits:h['requested_unit_id']=self.p['fulltext_scopes'][did]")
# Fulltext article shortcuts must preserve the selected subtree rather than root.
edit(p,"{'source_id':row['source_id'],'document_id':did}", "{'source_id':row['source_id'],'document_id':did, **({'unit_id':self.p['fulltext_scopes'][did]} if self.policy['structure_first'] and self.p['fulltext_scopes'][did] is not None else {})}")
# Existing model input uses a character budget, not a token estimate. Expand only
# inside explicitly acquired scopes and only if the actual serialized view fits.
edit(p,"        data['presentation_id'] = lc.token(self.s, 'P', digest(data))\n        return data, actions", "        data['presentation_id'] = lc.token(self.s, 'P', digest(data))\n        return data, actions")
# Batch at the end of view, after inventory/chain additions so the limit includes them.
s=p.read_text();start=s.index('    def view(self):');end=s.index('\n    def ',start+5);part=s[start:end]
print(part[-800:])
p=S/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=json.loads(p.read_text());v['candidate_navigation'].update(structure_first=True,batch_selected_pages=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in B.rglob('*.py'):
 if p.name in ('law_candidates.py','unit_fulltext.py','law_navigation.py','unit_reading.py'):compile(p.read_text(),str(p),'exec')
