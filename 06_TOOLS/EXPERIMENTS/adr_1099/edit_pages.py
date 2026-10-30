"""Defer fulltext excerpt bodies until their candidate page is requested."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
CODE=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1099/performance-r1/snapshot'
AG='02_BACKEND/semantic_runtime/legal_agent/'
def edit(name, old, new, count=1):
    p=CODE/AG/name;t=p.read_text();assert t.count(old)==count,(name,old[:60],t.count(old));p.write_text(t.replace(old,new))

edit('law_navigation.py',"        if key not in cache:\n            page=self.p.get('article_pages'", "        key = digest([key, 'visible-details-v2']) if self.policy.get('minimal_input') else key\n        if key not in cache:\n            page=self.p.get('article_pages'")
edit('law_navigation.py',"                sid=item['source_id'];source=self.s.tools.sources[sid]\n                hits=self.idx.hit_page(self.db,self.fulltext_terms(did),sid,lc.allowed(self.s),limit=3,**self.fulltext_args(did))['items']\n                body=next((h for h in hits if str(h['unit_id'])!=str(h['article_unit_id'])),hits[0] if hits else None)\n                rows.append({'source_id':sid,'article':source.get('heading',''),'matched_units':item['unit_count'],\n                    'preview':body['text'][:240] if body else ''})",
"                sid=item['source_id'];source=self.s.matcher.sources[sid]\n                row={'source_id':sid,'article':source.get('heading',''),'matched_units':item['unit_count']}\n                if self.policy.get('minimal_input'):\n                    # One immutable query descriptor per law/menu, not per row.\n                    self.p.setdefault('candidate_preview_queries', {}).setdefault(key, {\n                        'terms':list(self.fulltext_terms(did)), 'allowed':sorted(lc.allowed(self.s)),\n                        'args':deepcopy(self.fulltext_args(did)), 'document_id':did,\n                        'index_sha256':self.idx.manifest['index_sha256']})\n                    row['deferred_preview']={'query':key,'source_id':sid}\n                else:\n                    hits=self.idx.hit_page(self.db,self.fulltext_terms(did),sid,lc.allowed(self.s),limit=3,**self.fulltext_args(did))['items']\n                    body=next((h for h in hits if str(h['unit_id'])!=str(h['article_unit_id'])),hits[0] if hits else None)\n                    row['preview']=body['text'][:240] if body else ''\n                rows.append(row)")
edit('law_navigation.py', '    def bind_reference_delivery(self, include_current=False, current_pages=()):', '''    def prepare_read_details(self, data, candidates, targets):
        """Prepare only visible excerpts; durable query and body cache survive resume."""
        self.s.store.check_unchanged(); self.idx.check_unchanged()
        allowed=set(lc.allowed(self.s)); targets=set(targets)
        changed=False
        value=deepcopy(data)
        for law in value.get('laws', []):
            for row in law.get('article_matches', []):
                descriptor=row.pop('deferred_preview', None)
                if not descriptor or row.get('read_action') not in targets:continue
                target=row['read_action']; action=candidates[target]
                sid=descriptor['source_id']; query=self.p['candidate_preview_queries'][descriptor['query']]
                if (action['identity']['source_id']!=sid or sid not in allowed
                        or not set(query['allowed'])<=allowed
                        or query['document_id']!=law['document_id']
                        or query['index_sha256']!=self.idx.manifest['index_sha256']):
                    raise ContractError('candidate detail query binding changed')
                key=digest([self.p['binding'],descriptor,query])
                cache=self.p.setdefault('candidate_preview_cache', {})
                if key not in cache:
                    hits=self.idx.hit_page(self.db,query['terms'],sid,query['allowed'],limit=3,**query['args'])['items']
                    body=next((h for h in hits if str(h['unit_id'])!=str(h['article_unit_id'])),hits[0] if hits else None)
                    self.s.store.check_unchanged(); self.idx.check_unchanged()
                    cache[key]=body['text'][:240] if body else ''
                    changed=True
                row['preview']=cache[key]
        self.s.store.check_unchanged(); self.idx.check_unchanged()
        if changed:self.save()
        return value

    def bind_reference_delivery(self, include_current=False, current_pages=()):''')
edit('decision_projection.py',"        value = pages.choose(inv,payload,schema,invoke,expand,key=key,correction_scope=correction_scope)",
"        def prepare_page(view):\n            targets=[r['target'] for r in view['read_candidates']]\n            if not hasattr(inv, 'prepare_read_details'):return view\n            prepared=inv.prepare_read_details(data,candidates,targets)\n            visible={k:candidates[k] for k in targets}\n            detailed={r['target']:r for r in read_candidate_rows(prepared,visible,getattr(inv.s,'matcher',None))}\n            return {**view,'read_candidates':[detailed[k] for k in targets]}\n        value = pages.choose(inv,payload,schema,invoke,expand,key=key,correction_scope=correction_scope,prepare_page=prepare_page)")
edit('read_candidate_pages.py',"def choose(inv, data, schema, invoke, expand, *, key, correction_scope=None):", "def choose(inv, data, schema, invoke, expand, *, key, correction_scope=None, prepare_page=None):")
edit('read_candidate_pages.py',"VERSION = 'read-candidate-pages-v1'", "VERSION = 'read-candidate-pages-v2'")
edit('read_candidate_pages.py',"        view, wire = page_view(data, schema, page, page_size)", "        view, wire = page_view(data, schema, page, page_size)\n        if prepare_page is not None:\n            view = prepare_page(view)")
edit('read_candidate_pages.py',"'sequence': state['sequence'], 'corpus_queries': 0,", "'sequence': state['sequence'], 'detail_policy':'first-visit-bounded-revisit-cached',")
edit('read_candidate_pages.py','"""Durable, SQL-free page selection over one immutable prepared read menu.\n\nOnly normal journal/budget operations are performed by the existing decision\nowner. Page movement never calls Investigation.view or a search/source index.\n"""', '"""Durable pages over a bound metadata menu.\n\nFirst visits may load bounded excerpts through the existing search projection;\nrevisits reuse checkpointed details. Candidate availability precedes pagination.\n"""')
edit('law_navigation.py',"        read_choice=choose_read(self,data,actions,phase)\n", "        read_choice=choose_read(self,data,actions,phase)\n")
# Canonical fallback is rare (e.g. finalization reserve): materialize its exact
# offered reads before that older whole-menu consumer sees the view.
p=CODE/AG/'law_navigation.py';t=p.read_text();needle='        read_choice=choose_read(self,data,actions,phase)\n';pos=t.index(needle);print(t[pos:pos+230])
print('D candidate details staged; inspect canonical fallback before freezing.')
