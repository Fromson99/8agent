from pathlib import Path
p=Path('02_BACKEND/lawrag/research/candidates/adr_0694/structured-reading/snapshot/02_BACKEND/semantic_runtime/legal_agent/law_navigation.py');s=p.read_text()
a="        data['presentation_id']=lc.token(self.s,'P',digest(data));self.save()"
b="        if self.policy['batch_selected_pages'] and not restored:\n            self.batch_pages(data,actions)\n        data['presentation_id']=lc.token(self.s,'P',digest(data));self.save()"
assert a in s;s=s.replace(a,b)
a='    def bounded_model_view(self, data):'
b='''    def batch_pages(self, data, actions):
        """Deliver consecutive already-acquired pages inside the actual view budget.

        max_context_chars is a character limit. Physical model usage remains the
        provider-reported token count; acquisition never implies delivery/adoption.
        """
        import json
        limit=self.s.profile.get('max_context_chars') or 0
        if not limit:return
        original_pages=len(data['sources'])
        for gid in list(dict.fromkeys(p['branch_id'] for p in data['sources'])):
            group=self.p['groups'][gid]
            for number in range(max(p['page'] for p in data['sources'] if p['branch_id']==gid),len(group['page_plan'])):
                page=self.render_page(group,number)
                basis={k:page[k] for k in ('id','branch_id','source_id','page','total_pages')}
                data['sources'].append(page);data['basis'].append(basis)
                if len(json.dumps(self.model_view(data),ensure_ascii=False))>limit:
                    data['sources'].pop();data['basis'].pop();break
            displayed=[p for p in data['sources'] if p['branch_id']==gid]
            last=max(p['page'] for p in displayed)
            if len(displayed)<2:continue
            for page in displayed:
                page['selected_scope_complete']=inventory.covers(
                    inventory.expected(self.s,group['hit']['document_id'],self.p['selected'][gid]['offer']['block_ids']),
                    [s for b in self.p['basis_history'].values() if b.get('branch_id')==gid and b.get('scope_id')==page['scope_id'] for s in b.get('spans',[])]+
                    [s for p in displayed if p['page']<=page['page'] for s in p['spans']])
            old=[k for k,a in actions.items() if a['action']=='READ_PARENT' and a['identity'].get('branch_id')==gid and a['identity'].get('continuation')]
            for key in old:actions.pop(key)
            target=None
            if last<len(group['page_plan']):
                identity={'branch_id':gid,'page':last,'continuation':True}
                target=lc.token(self.s,'T',['READ_PARENT',identity]);actions[target]={'id':target,'action':'READ_PARENT','identity':identity,'label':'선택 범위의 다음 원문 페이지 보기'}
            for card in data['articles']:
                if card['id']==gid:
                    card['read_parent_action']=target
                    card['original_basis_refs']=list(dict.fromkeys(card.get('original_basis_refs',[])+[p['id'] for p in displayed]))
        data['actions']=[{k:a[k] for k in ('id','action','label')} for a in actions.values()]
        if len(data['sources'])>original_pages:
            data['read_batch']={'acquired_pages_presented':len(data['sources']),'automatic_adoption':False,
                'budget_unit':'characters','max_context_chars':limit}

    def bounded_model_view(self, data):'''
assert a in s;p.write_text(s.replace(a,b))
