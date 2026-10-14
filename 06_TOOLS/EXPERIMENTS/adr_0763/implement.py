from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0763/recovery/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=C/'law_navigation.py';s=p.read_text()
def replace(old,new):
 global s
 assert old in s,old[:80]
 s=s.replace(old,new,1)
helper='''SEARCH_RECOVERY_CONTRACT = 'request-search-recovery-v1'


def request_scope_view(question, matcher, scope):
    """Conservative navigation scope from literal request, never reading focus.

    A unique named document is a recovery target, not an authority grant. Only
    explicit single-coordinate-only syntax becomes a hard subtree constraint.
    Ambiguity stays UNKNOWN; unresolved headings do not erase a named document.
    """
    from lawrag.core.legal_coordinate import find_coordinates
    out = {'status': 'UNKNOWN', 'document_id': None, 'unit_id': None,
           'quote_span': None, 'reason': 'NO_UNIQUE_REQUEST_DOCUMENT', 'hard_bound': False}
    hits = sq.document_hits(question, matcher)
    docs = {d for h in hits for d in h['values']}
    if len(docs) != 1 or not docs <= set(scope): return out
    did = next(iter(docs)); hit = next(h for h in hits if did in h['values'])
    out.update(document_id=did, quote_span={'start':hit['start'], 'end':hit['end'],
        'text':question[hit['start']:hit['end']]})
    # Explicitly excluded/contrasted names and multiple coordinate references do
    # not establish a new wide recovery scope. Existing bounded tools remain.
    if re.match(r'\\s*(?:은|는|을|를)?\\s*(?:제외|빼고|말고|아닌)', question[hit['end']:]):
        return {**out, 'reason':'EXCLUDED_OR_CONTRASTED_DOCUMENT'}
    mentions = find_coordinates(question)
    if mentions:
        if len(mentions) != 1: return {**out, 'reason':'AMBIGUOUS_REQUEST_COORDINATES'}
        mention = mentions[0]
        suffix = question[mention.end:]
        only = re.match(r'\\s*(?:(?:의\\s*)?(?:안|내|범위)(?:에서|에)?\\s*만|에서만|만)(?!큼)', suffix)
        if not only: return {**out, 'reason':'COORDINATE_MENTION_NOT_EXPLICIT_BOUND'}
        prefix = question[:mention.end]
        route = sq.resolve(prefix, matcher, scope, document_id=did)
        if route.get('status') != 'MATCH' or len(route.get('pairs', [])) != 1:
            return {**out, 'reason':'UNRESOLVED_REQUEST_COORDINATE'}
        pair = route['pairs'][0]
        if pair['document_id'] != did: return out
        # Do not treat a negatively requested subtree as a positive bound.
        if re.search(r'제외|빼고|아닌|말고|비교', question[:mention.end+only.end()]):
            return {**out, 'reason':'AMBIGUOUS_REQUEST_RESTRICTION'}
        end = mention.end+only.end()
        return {**out, 'status':'BOUND', 'unit_id':str(pair['unit_id']),
                'quote_span':{'start':hit['start'],'end':end,'text':question[hit['start']:end]},
                'reason':'EXPLICIT_SINGLE_SUBTREE_ONLY', 'hard_bound':True}
    return {**out, 'status':'BOUND', 'reason':'UNIQUE_NAMED_DOCUMENT'}


'''
replace('class Investigation:\n',helper+'class Investigation:\n')
replace("self.idx, self.db = lc.index(session); self.policy = lc.policy(session)","self.idx, self.db = lc.index(session); self.policy = lc.policy(session)\n        self.request_scope = request_scope_view(question, session.matcher, session.scope)")
replace("'index': self.idx.manifest['index_sha256'], 'policy': self.policy})","'index': self.idx.manifest['index_sha256'], 'policy': self.policy,\n            'search_recovery': SEARCH_RECOVERY_CONTRACT, 'request_scope':self.request_scope})")
methods='''    def scope_allows(self, action):
        """Same constraint for fresh/replayed menus and validation before I/O."""
        bound = self.request_scope
        if not bound['hard_bound']: return True
        kind, identity = action['action'], action['identity']
        if kind in ('RESEARCH','NEXT_LAWS','FOLLOW_CONNECTION'): return False
        if kind in ('SEARCH_STRUCTURE','OPEN_STRUCTURE','NEXT_STRUCTURE'):
            return identity.get('document_id') == bound['document_id']
        if kind not in ('SEARCH_BODY','OPEN_LAW','NEXT_ARTICLES','NEXT_HITS',
                        'READ_ARTICLES','READ_PARENT','READ_SCOPE','VIEW_SAVED_SOURCE'): return True
        did, uid = identity.get('document_id'), identity.get('unit_id')
        if kind in ('READ_PARENT','READ_SCOPE','VIEW_SAVED_SOURCE'):
            group = self.p['groups'].get(identity.get('branch_id'))
            if not group: return False
            did = group['hit']['document_id']
            if kind == 'READ_SCOPE':
                offer = next((o for o in ur.offers(self.s, group['hit']) if o['id']==identity.get('scope')), None)
            elif kind == 'VIEW_SAVED_SOURCE' or identity.get('continuation'):
                offer = self.p['selected'].get(group['id'],{}).get('offer')
            else: offer = group['offer']
            uid = offer.get('unit_id') if offer else None
        if kind == 'NEXT_HITS':
            source = self.s.tools.sources.get(identity.get('source_id'),{})
            did = source.get('document_id'); uid = self.p.get('fulltext_scopes',{}).get(did)
        if did != bound['document_id'] or uid is None: return False
        # Parent links prove containment, including sub-article originals.
        seen = set(); uid = str(uid)
        while uid not in seen:
            if uid == bound['unit_id']: return True
            seen.add(uid); parent = self.s.matcher.units.get((did,uid),{}).get('parent')
            if parent is None: break
            uid = str(parent)
        return False

    def search_status(self):
        """Projection from existing accepted action receipts, no second ledger."""
        memory = trail.state(self.p); first = memory['frames'].get(memory.get('entry_frame_id'),{}).get('data',{})
        previous = first.get('search_status',{}).get('attempts',[])
        if previous:
            initial = deepcopy(previous[0])
        elif not memory['steps']:
            page = self.record.get('structure_catalogue') or {}
            initial = {'ref':'ENTRY', 'mode':self.record.get('discovery_mode','UNKNOWN').upper(),
                'scope':{'document_ids':sorted(self.s.scope)},
                'queries':list(self.record['law_navigation'].get('queries',[])), 'status':'COMPLETED',
                'result':{'total':page.get('total') if self.record.get('discovery_mode')=='structure'
                          else self.record['law_navigation']['law_page'].get('total'),
                          'resolutions':[{k:r[k] for k in ('status','reason','failure') if k in r}
                                         for r in page.get('resolutions',[])]}}
        else:
            initial = {'ref':'ENTRY','mode':'UNKNOWN','scope':None,'queries':first.get('search_queries',[]),
                       'status':'UNKNOWN','result':None}
        attempts = [initial]
        for step in memory['steps']:
            if step['action'] not in ('RESEARCH','SEARCH_STRUCTURE','SEARCH_BODY'): continue
            target = (step.get('targets') or [{}])[0].get('identity',{})
            mode = 'STRUCTURE' if step['action']=='SEARCH_STRUCTURE' or (step['action']=='RESEARCH'
                and self.policy['structure_first'] and not self.policy['selectable_search']) else 'FULLTEXT'
            attempts.append({'ref':step['id'],'mode':mode,'scope':deepcopy(target),
                'queries':list(step.get('queries',[])),'status':step['status'],
                'result':deepcopy(step.get('search_result') or step.get('structure_lookup') or step.get('outcome'))})
        resolutions = self.p['structure_page'].get('resolutions',[])
        return {'contract':SEARCH_RECOVERY_CONTRACT, 'request_scope':deepcopy(self.request_scope),
            'focus_scope':deepcopy(self.p.get('structure_location')),
            'document_match':'MATCH' if self.request_scope['document_id'] else 'UNKNOWN',
            'heading_resolution':[{'status':r.get('status','UNKNOWN'),
                'reason':r.get('reason'), 'failure':r.get('failure')} for r in resolutions],
            'attempts':attempts, 'history_complete':initial['mode']!='UNKNOWN',
            'rule':'Document match and heading resolution are separate. A read is not a body search; '
                   'different mode or scope is a different search. Untried is not an empty result.'}

'''
replace('    @latency.timed(\'law.select.build_view\')\n',methods+"    @latency.timed('law.select.build_view')\n")
replace("if self.recovery_blocked(value): return None","if self.recovery_blocked(value) or not self.scope_allows(value): return None")
replace("law['body_search_action']=offer('SEARCH_BODY',location,law['name']+' 현재 구조 범위 안에서 본문 표현 검색')", """law['body_search_action']=offer('SEARCH_BODY',location,law['name']+' 현재 읽기 위치 '+(sq.node_label(self.s.matcher,did,uid).get('coordinate') or str(uid) if uid is not None else '문서 전체')+' 안에서 본문 검색')
                bound=self.request_scope
                if bound['status']=='BOUND' and bound['document_id']==did:
                    request_location={'document_id':did,'unit_id':bound['unit_id']}
                    law['request_body_search_action']=offer('SEARCH_BODY',request_location,
                        law['name']+' 요청 범위 '+('문서 전체' if bound['unit_id'] is None else sq.node_label(self.s.matcher,did,bound['unit_id']).get('coordinate') or str(bound['unit_id']))+'에서 본문 검색')
                law['body_search_scopes']=[{'target':t,'document_id':actions[t]['identity']['document_id'],
                    'unit_id':actions[t]['identity'].get('unit_id'),
                    'role':'REQUEST' if t==law.get('request_body_search_action') else 'FOCUS'}
                    for t in dict.fromkeys([law.get('request_body_search_action'),law['body_search_action']]) if t]""")
replace("data = {'question': self.question, 'issues':", "data = {'search_status':self.search_status(), 'question': self.question, 'issues':")
# Enforce on actions restored from history or added later by recovery helpers too.
replace("investigation_scope.annotate(data,self.question)\n", """investigation_scope.annotate(data,self.question)
        data['search_status']=self.search_status()
        for target in list(actions):
            if not self.scope_allows(actions[target]): del actions[target]
        data['actions']=[row for row in data['actions'] if row['id'] in actions]
""")
replace("kind = value['next_action']; targets = value['targets']", """kind = value['next_action']; targets = value['targets']
        if any(not self.scope_allows(actions[target]) for target in targets):
            raise ProposalError('action outside explicit request subtree')""")
# Body searches have their own identity+query guard; the generic action-only guard
# must not forbid a new query through the same current target.
replace("'SEARCH_STRUCTURE', 'OPEN_STRUCTURE', 'BROWSE_STRUCTURE') and not data.get('return_context'):","'SEARCH_STRUCTURE', 'OPEN_STRUCTURE', 'BROWSE_STRUCTURE', 'SEARCH_BODY') and not data.get('return_context'):")
replace("if decision['next_action']=='FINISH' and self.control:","""if decision['next_action']=='SEARCH_BODY':
            did=actions[decision['targets'][0]]['identity']['document_id']
            page=self.p['article_pages'][did]
            step['search_result']={'total':page.get('total'),'presented':len(page.get('items',[])),
                'has_more':bool(page.get('next_cursor'))}
        if decision['next_action']=='FINISH' and self.control:""")
replace("'reads_acquired': len(self.record.get('unit_reads', []))}","'reads_acquired': len(self.record.get('unit_reads', []))}\n        step['search_result']=deepcopy(step['outcome'])")
replace("value=deepcopy({k:v for k,v in data.items() if k!='articles'})", """value=deepcopy({k:v for k,v in data.items() if k!='articles'})
        if value.get('search_status'):
            for key in ('previous_search_queries','search_expression_history','structure_search_history'):
                value.pop(key,None)""")
replace("instructions = {'attempt': 1", """if str(error)=='no adopted originals for completion':
        conflicts.append({'code':'NO_ADOPTED_ORIGINALS', 'corrections':[
            '현재 원문이 실제 사용자 요구를 뒷받침할 때만 ADOPT한다. 오류를 없애려고 무관한 원문을 채택하지 않는다.',
            '잘못된 조문을 읽었으면 search_status의 방식·범위를 보고 아직 시도하지 않은 요청 범위 검색 또는 관련 원문 READ를 선택한다.',
            '허용된 조사로도 필요한 근거를 구할 수 없으면 PENDING으로 한계를 남긴다. FINISH는 부재를 추측하는 도구가 아니다.']})
    instructions = {'attempt': 1""")
replace('관련 후보를 찾았고 read_action이 있으면 그 원문을 바로 읽는다.', '제목·위치가 질문의 대상·행위·세부 요구와 실제로 맞는 후보에 read_action이 있으면 바로 읽는다. read_action의 존재는 관련성 증명이 아니다.')
replace('같은 검색·거절된 결정을 반복하지 말고 previous_search_queries/search_expression_history/recent_rejections를 확인한다.', 'search_status의 mode·scope·result와 recent_rejections를 확인한다. 동일 표현이어도 STRUCTURE와 FULLTEXT, 문서 전체와 현재 조문은 다른 검색이다. 동일 방식·범위·표현의 반복만 피한다.')
replace('목록은 일부 후보만 보여준다.', 'search_status.document_match=MATCH여도 heading_resolution이 MISS면 요청한 조항은 아직 찾지 못했다. 읽은 조문이 무관하면 request_body_search_action의 요청 범위 본문 검색 등 아직 시도하지 않은 경로로 복구한다. 원하는 내용을 같은 문서 안에서 찾는 것은 질문을 벗어난 추가 조문 조사가 아니다. 본문 미검색은 본문 결과 0건이나 문서 부재가 아니다. 관련 원문을 이미 찾았으면 검색을 더 할 의무는 없다.\n목록은 일부 후보만 보여준다.')
p.write_text(s)
p=C/'request_entry.py';s=p.read_text();needle='FULLTEXT 전에 STRUCTURE를 반드시 거칠 필요가 없다.';assert needle in s;s=s.replace(needle,needle+' 문서명을 알아도 원하는 조문번호·정확한 제목을 모르면, 대상·행위·신고 내용 등 본문 단서로 FULLTEXT를 선택할 수 있다. 문서명만으로 STRUCTURE를 고정하지 않는다.');p.write_text(s)
p=C/'investigation_scope.py';s=p.read_text();needle='검색 실패는 부재 증명이 아니며 제시된 다른 경로를 고른다.';assert needle in s;s=s.replace(needle,needle+' 잘못된 조문을 읽은 뒤 요청된 내용을 찾기 위한 문서 범위 본문 검색은 DIRECT이며 무관한 추가 조사가 아니다.');p.write_text(s)
print('Candidate A implemented (3 product files); title matcher/cache unchanged')
