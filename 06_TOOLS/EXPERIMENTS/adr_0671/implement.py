from pathlib import Path
C=Path('02_BACKEND/lawrag/research/candidates/adr_0671/investigation-chain/snapshot/02_BACKEND/semantic_runtime/legal_agent')
p=C/'law_navigation.py';s=p.read_text()
s=s.replace('from . import unit_relations as rel','from . import unit_relations as rel\nfrom . import investigation_chain as trail')
s=s.replace("for gid in groups:\n        if 'DEFER'", "for gid in set(groups) & set(permissions):\n        if 'DEFER'")
s=s.replace("'maxItems': 0 if terminal else 1},", "'maxItems': 0 if terminal else (8 if kind == 'READ_ARTICLES' else 1)},")
s=s.replace('기본 읽기는 적중 목의 부모', '''investigation_chain.steps는 지금까지의 행동·선택·판단 기록이다. 이를 매번 읽고 기존 판단을 이어간다.
RETURN_TO로 return_points의 어느 과거 시점이든 선택할 수 있다. 반드시 돌아갈 이유를 기록한다.
돌아가면 그때의 검색어·후보·원문·연결 선택지가 다시 제시된다. 이후 판단과 채택 근거는 유지된다.
READ_ARTICLES는 같은 법의 article_matches에 제시된 여러 조문을 targets로 함께 선택해 전체를 읽는다.
읽는 것은 채택이 아니다. 먼저 조사하고 실제 제공된 원문으로만 ADOPT한다.
law_decisions/branch_decisions는 이번에 바뀌는 것만 반환한다. 이미 한 보류·채택 이유를 반복 작성하지 않는다.
필요한 원문이나 연결 선택지가 현재 없으면 과거 해당 시점으로 돌아간다. 제목만으로 원문 내용을 추측하지 않는다.
기본 읽기는 적중 목의 부모''')
s=s.replace("self.p.setdefault('read_state',", "trail.state(self.p)\n        self.p.setdefault('window', 'search'); self.p.setdefault('window_groups', [])\n        self.s.investigation_menu_hook = self.reference_menu\n        self.s.investigation_decision_hook = self.reference_decision\n        self.p.setdefault('read_state',")
s=s.replace("self.p['article_pages'] = {}; self.p['hit_pages'] = {}", "self.p['article_pages'] = {}; self.p['hit_pages'] = {}\n            self.p['window']='search'; self.p['window_groups']=[]; self.p.pop('revisit',None)")
s=s.replace('    def view(self):\n', '    def build_view(self):\n',1)
s=s.replace("        page_group=self.p.get('focus') if self.p.get('focus') in waiting else (waiting[0] if waiting else None)", "        focus_ids=self.p.get('window_groups',[])\n        page_groups=list(dict.fromkeys([g for g in focus_ids if g in waiting]+waiting))[:8]\n        page_group=self.p.get('focus') if self.p.get('focus') in waiting else (waiting[0] if waiting else None)")
s=s.replace("        ordered = [lc.token(self.s, 'L', r['document_id']) for r in self.p['law_page']['items']]", "        search_window=self.p.get('window','search')=='search'\n        ordered = [lc.token(self.s, 'L', r['document_id']) for r in self.p['law_page']['items']] if search_window else []\n        ordered.extend(self.p['groups'][gid]['law_id'] for gid in self.p.get('window_groups',[]) if gid in self.p['groups'])")
s=s.replace("ordered.extend(g['law_id'] for g in self.p['groups'].values() if g['id'] in self.p['selected'] and g['status']!='EXCLUDED')", "ordered.extend(g['law_id'] for g in self.p['groups'].values() if g['status']=='ACTIVE')")
s=s.replace("        if self.p['law_page']['next_cursor']:\n            offer", "        if search_window and self.p['law_page']['next_cursor']:\n            offer")
s=s.replace("            if group['status'] == 'EXCLUDED': continue", "            if group['status'] == 'EXCLUDED': continue\n            if not search_window and group['id'] not in self.p.get('window_groups',[]) and group['status']!='ACTIVE':continue",1)
s=s.replace("                if group['id']==page_group:", "                if group['id'] in page_groups:")
s=s.replace("        basis.extend(self.p['basis_history'].values())", "        visible={c['id'] for c in cards}\n        basis.extend(b for b in self.p['basis_history'].values() if b.get('branch_id') in visible)")
s=s.replace("        references = self.inspect_references()", "        references = self.reference_overview()",1)
s=s.replace("                         for g in self.p['groups'].values()],", "                         for g in self.p['groups'].values() if g['id'] in visible],",1)
s=s.replace("            law['articles'] = [c for c in cards if c['law_id']==law['id']]", "            law['articles'] = [c for c in cards if c['law_id']==law['id']]\n            if search_window or self.p.get('window')=='law':\n                law['article_matches']=self.article_menu(law,offer)")
s=s.replace("elif len(targets) != 1 or actions[targets[0]]['action'] != kind:", "elif not targets or len(targets) > (8 if kind=='READ_ARTICLES' else 1) or any(actions[t]['action']!=kind for t in targets):")
s=s.replace("        if targets and kind in ('READ_PARENT', 'READ_SCOPE'):", "        if targets and kind == 'READ_ARTICLES':\n            for target in targets:\n                did=actions[target]['identity']['document_id']\n                if not investigating(lc.token(self.s,'L',did)):raise ProposalError('READ requires an active law investigation reason')\n        if targets and kind in ('READ_PARENT', 'READ_SCOPE'):",1)
s=s.replace("        if targets and kind not in ('FOLLOW_CONNECTION', 'READ_PARENT', 'READ_SCOPE'):", "        if targets and kind not in ('FOLLOW_CONNECTION', 'READ_PARENT', 'READ_SCOPE', 'RETURN_TO') and not data.get('return_context'):")
s=s.replace("        if targets and kind in ('READ_PARENT','READ_SCOPE'):", "        if targets and kind in ('READ_PARENT','READ_SCOPE') and not data.get('return_context'):")
s=s.replace('    def execute(self, decision, data, actions):', '    def execute_tool(self, decision, data, actions):',1)
s=s.replace("        if kind in ('FINISH', 'PENDING', 'RESEARCH'): return", "        if kind == 'RESEARCH':self.p['window']='search'\n        if kind in ('FINISH', 'PENDING', 'RESEARCH'): return")
s=s.replace("        if kind in ('READ_PARENT', 'READ_SCOPE'):\n            group", "        if kind == 'RETURN_TO':\n            self.restore(identity['frame_id'],decision['reason'])\n            if trail.frame(self.p,identity['frame_id'])['kind']=='REFERENCE':\n                kind='FOLLOW_CONNECTION'; identity={'replay_frame':identity['frame_id']}\n            else:return\n        if kind == 'READ_ARTICLES':\n            ids=[]\n            for target in decision['targets']:\n                ident=actions[target]['identity'];sid=ident['source_id']\n                self.open_hits(sid,None,1)\n                group=next(g for g in self.p['groups'].values() if g['source_id']==sid and g['hit']['unit_id']==g['hit']['article_unit_id'])\n                gid=group['id'];handle=lc.token(self.s,'T',['READ_PARENT',{'branch_id':gid,'page':0}])\n                temp={handle:{'id':handle,'action':'READ_PARENT','identity':{'branch_id':gid,'page':0},'label':'選択された条文全体'}}\n                self.execute_tool({**decision,'law_decisions':[],'branch_decisions':[],'next_action':'READ_PARENT','targets':[handle]}, {'sources':[]},temp)\n                ids.append(gid)\n            self.p['window']='read';self.p['window_groups']=ids\n        elif kind in ('READ_PARENT', 'READ_SCOPE'):\n            group")
s=s.replace("            self.p['focus']=group['id']", "            self.p['focus']=group['id'];self.p['window']='read';self.p['window_groups']=[group['id']]")
s=s.replace("                if identity['page'] != group['delivery']: raise ContractError('stale parent continuation')", "                if identity['page'] != group['delivery'] and not data.get('return_context'): raise ContractError('stale parent continuation')")
s=s.replace("        elif kind == 'NEXT_LAWS':\n            self.p", "        elif kind == 'NEXT_LAWS':\n            self.p['window']='search';self.p['window_groups']=[]\n            self.p")
s=s.replace("            self.p['article_pages'][did] = page\n            for row in page['items']: self.open_hits(row['source_id'], None, 1)", "            self.p['article_pages'][did] = page\n            self.p['window']='law';self.p['window_groups']=[]\n            for row in page['items']:\n                self.open_hits(row['source_id'], None, 1)\n                self.p['window_groups'].extend(g['id'] for g in self.p['groups'].values() if g['source_id']==row['source_id'])")
s=s.replace("        elif kind == 'NEXT_HITS': self.open_hits(identity['source_id'], identity['cursor'], self.policy['hit_page_size'])", "        elif kind == 'NEXT_HITS':\n            self.open_hits(identity['source_id'], identity['cursor'], self.policy['hit_page_size'])\n            self.p['window']='law';self.p['window_groups']=[g['id'] for g in self.p['groups'].values() if g['source_id']==identity['source_id']]")
s=s.replace("        elif kind == 'FOLLOW_CONNECTION':\n            selected = self.read_records()", "        elif kind == 'FOLLOW_CONNECTION':\n            replay=trail.frame(self.p,identity['replay_frame']) if identity.get('replay_frame') else None\n            focused={g['source_id'] for gid,g in self.p['groups'].items() if gid in self.p.get('window_groups',[])}\n            if replay:focused={g['anchor']['source_id'] for g in replay['offered'].values()}\n            all_reads=self.read_records()\n            selected={k:r for k,r in all_reads.items() if r['source_id'] in focused}\n            if not selected:selected=self.active_records() or all_reads\n            reference_key=digest(sorted(focused))\n            self.p['reference_state']=self.p.setdefault('reference_states',{}).setdefault(reference_key,{})")
s=s.replace("                phase_prefix='source-reference-law-'+str(self.p['turn'])+'-', max_model_batches=1)", "                phase_prefix='source-reference-law-'+str(self.p['turn'])+'-', max_model_batches=1,\n                replay_menu={'data':replay['data'],'offered':replay['offered']} if replay else None)")
s=s.replace("            for key, r in selected.items():", "            new_groups=[]\n            for key, r in selected.items():",1)
s=s.replace("                group = self.p['groups'][gid]\n                if gid", "                group = self.p['groups'][gid];new_groups.append(gid)\n                if gid")
s=s.replace("        if kind=='READ_SCOPE' or", "            self.p['window']='references';self.p['window_groups']=new_groups or self.p.get('window_groups',[])\n        if kind=='READ_SCOPE' or")
s=s.replace("        records = self.active_records(); originals", "        records = self.active_records(); originals")
s=s.replace("'law_navigation': {'contract': lc.CONTRACT,", "'investigation_chain':trail.context(self.p),'return_points':trail.points(self.p),\n            'law_navigation': {'contract': lc.CONTRACT,")
s=s.replace("'read_state', 'reference_state','reference_reads','reference_turn'", "'read_state', 'reference_state','reference_reads','reference_turn','action_chain','reference_states'")
s=s.replace("'label':'選択された条文全体'", "'label':'선택한 조문 전체'")
s=s.replace("schema = decision_schema(data, actions, set(self.p['groups']))", "schema = decision_schema(data, actions, {b['id'] for b in data['branches']})")
# Additional methods inserted before original view renderer.
methods='''    def article_menu(self, law, offer):
        did=law['document_id'];key=digest([self.p['catalogue']['query_fingerprint'],did,self.p.get('article_pages',{}).get(did)])
        cache=self.p.setdefault('article_menu_cache',{})
        if key not in cache:
            page=self.idx.article_groups_page(self.db,self.p['catalogue']['terms'],did,lc.allowed(self.s),limit=8)
            rows=[]
            for item in page['items']:
                sid=item['source_id'];source=self.s.tools.sources[sid]
                hits=self.idx.hit_page(self.db,self.p['catalogue']['terms'],sid,lc.allowed(self.s),limit=3)['items']
                body=next((h for h in hits if str(h['unit_id'])!=str(h['article_unit_id'])),hits[0] if hits else None)
                rows.append({'source_id':sid,'article':source.get('heading',''),'matched_units':item['unit_count'],
                    'preview':body['text'][:240] if body else ''})
            cache[key]=rows
        out=deepcopy(cache[key])
        for row in out:
            if not any(r['source_id']==row['source_id'] for r in self.p['selected'].values()):
                row['read_action']=offer('READ_ARTICLES',{'source_id':row['source_id'],'document_id':did},row['article']+' 전체 원문 읽기')
        return out

    def reference_overview(self):
        reads=self.read_records();focus={self.p['groups'][g]['source_id'] for g in self.p.get('window_groups',[]) if g in self.p['groups']}
        return {'pending':bool(reads),'current_anchor_ids':sorted(focus),
            'menu':'현재 읽은 범위의 연결 선택 도구를 열면 상세를 제공한다.',
            'previous_menus':sum(f['kind']=='REFERENCE' for f in trail.state(self.p)['frames'].values())}

    def location(self):
        return {k:deepcopy(self.p.get(k)) for k in ('catalogue','law_page','article_pages','hit_pages','opened_law','focus','window','window_groups')}

    def restore(self, frame_id, reason):
        f=trail.frame(self.p,frame_id)
        # Only presentation location is restored; observations and choices are permanent.
        for k,v in f['location'].items():
            if v is None:self.p.pop(k,None)
            else:self.p[k]=deepcopy(v)
        self.p['revisit']={'frame_id':frame_id,'reason':reason}
        trail.state(self.p)['current_frame']=frame_id
        self.s.repo.event('INVESTIGATION_POINT_RETURNED',self.p['revisit'])

    def reference_menu(self, data, offered):
        f=trail.capture(self.p,'REFERENCE',data,offered=offered,location=self.location())
        data={**data,'chain_frame_id':f,'investigation_chain':trail.context(self.p),
              'return_context':deepcopy(self.p.get('revisit'))}
        self.save();return data

    def reference_decision(self, data, decision):
        step=trail.begin(self.p,data,decision,kind='REFERENCE');step['status']='APPLIED'
        self.s.repo.event('INVESTIGATION_CHAIN_STEP',step);self.save()

    def view(self):
        fresh,actions=self.build_view();restored=self.p.get('revisit')
        if restored and trail.frame(self.p,restored['frame_id'])['kind']=='NAVIGATION':
            archived=trail.frame(self.p,restored['frame_id'])
            data=deepcopy(archived['data']);actions=deepcopy(archived['actions'])
            # Current adopted evidence remains selectable alongside the historical menu.
            existing={c['id'] for c in data['articles']}
            for card in fresh['articles']:
                if card['status']=='ACTIVE' and card['id'] not in existing:
                    data['articles'].append(card);existing.add(card['id'])
                    law=next((l for l in data['laws'] if l['id']==card['law_id']),None)
                    if law is None:
                        law=deepcopy(next(l for l in fresh['laws'] if l['id']==card['law_id']));law['articles']=[];data['laws'].append(law)
                    law['articles'].append(card)
            data['basis']=list({b['id']:b for b in data['basis']+fresh['basis'] if b.get('branch_id') is None or b.get('branch_id') in existing}.values())
            data['branches']=[]
            for card in data['articles']:
                g=self.p['groups'][card['id']];card['status']=g['status'];card['reason']=g['reason']
                refs=[b['id'] for b in data['basis'] if b.get('branch_id')==g['id']]
                card['original_basis_refs']=refs
                data['branches'].append({'id':g['id'],'law_id':g['law_id'],'status':g['status'],'reason':g['reason'],
                    'allowed_decisions':(['KEEP' if g['status']=='ACTIVE' else 'ADOPT','DEFER','EXCLUDE'] if refs else ['DEFER'])})
            data['return_context']=deepcopy(restored);frame_id=archived['id']
        else:
            data=fresh;frame_id=trail.capture(self.p,'NAVIGATION',data,actions=actions,location=self.location())
        for point in trail.points(self.p):
            if point['id']==frame_id:continue
            target=lc.token(self.s,'T',['RETURN_TO',point['id']])
            actions[target]={'id':target,'action':'RETURN_TO','identity':{'frame_id':point['id']},'label':'시점 '+str(point['number'])+' '+point['kind']+' 선택지로 돌아가기'}
            point['return_action']=target
        data['return_points']=trail.points(self.p)
        for point in data['return_points']:
            target=lc.token(self.s,'T',['RETURN_TO',point['id']])
            if target in actions:point['return_action']=target
        data['chain_frame_id']=frame_id;data['investigation_chain']=trail.context(self.p)
        data['adopted_evidence']=[{'branch_id':g['id'],'law_id':g['law_id'],'article':g['hit']['heading'],
            'reason':g['reason'],'basis_refs':[b['id'] for b in self.p['basis_history'].values() if b.get('branch_id')==g['id']]}
            for g in self.p['groups'].values() if g['status']=='ACTIVE']
        data['actions']=[{k:a[k] for k in ('id','action','label')} for a in actions.values()]
        data['presentation_id']=lc.token(self.s,'P',digest(data));self.save()
        return data,actions

    def execute(self, decision, data, actions):
        step=trail.begin(self.p,data,decision,actions)
        self.save()
        try:self.execute_tool(decision,data,actions)
        except Exception:
            step['status']='INTERRUPTED';self.save();raise
        step['status']='APPLIED'
        if decision['next_action']!='RETURN_TO':self.p.pop('revisit',None)
        self.s.repo.event('INVESTIGATION_CHAIN_STEP',step);self.save()

'''
s=s.replace('    def build_view(self):',methods+'    def build_view(self):')
p.write_text(s)
p=C/'law_candidates.py';s=p.read_text().replace("CONTRACT = 'law-candidate-navigation-v2'", "CONTRACT = 'law-candidate-navigation-v3'");p.write_text(s)
