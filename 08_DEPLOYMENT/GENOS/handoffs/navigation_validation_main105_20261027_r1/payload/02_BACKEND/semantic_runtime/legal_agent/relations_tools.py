"""V3 exploration on the existing source reader, with bounded durable policy tasks."""
import json
import sqlite3
import time
from itertools import islice
from ..contracts import digest
from . import relations_protocol as protocol
from .exploration_tools import ExplorationTools
from .relation_cards import RelationCards
from .repository import encoded, text_hash
from .errors import BudgetExhausted, DeadlineExceeded, ContractError, ProposalError

FAMILIES = ('reference','definition','term','occurrence','structure','knowledge')


class RelationsTools(ExplorationTools):
    def __init__(self, *args):
        super().__init__(*args)
        self.handlers = {name: getattr(self, name) for name in protocol.REGISTRY}
        self.capabilities.update({name: True for name in self.handlers})
        self.cards = RelationCards(self)
        tables={r[0] for r in self.glossary.dbs['dictionary'].execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.capabilities['lexical_observations']='AVAILABLE' if {'sense_assertion','sense_candidate'}<=tables else 'UNAVAILABLE_IN_SELECTED_GLOSSARY'
        self._draining = False
        self._actor = 'MODEL'
        self._view_id = None

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
        read=[e['evidence_id'] for e in self.repo.evidence() if e['document_id']==n['document_id'] and ids & {p['block_id'] for p in e['spans']}]
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
        if args['mode']!='fulltext': return super().search(args,offset)
        if hasattr(self.matcher.fulltext,'rank_units'):
            return ExplorationTools.search(self,args,offset)
        from ..fulltext import question_terms
        docs,bounds=self.docs_bounds(args['target']);terms=question_terms(args['query'])
        ids=self.matcher.fulltext.rank(self.matcher.fulltext_db,terms,set(self.sources_in(args['target'])))
        route=self.handle('L',{'kind':'search','query':args['query'],'target':args['target'],'mode':'fulltext'})
        locations={}
        for sid in ids:
            source=self.tools.sources[sid]
            if bounds:
                text=' '.join(b['text'] for b in source['blocks'] if bounds[0]<=int(b['block_id'])<bounds[1])
                if not set(terms).intersection(question_terms(text)): continue
                n=self.resolve(args['target']);key=(n['document_id'],n['unit_id'],None)
            else: key=(source['document_id'],source.get('unit_id'),sid)
            locations[key]=None
        keys,nxt=self.page(list(locations),offset)
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
        # Keep source page bounds without deriving a separate wire byte cap.
        self.source.profile={**self.profile,'max_read_chars':min(self.profile['max_read_chars'],
            self.profile['max_context_chars']//8)}
        n=self.resolve(args['target'],'DUPE')
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
        size=self.profile['relation_page_size']; page=[]; count=0
        for i,n in enumerate(stream):
            self.context.remaining()
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
                'reused_from':result.get('reused_from'),'server_reason':
                    result['tool_outcome'].get('cause_code') if result.get('tool_outcome') else result.get('server_reason')})
        return rows

    from .tool_execution_receipt import recorded_execution

    @recorded_execution
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
            from .tool_outcome import failure_details
            result['failure']=failure_details(exc,execution='NOT_STARTED')
            with self.repo.transaction():
                self.repo.event('ACTION_NOT_EXECUTED',result)
                self.repo.db.execute('UPDATE action_context SET status=?,result_json=? WHERE action_id=?',('NOT_EXECUTED',encoded(result),action_id))
            if isinstance(exc,ProposalError): return result
            raise
        self._tool_receipt_phase='handler'
        started=time.monotonic(); evidence=[]; key,offset=self.source.cursor_position(action)
        scan=action['tool'] in ('follow_relations','follow_reference')
        scan_deadline=self.context.deadline
        if scan:
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
            result.update(items=items,evidence_ids=[e['evidence_id'] for e in evidence],status=status,
                next_cursor=self.source.cursor(key,nxt) if nxt is not None else None,
                coverage={'complete':nxt is None,'meaning':'selected operation only'})
            result.update(extra)
            result['relation_ids']=[n['relation_id'] for n in items if 'notice_hash' in n]
            from .tool_outcome import FAILURE_STATUSES
            if status in FAILURE_STATUSES:
                evidence=[]
                result.update(items=[],evidence_ids=[],relation_ids=[],next_cursor=None,
                              coverage={'complete':False,'meaning':'failed operation; not absence evidence'})
        except (sqlite3.OperationalError,ProposalError,ValueError) as exc:
            result.update(status='ERROR',server_reason=str(exc),scan_status='FAILED')
            evidence=[]
            result.update(items=[],evidence_ids=[],relation_ids=[],next_cursor=None,
                          coverage={'complete':False,'meaning':'failed operation; not absence evidence'})
            from .tool_outcome import failure_details
            result['failure']=failure_details(exc)
        finally:
            if scan:
                for db in (self.store.db,self.tools.db,*self.glossary.dbs.values()):
                    db.set_progress_handler(lambda: int(time.monotonic()>=self.context.deadline),1000)
        result['budget']={'action_reserved':True,'stored_chars':sum(len(p['text']) for e in evidence for p in e['spans']),
            'new_read_chars':0 if action['tool']!='read' or result['status']=='REUSED' else sum(len(p['text']) for e in evidence for p in e['spans']), 'duration_ms':int((time.monotonic()-started)*1000)}
        self._tool_receipt_phase='observation'
        with self.repo.transaction():
            result=self.repo.record_observation(action,result,evidence,verify=self.source.verify)
            for e in evidence:
                self.repo.db.execute('INSERT OR IGNORE INTO evidence_origin VALUES(?,?,?)',(e['evidence_id'],action_id,depth))
                if not self.repo.db.execute("SELECT 1 FROM entity_head WHERE kind='relation_set' AND entity_id=?",(e['evidence_id'],)).fetchone():
                    seq=self.repo.event('RELATION_SET_CREATED',{'evidence':e['evidence_id']})
                    self.repo.put('relation_set',e['evidence_id'],{'evidence':e['evidence_id'],'relations':[]},seq)
                if result.get('coverage_key'):
                    self.repo.db.execute('INSERT OR IGNORE INTO read_coverage VALUES(?,?)',(result['coverage_key'],e['evidence_id']))
                for family in FAMILIES:
                    origin=self.repo.db.execute('SELECT action_id,automatic_depth FROM evidence_origin WHERE evidence_id=?',(e['evidence_id'],)).fetchone()
                    self.repo.enqueue_system(origin['action_id'],e['evidence_id'],{'tool':'follow_relations',
                        'args':{'target':e['evidence_id'],'family':family,'cursor':None}},origin['automatic_depth'])
                self.repo.enqueue_system(origin['action_id'],e['evidence_id'],
                    {'tool':'prefetch_decision'},origin['automatic_depth'])
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
                    notices=[n for n in self.repo.notices() if n['anchor']==row['evidence_id']]
                    scans=list(self.repo.db.execute('SELECT status FROM relation_scan WHERE anchor=?',(row['evidence_id'],)))
                    if len(notices)>self.profile['relation_page_size'] or len(scans)!=len(FAMILIES) or any(r[0]!='COMPLETE' for r in scans):
                        self.finish_task(row,'SKIPPED_SELECTION',{'reason':'many or incomplete relations; model selects targets'})
                    else:
                        for n in notices:
                            if n.get('auto_eligible'): self.queue_auto(row,n)
                        self.finish_task(row,'DONE',{'reason':'bounded direct-target eligibility checked after all families'})
                    continue
                budget=self.repo.budget()
                if budget['tool_used']>=budget['tool_limit']-self.profile['tool_finalization_reserve'] or time.monotonic()>=self.context.deadline:
                    self.finish_task(row,'SKIPPED_BUDGET',{'reason':'shared tool/time reserve'})
                    continue
                with self.repo.transaction():
                    self.repo.db.execute("UPDATE system_task SET status='RUNNING' WHERE task_id=?",(row['task_id'],))
                purpose={'question_refs':[], 'expected_information':'원문과 연결된 관계 및 정확 대상 범위 확인',
                         'reason':'시스템 정책: READ 후 관계 안내' if operation['tool']=='follow_relations' else '시스템 정책: 검증된 직접 준용 대상 선읽기'}
                try:
                    result=self.execute({**operation,**purpose},row['task_id'],actor='SYSTEM_POLICY',
                        parent=row['parent_action_id'],trigger=trigger,depth=row['depth'])
                    self.finish_task(row,'DONE' if result['status'] not in ('ERROR','NOT_EXECUTED') else 'FAILED',result)
                except (BudgetExhausted,DeadlineExceeded) as exc:
                    self.finish_task(row,'SKIPPED_BUDGET',{'reason':str(exc)})
        finally:
            self._draining=False

    def finish_task(self,row,status,result):
        with self.repo.transaction():
            self.repo.db.execute('UPDATE system_task SET status=?,result_json=? WHERE task_id=?',(status,encoded(result),row['task_id']))
            self.repo.event('SYSTEM_TASK_'+status,{'task_id':row['task_id'],'result':result})

    def queue_auto(self,row,n):
        origin=self.repo.db.execute('SELECT automatic_depth FROM evidence_origin WHERE evidence_id=?',(row['evidence_id'],)).fetchone()
        if not origin or origin[0]>=self.profile['auto_reference_read_depth']: return
        target=n['targets'][0]['target']; raw=self.resolve(target,'PU')
        extent=digest([self.context.binding_hash,raw['document_id'],self.block_ids(raw)])
        if self.repo.db.execute('SELECT 1 FROM auto_visit WHERE extent_hash=?',(extent,)).fetchone(): return
        if self.covers(raw,self.repo.evidence()): return
        budget=self.repo.db.execute('SELECT * FROM auto_budget').fetchone()
        cost=min(self.profile['max_read_chars'],sum(len(self.store.source(raw['document_id'],b)['text']) for b in self.block_ids(raw)))
        if budget['reads']>=self.profile['max_auto_reference_reads_per_request'] or budget['chars']+cost>self.profile['max_auto_reference_chars_per_request']:
            with self.repo.transaction():
                self.repo.event('AUTO_READ_SKIPPED_BUDGET',{'relation_id':n['relation_id']})
            return
        with self.repo.transaction():
            task=self.repo.enqueue_system(row['parent_action_id'],row['evidence_id'],{'tool':'read',
                'args':{'target':target,'extent':'subtree','cursor':None},'trigger_reference_id':n['reference_id']},origin[0]+1)
            self.repo.db.execute('INSERT INTO auto_visit VALUES(?,?)',(extent,task))
            self.repo.db.execute('UPDATE auto_budget SET reads=reads+1,chars=chars+?',(cost,))
