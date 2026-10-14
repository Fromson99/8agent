from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0694/structured-reading/snapshot';B=S/'02_BACKEND/semantic_runtime'
def edit(p,a,b):
 s=p.read_text();assert a in s,(p,a[:100]);p.write_text(s.replace(a,b))
p=B/'legal_agent/law_candidates.py'
edit(p,"'assessment_reentry_limit': 2, 'completion_contract': False}","'assessment_reentry_limit': 2, 'completion_contract': False, 'structure_first': False, 'batch_selected_pages': False}")
edit(p,"    return result\n", "    if any(type(result[k]) is not bool for k in ('structure_first','batch_selected_pages')):\n        raise ContractError('invalid structure/read policy')\n    if result['structure_first'] and result['mode'] != 'law-first-v1':\n        raise ContractError('structure-first requires law navigation')\n    return result\n")
edit(p,"    page = idx.law_groups_page(db, terms, allowed(s), limit=policy(s)['law_page_size'])", "    if policy(s)['structure_first']:\n        return structured_discovery(s, queries, terms)\n    page = idx.law_groups_page(db, terms, allowed(s), limit=policy(s)['law_page_size'])")
p.write_text(p.read_text()+'''

def structured_discovery(s, queries, terms):
    """Titles/coordinates locate sources; never search original bodies here."""
    from . import structure_query as sq
    routes = [sq.resolve(q, s.matcher, s.scope) for q in [s.context.request['question'], *queries]]
    directory = sq.catalogue(s.matcher, s.scope, queries=[s.context.request['question'], *queries],
        limit=policy(s)['law_page_size'])
    pairs = {(p['document_id'], str(p['unit_id'])): p for r in routes if r['status']=='MATCH' for p in r['pairs']}
    hits=[]
    for did,uid in pairs:
        for sid in s.matcher._unit_sources(did,uid):
            if sid not in allowed(s):raise ContractError('structured source outside request scope')
            hits.append(structure_hit(s,sid,uid))
    hits=list({(h['key'],h.get('requested_unit_id')):h for h in hits}.values())
    docs=list(dict.fromkeys([r['document_id'] for r in directory['items']]+[did for did,_ in pairs]))
    page={'items':[{'document_id':did,'article_count':None,'unit_count':None} for did in docs],
        'total':len(docs),'next_cursor':None}
    idx,_=index(s)
    catalogue={'contract':CONTRACT,'terms':terms,'queries':queries,'law_page':page,
        'query_fingerprint':digest({'terms':terms,'queries':queries,'scope':sorted(s.scope),
            'index':idx.manifest['index_sha256'],'search_policy':'structure-first-scoped-v1'}),
        'index_sha256':idx.manifest['index_sha256'],'search_policy':'structure-first-scoped-v1'}
    selected=list(dict.fromkeys(h['source_id'] for h in hits))
    s.repo.event('LAW_STRUCTURE_DIRECTORY',directory)
    return selected,{'discovery_mode':'structure','law_navigation':catalogue,'structure_catalogue':directory,
        'unit_hits':hits,'unit_index_sha256':idx.manifest['index_sha256'],'selected_for_read':selected,
        'discovered':selected,'routes':{},'queries':[], 'structure_query':{'status':'MATCH' if pairs else 'MISS',
        'pairs':list(pairs.values()),'source_ids':selected,'query_routes':routes},'parent_selections_preserved':True}


def fulltext_scope_keys(session, document_id, unit_id=None):
    """Resolve selected metadata scope to indexed units before lexical ranking."""
    import json
    from .structure_query import document_tree
    if document_id not in session.scope:raise ContractError('fulltext document outside request scope')
    tree=document_tree(session.matcher,document_id)
    if unit_id is None:units=set(tree['nodes'])
    else:
        unit_id=str(unit_id)
        if unit_id not in tree['nodes']:raise ContractError('fulltext subtree is not stored')
        units=set();todo=[unit_id]
        while todo:
            uid=todo.pop()
            if uid in units:continue
            units.add(uid);todo.extend(tree['children'].get(uid,[]))
    idx,db=index(session);idx.check_unchanged()
    rows=db.execute('SELECT key,source_id FROM unit WHERE document_id=? AND json_extract(json,\'$.unit_id\') IN (SELECT value FROM json_each(?))',
                    (document_id,json.dumps(sorted(units)))).fetchall()
    permitted=allowed(session)
    return frozenset(key for key,sid in rows if sid in permitted)
''')
p=B/'unit_fulltext.py'
edit(p,'def _page_query(self, terms, allowed, cursor, limit, kind, identity=None):','def _page_query(self, terms, allowed, cursor, limit, kind, identity=None, unit_keys=None):')
edit(p,"'scope': sorted(scope), 'kind': kind, 'identity': identity}","'scope': sorted(scope), 'kind': kind, 'identity': identity,\n                          **({'unit_keys':sorted(set(unit_keys))} if unit_keys is not None else {})}")
edit(p,"        return where, params, binding, offset, bool(terms and scope)","        if unit_keys is not None:\n            where += ' AND u.key IN (SELECT value FROM json_each(?))'; params.append(json.dumps(sorted(set(unit_keys))))\n        return where, params, binding, offset, bool(terms and scope and (unit_keys is None or unit_keys))")
for method,lim in [('law_groups_page',12),('article_groups_page',8),('hit_page',16)]:
 s=p.read_text();start=s.index('    def '+method);end=s.index('\n    def ',start+5) if '\n    def ' in s[start+5:] else len(s)
 part=s[start:end].replace(f'limit={lim}):',f'limit={lim}, unit_keys=None):')
 for kind,ident in [('laws',''),('articles',', document_id'),('hits',', source_id')]:
  part=part.replace(f"'{kind}'{ident})",f"'{kind}'{ident}, unit_keys=unit_keys)")
 part=part.replace('projection = self._projection(db, terms, allowed)','projection = self._projection(db, terms, allowed) if unit_keys is None else None')
 p.write_text(s[:start]+part+s[end:])
p=B/'legal_agent/unit_reading.py'
edit(p,'    reads=[]\n    for h in hits:',"    reads=[]\n    unique={(h['key'],h.get('requested_unit_id')):h for h in hits}\n    for h in unique.values():")
p=B/'legal_agent/law_navigation.py'
edit(p,'본문 표현의 추가 검색이 필요하면 RESEARCH로 fulltext 검색한다.', '구조 우선 정책에서는 먼저 SEARCH_STRUCTURE로 문서명·제목·번호를 찾고 목차를 본다.\n본문 표현의 추가 검색은 선택한 문서나 현재 하위 목차의 SEARCH_BODY로만 한다. OPEN_LAW도 표시된 구조 범위 안에서만 검색한다.\nRESEARCH는 구조 검색어를 다시 정한다. 구조 조회 실패를 전체 본문 검색으로 우회하지 않는다.')
edit(p,"if kind == 'RESEARCH' else", "if kind in ('RESEARCH','SEARCH_BODY') else")
edit(p,"INVESTIGATIVE_ACTIONS = {'RESEARCH',", "INVESTIGATIVE_ACTIONS = {'RESEARCH', 'SEARCH_BODY',")
edit(p,"self.p.setdefault('window', 'search')", "self.p.setdefault('window', 'structure' if self.policy['structure_first'] else 'search')")
edit(p,"        self.p.setdefault('structure_location', None)","        self.p.setdefault('structure_location', None)\n        self.p.setdefault('fulltext_scopes', {})\n        self.p.setdefault('fulltext_queries', {})")
edit(p,"            self.p['structure_page'] = sq.catalogue(self.s.matcher, self.s.scope,", "            self.p['structure_page'] = record.get('structure_catalogue') or sq.catalogue(self.s.matcher, self.s.scope,")
edit(p,"            self.p['article_pages'] = {}; self.p['hit_pages'] = {}", "            self.p['article_pages'] = {}; self.p['hit_pages'] = {}\n            self.p['fulltext_scopes'] = {}; self.p['fulltext_queries'] = {}\n            if self.policy['structure_first']:self.p['structure_page']=record['structure_catalogue']")
edit(p,"            self.p['window']='search'; self.p['window_groups']=[];", "            self.p['window']='structure' if self.policy['structure_first'] else 'search'; self.p['window_groups']=[];")
edit(p,"        did=law['document_id'];key=digest([self.p['catalogue']['query_fingerprint'],did,self.p.get('article_pages',{}).get(did)])", "        did=law['document_id']\n        if self.policy['structure_first'] and did not in self.p['fulltext_scopes']:return []\n        key=digest([self.p['catalogue']['query_fingerprint'],did,self.p.get('article_pages',{}).get(did),self.p['fulltext_scopes'].get(did),self.p['fulltext_queries'].get(did)])")
edit(p,"self.idx.article_groups_page(self.db,self.p['catalogue']['terms'],did,lc.allowed(self.s),limit=8)","self.idx.article_groups_page(self.db,self.fulltext_terms(did),did,lc.allowed(self.s),limit=8,**self.fulltext_args(did))")
edit(p,"self.idx.hit_page(self.db,self.p['catalogue']['terms'],sid,lc.allowed(self.s),limit=3)","self.idx.hit_page(self.db,self.fulltext_terms(did),sid,lc.allowed(self.s),limit=3,**self.fulltext_args(did))")
edit(p,"'structure_location','opened_law'", "'structure_location','fulltext_scopes','fulltext_queries','opened_law'")
edit(p,"            law['open_action'] = offer('OPEN_LAW', {'document_id': law['document_id']}, law['name']+'의 fulltext 적중 조별 후보 보기')\n",'')
edit(p,"            law['document_structure'] = tree", "            law['document_structure'] = tree\n            location={'document_id':did, **({'unit_id':uid} if self.policy['structure_first'] else {})}\n            law['open_action'] = offer('OPEN_LAW',location,law['name']+' 현재 구조 범위의 본문 검색 결과 보기')\n            if self.policy['structure_first']:\n                law['body_search_action']=offer('SEARCH_BODY',location,law['name']+' 현재 구조 범위 안에서 본문 표현 검색')")
edit(p,"        if search_window and self.p['law_page']['next_cursor']:","        if not self.policy['structure_first'] and search_window and self.p['law_page']['next_cursor']:")
edit(p,"{'document_id': did, 'cursor': page['next_cursor']}","{'document_id': did, 'cursor': page['next_cursor'], **({'unit_id':self.p['fulltext_scopes'][did]} if self.policy['structure_first'] else {})}")
edit(p,"'허용된 전체 문서 범위에서 새 검색'", "'법령명·조문 제목·번호로 구조 검색을 다시 시작' if self.policy['structure_first'] else '허용된 전체 문서 범위에서 새 검색'")
edit(p,"        elif kind == 'NEXT_LAWS':\n", "        elif kind == 'NEXT_LAWS':\n            if self.policy['structure_first']:raise ContractError('global fulltext disabled by structure-first policy')\n")
edit(p,"        elif kind in ('OPEN_LAW', 'NEXT_ARTICLES'):\n            did = identity['document_id']", "        elif kind in ('OPEN_LAW', 'NEXT_ARTICLES','SEARCH_BODY'):\n            did = identity['document_id']\n            if self.policy['structure_first']:\n                if did not in self.s.scope:raise ContractError('fulltext selection outside request scope')\n                uid=identity.get('unit_id')\n                lc.fulltext_scope_keys(self.s,did,uid)\n                if kind == 'NEXT_ARTICLES' and (did not in self.p['fulltext_scopes'] or self.p['fulltext_scopes'][did]!=uid):\n                    raise ContractError('fulltext continuation scope changed')\n                if kind != 'NEXT_ARTICLES':\n                    self.p['article_pages'].pop(did,None)\n                    self.p['hit_pages']={sid:v for sid,v in self.p['hit_pages'].items() if self.s.tools.sources[sid]['document_id']!=did}\n                    self.p['fulltext_scopes'][did]=uid\n                    self.p['fulltext_queries'][did]=(sorted({t for q in decision['queries'] for t in lc.question_terms(q)}) if kind=='SEARCH_BODY' else self.p['catalogue']['terms'])\n                self.s.repo.event('LAW_SCOPED_FULLTEXT',{'document_id':did,'unit_id':uid,'queries':decision.get('queries',[]),'index_sha256':self.idx.manifest['index_sha256']})")
edit(p,"self.p['structure_location'] = {'document_id': did, 'unit_id': None, 'offset': 0}","self.p['structure_location'] = {'document_id': did, 'unit_id': identity.get('unit_id'), 'offset': 0}")
edit(p,"page = self.idx.article_groups_page(self.db, self.p['catalogue']['terms'], did, lc.allowed(self.s),\n                cursor=identity.get('cursor'), limit=self.policy['article_page_size'])", "page = self.idx.article_groups_page(self.db, self.fulltext_terms(did), did, lc.allowed(self.s),\n                cursor=identity.get('cursor'), limit=self.policy['article_page_size'], **self.fulltext_args(did))")
edit(p,"page = self.idx.hit_page(self.db, self.p['catalogue']['terms'], sid, lc.allowed(self.s), cursor=cursor, limit=limit)","did=self.s.tools.sources[sid]['document_id']\n        page = self.idx.hit_page(self.db, self.fulltext_terms(did), sid, lc.allowed(self.s), cursor=cursor, limit=limit, **self.fulltext_args(did))")
edit(p,"    def open_hits(self, sid, cursor, limit):",'''    def fulltext_args(self, did):
        if not self.policy['structure_first']:return {}
        if did not in self.p['fulltext_scopes']:raise ContractError('fulltext requires explicit structured document selection')
        return {'unit_keys':lc.fulltext_scope_keys(self.s,did,self.p['fulltext_scopes'][did])}

    def fulltext_terms(self, did):
        return self.p['fulltext_queries'].get(did,self.p['catalogue']['terms'])

    def open_hits(self, sid, cursor, limit):''')
# Persist exact selected targets and completed substeps; replay uses the same plan.
edit(p,"        if kind == 'READ_ARTICLES':\n            ids=[]\n            for target in decision['targets']:",'''        if kind == 'READ_ARTICLES':
            identities=[actions[t]['identity'] for t in decision['targets']]
            plan_id=digest({'binding':self.p['binding'],'targets':identities,'issues':decision.get('issue_refs',[]),
                'gaps':self.p.get('assessment_gaps',[]),'turn':self.p['turn']})
            plan=self.p.setdefault('read_plans',{}).setdefault(plan_id,{'binding':self.p['binding'],
                'state_version':self.p.get('state_version'),'targets':deepcopy(identities),'completed':{},'status':'STARTED'})
            self.save();ids=[]
            for target in decision['targets']:
                if target in plan['completed']:
                    ids.append(plan['completed'][target]);continue''')
edit(p,"                self.execute_tool({**decision,'law_decisions':[],'branch_decisions':[],'next_action':'READ_PARENT','targets':[handle]}, {'sources':[]},temp)\n                ids.append(gid)","                if gid not in plan['completed'].values():\n                    try:self.execute_tool({**decision,'law_decisions':[],'branch_decisions':[],'next_action':'READ_PARENT','targets':[handle]}, {'sources':[]},temp)\n                    except Exception:\n                        plan['status']='INTERRUPTED';plan['remaining_target']=target;self.save();raise\n                plan['completed'][target]=gid;plan['status']='STARTED';self.save()\n                ids.append(gid)")
edit(p,"            self.p['window']='read';self.p['window_groups']=ids", "            plan['status']='ACQUIRED';plan.pop('remaining_target',None);self.save()\n            self.p['window']='read';self.p['window_groups']=list(dict.fromkeys(ids))")
# Enable only in the explicit candidate serving profile.
p=S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json';v=json.loads(p.read_text());v['candidate_navigation'].update(structure_first=True,batch_selected_pages=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print('Applied structured-search and resumable-read candidate')
