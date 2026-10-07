"""V3 exploration on the existing source reader, with bounded durable policy tasks."""
import json
import logging
import sqlite3
import time
from contextlib import nullcontext
from itertools import islice
from ..contracts import digest
from .. import observability as obs
from . import relations_protocol as protocol
from .exploration_tools import ExplorationTools
from .workflow_relation_cards import RelationCards
from .repository import encoded, text_hash
from .errors import BudgetExhausted, DeadlineExceeded, ContractError, ProposalError, ToolExecutionError

FAMILIES = ('reference','definition','term','occurrence','structure','knowledge')
search_log = obs.get_logger('fulltext_tool')


class RelationsTools(ExplorationTools):
    def __init__(self, *args):
        super().__init__(*args)
        self.handlers = {name: getattr(self, name) for name in protocol.REGISTRY}
        self.capabilities.update({name: True for name in self.handlers})
        with obs.step(search_log, 'sources.relation_cards'):
            self.cards = RelationCards(self)
        glossary_value=getattr(self.glossary, '_value', self.glossary)
        lexical_available=getattr(glossary_value, '_lexical_observations_available', None)
        if lexical_available is None:
            with obs.step(search_log, 'sources.lexical_schema', cache_hit=False):
                tables={r[0] for r in self.glossary.dbs['dictionary'].execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sense_assertion','sense_candidate')")}
                lexical_available={'sense_assertion','sense_candidate'}<=tables
                glossary_value._lexical_observations_available=lexical_available
        else:
            obs.event(search_log, 'sources.lexical_schema.cached', cache_hit=True)
        self.capabilities['lexical_observations']='AVAILABLE' if lexical_available else 'UNAVAILABLE_IN_SELECTED_GLOSSARY'
        self._draining = False
        self._actor = 'MODEL'
        self._view_id = None
        self._candidate_evidence = None
        self._candidate_cache_active = False

    def resolve(self, ident, kinds='RFDUPELTK'):
        if isinstance(ident,str) and ident.startswith('K') and 'K' in kinds:
            row=self.repo.db.execute("SELECT identity_json,binding_hash FROM navigation_handle WHERE handle=? AND kind='K'",(ident,)).fetchone()
            if not row or row['binding_hash']!=self.context.binding_hash: raise ProposalError('unknown concept handle')
            return json.loads(row['identity_json'])
        return super().resolve(ident, kinds)

    def validate_action(self, action, offered=None):
        protocol.validate('ToolAction', action)
        if set(action['question_refs']) - {q['id'] for q in self.context.pieces}:
            raise ProposalError('unknown action question reference')
        args = action['args']
        if action['tool']=='read' and args['target'].startswith(('R','F')):
            raise ProposalError('READ requires a D/P/U document or location, or E evidence; '+args['target']+
                ' is a corpus/folder. Use locate(locator="document name and article", target="'+args['target']+
                '", branch="any", cursor=null), or search within that target; then READ a returned target with cursor=null.')
        if action['tool']=='inspect_relation':
            self.repo.notice(args['relation_id'])
            if offered is not None and args['relation_id'] not in offered:
                raise ProposalError('relation was not offered in this view')
        if action['tool']=='view_page' and offered is not None and args['cursor'] not in offered:
            raise ProposalError('continuation was not offered in this view')
        for ident in [args[k] for k in ('target','evidence') if k in args]+args.get('terms',[]):
            self.resolve(ident)
            if offered is not None and ident not in offered:
                raise ProposalError('handle was not offered in this view: '+ident)
        if 'target' in args:
            kinds = 'ETK' if action['tool']=='follow_relations' else 'DUPE' if action['tool']=='read' else 'RFDUPE' if action['tool']=='browse' else 'RFDU'
            self.resolve(args['target'], kinds)
        if 'evidence' in args: self.resolve(args['evidence'], 'E')
        for t in args.get('terms',[]): self.resolve(t,'T')
        if action['tool']=='search' and args['mode']=='fulltext' and not self.capabilities['fulltext']:
            raise ProposalError('fulltext unavailable')
        if action['tool']=='read' and args['target'].startswith('D') and args['extent']=='article':
            raise ProposalError('READ target '+args['target']+' is a whole document, not an article unit. '
                'Use locate(locator="article number or heading", target="'+args['target']+'", branch="body", cursor=null) '
                'then READ the returned P/U read_action; or READ this document with extent="subtree", cursor=null for its first page.')
        self.source.cursor_position(action)

    def page_token(self, section, items):
        key=digest({'tool':'view_page','args':{'section':section}})
        return self.source.cursor(key, {'items':items})

    def view_page(self, args, offset):
        if not isinstance(offset,dict) or not offset.get('items'):
            raise ProposalError('use the view_page action supplied in continuations')
        # One saved item at a time; a subsequent view offers the remaining snapshot.
        items=offset['items']; page=items[:1]
        evidence=[self.repo.evidence(e['evidence']) for e in page] if args['section']=='exact_evidence' else []
        return page,{'items':items[1:]} if len(items)>1 else None,evidence,{'view_section':args['section']}

    def inspect_relation(self,args,offset):
        return [self.repo.notice(args['relation_id'])],None,[],{}

    def block_ids(self, n):
        if n.get('block_ids') is not None: return n['block_ids']
        if n.get('source_id'): return [b['block_id'] for b in self.tools.sources[n['source_id']]['blocks']]
        did, uid = n['document_id'], n.get('unit_id')
        bounds = self.matcher.units[(did,str(uid))]['span'] if uid is not None else None
        return [r[0] for r in self.store.db.execute('SELECT block_id FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)', (did,))
                if not bounds or bounds[0]<=int(r[0])<bounds[1]]

    def preview(self, n, *, query=None, preferred=None):
        ids = self.block_ids(n); chosen = None; basis = 'LEADING_SOURCE'; total = 0
        for bid in ids:
            raw = self.store.source(n['document_id'],bid)
            total += len(raw['text'])
            if chosen is None: chosen = (raw,0)
            if preferred and bid==preferred.get('block_id'):
                chosen=(raw,preferred['start_cp']); basis='VERIFIED_WITNESS'; preferred=None
            if query and query in raw['text']:
                chosen=(raw,max(0,raw['text'].index(query)-60)); basis='EXACT_LITERAL_MATCH'; query=None
        spans=[]
        if chosen:
            raw,start=chosen; end=min(len(raw['text']),start+self.profile['preview_chars'])
            if end>start:
                spans=[{'block_id':raw['block_id'],'start_cp':start,'end_cp':end,'text':raw['text'][start:end],
                        'block_hash':text_hash(raw['text']),'span_hash':text_hash(raw['text'][start:end])}]
        chars=sum(len(p['text']) for p in spans)
        return {'preview_spans':spans,'preview_hash':digest([n,spans,self.context.binding_hash]),
                'preview_basis':basis,'source_chars':total,'preview_chars':chars,
                'preview_complete':chars==total,'truncated':chars<total,'suppressed_reason':None}

    def candidate(self, n, *, route=None, query=None):
        n={k:v for k,v in n.items() if k!='unit_path'}
        target=self.handle('P' if n.get('source_id') or n.get('block_ids') else 'U',n)
        if route: self.repo.db.execute('INSERT OR IGNORE INTO candidate_route VALUES(?,?)',(target,route))
        unit=self.matcher.units.get((n['document_id'],str(n.get('unit_id'))),{})
        ids=set(self.block_ids(n))
        if not self._candidate_cache_active or self._candidate_evidence is None:
            self._candidate_evidence = self.repo.evidence()
        read=[e['evidence_id'] for e in self._candidate_evidence if e['document_id']==n['document_id'] and ids & {p['block_id'] for p in e['spans']}]
        return {'target':target,'candidate_id':target,'document_name':self.matcher.documents[n['document_id']],
            'title':unit.get('title',''),'coordinate':unit.get('coordinate_key'),
            **self.location(target),**self.preview(n,query=query),'content_read':bool(read), 'evidence_ids':read,
            'citation_eligible':False,'candidate_decision':self.decision(target),
            'routes':[r[0] for r in self.repo.db.execute('SELECT route FROM candidate_route WHERE candidate=?',(target,))],
            'read_action':{'tool':'read','args':{'target':target,'extent':'subtree','cursor':None},
                           'purpose_required':True}}

    def node_card(self, did, uid, *, source_id=None, route=None):
        query=None
        if route:
            r=self.resolve(route,'L')
            if r.get('mode')=='literal': query=r.get('query')
        return self.candidate({'document_id':did,'unit_id':str(uid) if uid is not None else None,
                               'source_id':source_id},route=route,query=query)

    def search(self,args,offset):
        self._search_stage='execute'
        if args['mode']!='fulltext': return super().search(args,offset)
        from ..fulltext import question_terms, thread_snapshot, thread_delta, DIAGNOSTIC_REVISION
        self._search_stage='fulltext_tool.tokenize'
        with obs.step(search_log,'fulltext_tool.tokenize'):
            terms=question_terms(args['query'])
        self._search_stage='fulltext_tool.scope'
        with obs.step(search_log,'fulltext_tool.scope'):
            docs,bounds=self.docs_bounds(args['target'])
            allowed=set(self.sources_in(args['target']))
        self._search_stage='fulltext_tool.rank'
        with obs.step(search_log,'fulltext_tool.rank',term_count=len(terms),allowed_count=len(allowed)):
            db=self.matcher.fulltext_db
            # Slow NFS queries share the whole request budget. Do not abort a
            # valid FTS query after an independent 20-second local timer.
            db.set_progress_handler(lambda:int(time.monotonic()>=self.context.deadline),1000)
            ids=self.matcher.fulltext.rank(db,terms,allowed)
        self._search_stage='fulltext_tool.materialize'
        with obs.step(search_log,'fulltext_tool.location_mapping',result_count=len(ids)):
            measure=getattr(self.tools.sources,'measure_loads',None)
            with (measure() if measure else nullcontext(None)) as loads:
                before=thread_snapshot();locations={};completed=False;bounds_tokenize_ms=0.0
                route_handle_ms=0.0
                try:
                    t=time.perf_counter()
                    route=self.handle('L',{'kind':'search','query':args['query'],'target':args['target'],'mode':'fulltext'})
                    route_handle_ms=(time.perf_counter()-t)*1000
                    for sid in ids:
                        source=self.tools.sources[sid]
                        if bounds:
                            text=' '.join(b['text'] for b in source['blocks'] if bounds[0]<=int(b['block_id'])<bounds[1])
                            t=time.perf_counter()
                            try:matched=bool(set(terms).intersection(question_terms(text)))
                            finally:bounds_tokenize_ms+=(time.perf_counter()-t)*1000
                            if not matched: continue
                            n=self.resolve(args['target']);key=(n['document_id'],n['unit_id'],None)
                        else: key=(source['document_id'],source.get('unit_id'),sid)
                        locations[key]=None
                    completed=True
                finally:
                    obs.event(search_log,'fulltext.location.timings',
                              diagnostic_revision=DIAGNOSTIC_REVISION,
                              mapping_status='completed' if completed else 'failed',
                              result_count=len(ids),location_count=len(locations),bounds_enabled=bool(bounds),
                              route_handle_ms=round(route_handle_ms,3),bounds_tokenize_ms=round(bounds_tokenize_ms,3),
                              **thread_delta(before,thread_snapshot()),
                              **{k:round(v,3) if isinstance(v,float) else v for k,v in (loads or {}).items()})
        keys,nxt=self.page(list(locations),offset)
        with obs.step(search_log,'fulltext_tool.page_preview',result_count=len(keys)):
            # Previews, routes and candidate handles are materialized only for the returned page.
            items=[self.node_card(did,uid,source_id=sid,route=route) for did,uid,sid in keys]
        return items,nxt,[],{'search_receipt':{'mode':'fulltext','query':args['query'],
            'query_terms':terms,'searched_target':args['target'],'document_ids':docs,'bounds':bounds,
            'total_status':'exact','total':len(locations),'tokenizer':self.matcher.fulltext.manifest['tokenizer'],
            'ranking':self.matcher.fulltext.manifest['ranking']}}

    def lookup_definition(self,args,offset):
        items,nxt,evidence,extra=super().lookup_definition(args,offset)
        if extra.get('definition_kind')!='document':
            items=[{**c,'concept_target':self.handle('K',{'concept_id':c['id']})}
                   for c in items if self.cards.concept_allowed(c)]
        return items,nxt,evidence,extra

    def term_occurrences(self,args,offset):
        items,nxt,evidence,extra=super().term_occurrences(args,offset)
        labels=[self.tools.terms[self.resolve(t,'T')['term_id']]['label'] for t in args['terms']]
        for card in items:
            raw=self.resolve(card['target'],'PU')
            for label in labels:
                preview=self.preview(raw,query=label)
                if preview['preview_basis']=='EXACT_LITERAL_MATCH':
                    card.update(preview)
                    break
        return items,nxt,evidence,extra

    def read(self, args, offset):
        # Exact text appears both as text and spans. Leave room for navigation and schemas.
        from .relations_policy import SYSTEM, PROMPTS
        binding=self.profile.get('model_binding')
        byte_chars=self.profile['max_read_chars']
        if binding:
            overhead=2*len(encoded(protocol.schema('TurnDecision')).encode())
            overhead+=len(encoded(SYSTEM+PROMPTS['investigate']+self.context.request['question']).encode())+16000
            byte_chars=max(1,(binding['max_input_bytes']-overhead)//12)
        self.source.profile={**self.profile,'max_read_chars':min(self.profile['max_read_chars'],
            self.profile['max_context_chars']//8,byte_chars)}
        n=self.resolve(args['target'],'DUPE')
        if args['extent']=='article' and 'evidence_id' not in n:
            # A relation/search handle may point at just one paragraph. The
            # requested article extent must use the canonical source's range,
            # never the handle's narrower witness block_ids.
            did=n['document_id']
            ids=([n['source_id']] if n.get('source_id') else
                 self.matcher._unit_sources(did,n['unit_id']) if n.get('unit_id') is not None else [])
            if len(ids)!=1 or ids[0] not in self.tools.sources:
                raise ProposalError('article does not resolve to one source; locate an article first')
            source=self.tools.sources[ids[0]]
            if source['document_id']!=did:
                raise ProposalError('article source outside target document')
            n={'document_id':did,'unit_id':source['unit_id'],'source_id':ids[0],
               'block_ids':sorted({b['block_id'] for b in source['blocks']},key=int)}
        if not n.get('block_ids'): return super().read(args,offset)
        evidence,nxt=self.source._read(n,offset)
        key=digest({'node':n,'extent':args['extent']})
        previous=[self.repo.evidence(r[0]) for r in self.repo.db.execute('SELECT evidence_id FROM read_coverage WHERE target_hash=?',(key,))]
        complete=self.covers(n, previous+evidence)
        return [{'evidence':e['evidence_id'],'text':'\n'.join(p['text'] for p in e['spans']),
                 'text_hash':e['text_hash'],**self.location(args['target'])} for e in evidence],nxt,evidence,{
                 'coverage_key':key,'status':'OK' if complete else 'PARTIAL',
                 'coverage':{'complete':complete,'requested_extent':args['extent'],'basis':'union_of_exact_spans','truncated':nxt is not None}}

    def covers(self, target, evidence):
        for bid in self.block_ids(target):
            end=0
            for a,b in sorted((s['start_cp'],s['end_cp']) for e in evidence if e['document_id']==target['document_id'] for s in e['spans'] if s['block_id']==bid):
                if a>end: break
                end=max(end,b)
            if end<len(self.store.source(target['document_id'],bid)['text']): return False
        return True

    def materialize(self, value):
        from .relations_policy import GUIDANCE
        value={**value,'guidance':GUIDANCE.get(value.get('guidance_code'),'연결 정보가 제한되거나 미확인 상태입니다. 추가 확인 없이 관계가 없다고 단정하지 마십시오.')}
        value={**value,'targets':[self.candidate(t) for t in value['targets']]}
        if value.get('neighbour_term'):
            value['term_target']=self.handle('T',{'term_id':value['neighbour_term'],'routes':[],'target':self.root})
        if value.get('via_concept'):
            value['via_concept_target']=self.handle('K',{'concept_id':value['via_concept']['id']})
        if value.get('neighbour_concept'):
            c=value['neighbour_concept']
            value['concept_target']=self.handle('K',{'concept_id':c['id']})
        value['notice_hash']=digest(value)
        return value

    def relation_page(self, anchor, family, offset, direction='both'):
        if family=='reference': stream=self.cards.references(anchor,direction)
        elif family=='term': stream=self.cards.term_relations(anchor)
        else: stream=getattr(self.cards,{'definition':'definitions','occurrence':'occurrences'}.get(family,family))(anchor)
        started=time.monotonic(); size=self.profile['relation_page_size']; page=[]; count=0
        for i,n in enumerate(stream):
            if time.monotonic()-started>self.profile['relation_scan_seconds']:
                return page,offset+len(page),{'scan_status':'PARTIAL','scan_reason':'SCAN_TIME_LIMIT'}
            if i<offset: continue
            if len(page)>=size:
                return page,offset+len(page),{'scan_status':'PARTIAL','scan_reason':'PAGE_LIMIT'}
            item=self.materialize(n); count+=len(encoded(item))
            if count>self.profile['max_relation_chars']:
                if not page:
                    # The relation remains actionable without copying a large source frame.
                    item={**item,'witness_spans':[],'targets':[], 'auto_eligible':False,
                          'resolution':'PAYLOAD_TOO_LARGE','guidance_code':'NARROW_READ_REQUIRED'}
                    item['notice_hash']=digest({k:v for k,v in item.items() if k!='notice_hash'})
                    page.append(item)
                return page,offset+len(page),{'scan_status':'PARTIAL','scan_reason':'RELATION_CHAR_LIMIT'}
            page.append(item)
        return page,None,{'scan_status':'COMPLETE','scan_reason':'SELECTED_INDEX_ONLY'}

    def follow_reference(self,args,offset):
        items,nxt,extra=self.relation_page(args['evidence'],'reference',offset,args['direction'])
        return items,nxt,[],{**extra,'scan_anchor':args['evidence'],'scan_family':'reference',
                            'scan_direction':args['direction']}

    def follow_relations(self,args,offset):
        anchor=args['target']; family=args['family']
        if family=='all':
            position=offset if isinstance(offset,dict) else {'family':0,'offset':0}
            families=FAMILIES if anchor.startswith('E') else ('knowledge',) if anchor.startswith('K') else ('definition','term','occurrence','knowledge')
            family=families[position['family']]
            items,nxt,extra=self.relation_page(anchor,family,position['offset'])
            next_pos={'family':position['family'],'offset':nxt} if nxt is not None else {'family':position['family']+1,'offset':0} if position['family']+1<len(families) else None
            extra['all_families_complete']=next_pos is None
        else:
            if family in ('reference','structure') and not anchor.startswith('E'): raise ProposalError('relation family requires E')
            if anchor.startswith('K') and family!='knowledge': raise ProposalError('concept handle requires knowledge family')
            items,nxt,extra=self.relation_page(anchor,family,offset); next_pos=nxt
        return items,next_pos,[],{**extra,'scan_anchor':anchor,'scan_family':family,'scan_direction':'both'}

    def inspect(self,args,offset):
        section=args['section']
        if section=='relations': rows=self.repo.notices()
        elif section=='assessments':
            rows=[dict(r) for r in self.repo.db.execute("SELECT kind,entity_id,version,payload_json FROM entity_version WHERE kind IN ('assessment','relation_assessment') ORDER BY created_seq")]
        elif section=='actions': rows=self.action_summaries()
        elif section=='coverage': rows=self.repo.coverage()
        else: return super().inspect(args,offset)
        page,nxt=self.page(rows,offset)
        return page,nxt,[],{}

    def action_summaries(self):
        rows=[]
        for r in self.repo.db.execute('SELECT * FROM action_context ORDER BY created_seq'):
            a=json.loads(r['proposed_json']); result=json.loads(r['result_json'] or '{}')
            rows.append({'action_id':r['action_id'],'actor':r['actor'],'parent_action_id':r['parent_action_id'],
                'input_view_id':r['input_view_id'],'policy_hash':r['policy_hash'],
                'tool':a['tool'],'reason':a['reason'],'question_refs':a.get('question_refs',[]),
                'expected_information':a.get('expected_information'),'status':r['status'],
                'evidence_ids':result.get('evidence_ids',[]),'relation_ids':result.get('relation_ids',[]),
                'reused_from':result.get('reused_from'),'server_reason':result.get('server_reason')})
        return rows

    def execute(self, action, action_id, *, actor=None, view_id=None, parent=None, trigger=None, depth=0):
        actor=actor or self._actor
        view_id=None if actor=='SYSTEM_POLICY' else view_id or self._view_id
        proposal_hash=digest(action)
        old=self.repo.db.execute('SELECT * FROM action_context WHERE action_id=?',(action_id,)).fetchone()
        if old:
            if old['proposal_hash']!=proposal_hash or old['actor']!=actor:
                raise ProposalError('action ID reused with different canonical proposal')
            if old['result_json']: return json.loads(old['result_json'])
            raise ContractError('incomplete action cannot be replayed after interruption')
        with self.repo.transaction():
            seq=self.repo.event('ACTION_PROPOSED',{'action_id':action_id,'proposal':action,'actor':actor})
            self.repo.db.execute('INSERT INTO action_context VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (action_id,proposal_hash,encoded(action),actor,parent,trigger,
                 digest([self.context.binding['profile_sha256'],self.context.binding['pipeline_sha256']]) if actor=='SYSTEM_POLICY' else None,
                 view_id,'PROPOSED',None,seq))
        result={'action_id':action_id,'actor':actor,'input_view_id':view_id,'parent_action_id':parent,
                'trigger_reference_id':trigger,'effective_args':action['args'],'tool':action['tool'],'args_hash':digest({k:action[k] for k in ('tool','args')}),
                'policy_id':'read-relations-direct-prefetch-v3' if actor=='SYSTEM_POLICY' else None,
                'status':'NOT_EXECUTED','items':[],'evidence_ids':[],'relation_ids':[],'next_cursor':None}
        try:
            self.validate_action(action)
            self.context.remaining()
            self.repo.reserve_tool()
            self.repo.db.execute("UPDATE action_context SET status='RUNNING' WHERE action_id=?",(action_id,))
        except (BudgetExhausted,DeadlineExceeded,ProposalError) as exc:
            result['server_reason']=str(exc)
            with self.repo.transaction():
                self.repo.event('ACTION_NOT_EXECUTED',result)
                self.repo.db.execute('UPDATE action_context SET status=?,result_json=? WHERE action_id=?',('NOT_EXECUTED',encoded(result),action_id))
            if isinstance(exc,ProposalError): return result
            raise
        started=time.monotonic(); evidence=[]; key,offset=self.source.cursor_position(action)
        self._candidate_evidence = None
        self._candidate_cache_active = True
        scan=action['tool'] in ('follow_relations','follow_reference')
        scan_deadline=min(self.context.deadline,started+self.profile['relation_scan_seconds'])
        if scan:
            self._relation_scan_started=started
            self._relation_scan_deadline=scan_deadline
            for db in (self.store.db,self.tools.db,*self.glossary.dbs.values()):
                db.set_progress_handler(lambda: int(time.monotonic()>=scan_deadline),1000)
        try:
            cached=None
            if action['tool']=='read':
                cache_key=digest({'action':{k:action[k] for k in ('tool','args')},'binding':self.context.binding_hash})
                cached=self.repo.db.execute("SELECT observation_id,result_json FROM observation WHERE request_key=? AND status IN ('OK','PARTIAL','REUSED') ORDER BY created_seq LIMIT 1",(cache_key,)).fetchone()
            if cached:
                value=json.loads(cached['result_json']); evidence=[self.repo.evidence(e) for e in value['evidence_ids']]
                items=value['items']; nxt=None
                extra={k:v for k,v in value.items() if k in ('coverage','coverage_key','resolved_location','next_cursor')}
                extra.update(status='REUSED',reused_from=cached['observation_id'])
            else:
                items,nxt,evidence,extra=self.handlers[action['tool']](action['args'],offset)
            status=extra.pop('status','OK' if items else 'EMPTY')
            if status=='ERROR':
                raise ToolExecutionError('tool='+action['tool']+' handler returned ERROR: '
                                         +str(extra.get('server_reason') or extra.get('error') or 'unspecified execution failure'))
            result.update(items=items,evidence_ids=[e['evidence_id'] for e in evidence],status=status,
                next_cursor=self.source.cursor(key,nxt) if nxt is not None else None,
                coverage={'complete':nxt is None,'meaning':'selected operation only'})
            result.update(extra)
            result['relation_ids']=[n['relation_id'] for n in items if 'notice_hash' in n]
        except Exception as exc:
            stage=getattr(self,'_search_stage',None) if action['tool']=='search' else None
            elapsed_ms=int((time.monotonic()-started)*1000)
            interruption=('; fulltext SQL interrupted: request deadline or explicit SQLite interruption'
                          if stage=='fulltext_tool.rank' and str(exc).lower()=='interrupted' else '')
            detail=(f"tool={action['tool']} mode={action['args'].get('mode', 'n/a')} "
                    f"stage={stage or 'execute'} cause={type(exc).__name__}: {exc} "
                    f"duration_ms={elapsed_ms}{interruption}")
            obs.event(search_log,'tool.execution.failed',level=logging.ERROR,exc_info=True,
                      tool=action['tool'],mode=action['args'].get('mode'),
                      step=stage or 'execute',error_type=type(exc).__name__,
                      error_detail=str(exc),duration_ms=elapsed_ms)
            raise ToolExecutionError(detail) from exc
        finally:
            self._candidate_cache_active = False
            self._candidate_evidence = None
            if scan:
                self._relation_scan_deadline=None
                for db in (self.store.db,self.tools.db,*self.glossary.dbs.values()):
                    db.set_progress_handler(lambda: int(time.monotonic()>=self.context.deadline),1000)
        result['budget']={'action_reserved':True,'stored_chars':sum(len(p['text']) for e in evidence for p in e['spans']),
            'new_read_chars':0 if action['tool']!='read' or result['status']=='REUSED' else sum(len(p['text']) for e in evidence for p in e['spans']), 'duration_ms':int((time.monotonic()-started)*1000)}
        with self.repo.transaction():
            result=self.repo.record_observation(action,result,evidence,verify=self.source.verify)
            for e in evidence:
                self.repo.db.execute('INSERT OR IGNORE INTO evidence_origin VALUES(?,?,?)',(e['evidence_id'],action_id,depth))
                if not self.repo.db.execute("SELECT 1 FROM entity_head WHERE kind='relation_set' AND entity_id=?",(e['evidence_id'],)).fetchone():
                    seq=self.repo.event('RELATION_SET_CREATED',{'evidence':e['evidence_id']})
                    self.repo.put('relation_set',e['evidence_id'],{'evidence':e['evidence_id'],'relations':[]},seq)
                if result.get('coverage_key'):
                    self.repo.db.execute('INSERT OR IGNORE INTO read_coverage VALUES(?,?)',(result['coverage_key'],e['evidence_id']))
                # Only an explicit READ expands its direct neighbourhood. A model
                # re-read of automatically fetched evidence is a new explicit root.
                if actor in ('MODEL', 'REVIEWER'):
                    self.repo.enqueue_system(action_id,e['evidence_id'],{'tool':'follow_relations',
                        'args':{'target':e['evidence_id'],'family':'reference','cursor':None}},0)
                    self.repo.enqueue_system(action_id,e['evidence_id'],
                        {'tool':'prefetch_decision','anchor':e['evidence_id']},0)
            for n in result['items']:
                if n.get('notice_hash'): self.repo.record_notice(n)
            if result.get('scan_anchor'):
                self.repo.db.execute('INSERT INTO relation_scan VALUES(?,?,?,?,?) ON CONFLICT(anchor,family) DO UPDATE SET status=excluded.status,next_cursor=excluded.next_cursor,action_id=excluded.action_id',
                    (result['scan_anchor'],result['scan_family'],result['scan_status'] if result.get('scan_direction')=='both' else 'PARTIAL',result['next_cursor'],action_id))
            self.repo.db.execute('INSERT INTO action_receipt VALUES(?,?,?)',(action_id,proposal_hash,encoded(result)))
            self.repo.db.execute('UPDATE action_context SET status=?,result_json=? WHERE action_id=?',(result['status'],encoded(result),action_id))
            self.repo.event('ACTION_COMPLETED',{'action_id':action_id,'result_hash':digest(result)})
        if not self._draining: self.drain()
        return result

    def drain(self):
        self._draining=True
        try:
            while True:
                row=self.repo.db.execute("SELECT * FROM system_task WHERE status='PENDING' ORDER BY created_seq LIMIT 1").fetchone()
                if not row: break
                operation=json.loads(row['operation_json']); trigger=operation.pop('trigger_reference_id',None); result={}
                if operation['tool']=='prefetch_decision':
                    self.prefetch_direct(row)
                    continue
                budget=self.repo.budget()
                if budget['tool_used']>=budget['tool_limit']-self.profile['tool_finalization_reserve'] or time.monotonic()>=self.context.deadline:
                    self.finish_task(row,'SKIPPED_BUDGET',{'reason':'shared tool/time reserve'})
                    continue
                with self.repo.transaction():
                    self.repo.db.execute("UPDATE system_task SET status='RUNNING' WHERE task_id=?",(row['task_id'],))
                purpose={'question_refs':[], 'expected_information':'원문과 연결된 관계 및 정확 대상 범위 확인',
                         'reason':'시스템 정책: READ 후 관계 안내' if operation['tool']=='follow_relations' else '시스템 정책: 선택 원문의 직접 연결 대상 읽기'}
                try:
                    result=self.execute({**operation,**purpose},row['task_id'],actor='SYSTEM_POLICY',
                        parent=row['parent_action_id'],trigger=trigger,depth=row['depth'])
                    self.finish_task(row,'DONE' if result['status'] not in ('ERROR','NOT_EXECUTED') else 'FAILED',result)
                    if operation['tool']=='read' and result.get('next_cursor'):
                        self.repo.enqueue_system(row['parent_action_id'],row['evidence_id'],
                            {'tool':'read','args':{**operation['args'],'cursor':result['next_cursor']},
                             'trigger_reference_id':trigger},row['depth'])
                except (BudgetExhausted,DeadlineExceeded) as exc:
                    self.finish_task(row,'SKIPPED_BUDGET',{'reason':str(exc)})
        finally:
            self._draining=False

    def finish_task(self,row,status,result):
        with self.repo.transaction():
            self.repo.db.execute('UPDATE system_task SET status=?,result_json=? WHERE task_id=?',(status,encoded(result),row['task_id']))
            self.repo.event('SYSTEM_TASK_'+status,{'task_id':row['task_id'],'result':result})

    def prefetch_direct(self, row):
        notices=[n for n in self.repo.notices() if n['anchor']==row['evidence_id']]
        scan=self.repo.db.execute("SELECT * FROM relation_scan WHERE anchor=? AND family='reference'",
                                  (row['evidence_id'],)).fetchone()
        summary={'anchor':row['evidence_id'],'relation_count':len(notices),
                 'unresolved_count':sum(not n.get('targets') for n in notices),
                 'target_count':0,'read_chars':0}
        if not scan or scan['status']!='COMPLETE':
            summary.update(reason='INCOMPLETE_RELATION_SCAN',next_cursor=scan['next_cursor'] if scan else None)
            self.finish_task(row,'SKIPPED_SELECTION',summary); return
        # Deduplicate by exact document/block range, not relation ID or predicate.
        targets={}
        for n in notices:
            for target in n.get('targets',[]):
                raw=self.resolve(target['target'],'PU')
                blocks=self.block_ids(raw)
                key=digest([self.context.binding_hash,raw['document_id'],blocks])
                targets.setdefault(key,(n,target,raw,blocks))
        summary['target_count']=len(targets)
        if len(targets)>self.profile['relation_page_size']:
            self.finish_task(row,'SKIPPED_SELECTION',{**summary,'reason':'TARGET_COUNT_LIMIT'}); return
        pending=[]; total_chars=0; pages=0
        # read() uses this same conservative per-page bound (and final packing
        # checks actual serialized request bytes independently).
        per_page=min(self.profile['max_read_chars'],self.profile['max_context_chars']//8)
        for key,(n,target,raw,blocks) in targets.items():
            if self.covers(raw,self.repo.evidence()): continue
            if self.repo.db.execute('SELECT 1 FROM auto_visit WHERE extent_hash=?',(key,)).fetchone(): continue
            chars=sum(len(self.store.source(raw['document_id'],b)['text']) for b in blocks)
            total_chars+=chars
            pages+=max(1,(chars+per_page-1)//per_page)+(len(blocks)-1)//self.profile['page_size']
            pending.append((key,n,target,chars))
        summary.update(read_chars=total_chars,pending_target_count=len(pending))
        budget=self.repo.db.execute('SELECT * FROM auto_budget').fetchone()
        reason=None
        if total_chars>min(self.profile['max_auto_reference_chars_per_request'],self.profile['max_context_chars']//4):
            reason='TARGET_TEXT_LIMIT'
        elif budget['reads']+len(pending)>self.profile['max_auto_reference_reads_per_request'] or budget['chars']+total_chars>self.profile['max_auto_reference_chars_per_request']:
            reason='REQUEST_AUTO_READ_LIMIT'
        elif self.repo.budget()['tool_used']+pages>self.repo.budget()['tool_limit']-self.profile['tool_finalization_reserve']:
            reason='TOOL_RESERVE'
        if reason:
            self.finish_task(row,'SKIPPED_SELECTION',{**summary,'reason':reason}); return
        for key,n,target,chars in pending:
            with self.repo.transaction():
                task=self.repo.enqueue_system(row['parent_action_id'],row['evidence_id'],{'tool':'read',
                    'args':{'target':target['target'],'extent':'subtree','cursor':None},
                    'trigger_reference_id':n.get('reference_id')},1)
                self.repo.db.execute('INSERT INTO auto_visit VALUES(?,?)',(key,task))
                self.repo.db.execute('UPDATE auto_budget SET reads=reads+1,chars=chars+?',(chars,))
        self.finish_task(row,'DONE',{**summary,'reason':'ALL_RESOLVABLE_DIRECT_TARGETS_QUEUED' if pending else
            'TARGETS_ALREADY_READ' if targets else 'UNRESOLVED_RELATIONS' if notices else 'NO_INDEXED_RELATIONS'})
