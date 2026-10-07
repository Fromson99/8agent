"""Model-only source adoption, with independent legal claim and publication paths."""
import json
from ..contracts import digest
from .relations_session import RelationsSession
from .session import LegalSession
from . import workflow_tiers_protocol as protocol
from .workflow_tiers_policy import IMPLEMENTATION
from .workflow_tiers_views import build, span_choices
from .repository import text_hash
from .errors import ProposalError, ContractError, BudgetExhausted, DeadlineExceeded, TransportError


class TiersSession(RelationsSession):
    @property
    def goal_id(self): return 'G'+digest(self.context.request['question'])[:24]

    @staticmethod
    def offered_handles(value):
        result=set()
        def visit(v):
            if isinstance(v,dict):
                for k,x in v.items():
                    if k in ('target','evidence','evidence_id','relation_id','cursor','term_target','concept_target','via_concept_target') and isinstance(x,str): result.add(x)
                    elif k not in ('text','spans','selectable_spans','original_question','reason','relevance_reason'): visit(x)
            elif isinstance(v,list):
                for x in v: visit(x)
        visit(value)
        return result

    def selection_summary(self):
        return [{'selection_id':h['entity_id'],'version':h['version'],'evidence_id':h['payload']['evidence_id'],
                 'tier':h['payload'].get('tier'),'status':h['payload']['status']}
                for h in self.work.heads('source_selection',current=True)]

    def view(self,phase,*,required=(),extra=None):
        from .. import observability as obs
        with obs.step(obs.get_logger('model_view'),'model.view_build',phase=phase):
            return self._build_view(phase,required=required,extra=extra)

    def _build_view(self,phase,*,required=(),extra=None):
        if phase in ('investigate','select_sources'):
            if phase=='investigate' and self.context.remaining()<self.profile['selection_time_reserve_seconds']:
                raise BudgetExhausted('time reserved for final source selection')
            return build(self,phase)
        if phase=='review' and extra:
            extra={**extra,'claims':[{'claim':h['entity_id'],**h['payload']} for h in extra.get('claims',[])]}
        return super().view(phase,required=required,extra=extra)

    def validate_selection(self,view,d):
        internal=protocol.deepcopy(protocol.LEGACY_DECISION)
        internal['properties']['selections']['items']['properties']['basis_span_ids'].pop('maxItems',None)
        protocol.Draft202012Validator(internal).validate(d)
        self.work.check_view(view['view_id'],view['phase'])
        if (d['goal_id'],d['question_revision'],d['view_id'])!=(self.goal_id,1,view['view_id']):
            raise ProposalError('selection goal/revision/view mismatch')
        choices={p['span_id']:p for p in view['selectable_spans']}
        plans=[]; selected=set(); seen=set()
        for item in d['selections']:
            e=self.work.evidence(item['evidence_id']); self.work.visible(view['view_id'],[e['evidence_id']])
            spans=[]
            for ident in item['basis_span_ids']:
                p=choices.get(ident)
                if not p or p['evidence_id']!=e['evidence_id']: raise ProposalError('span not presented for selected evidence; READ and reselect')
                spans.append(p)
            spans=list({p['span_id']:p for p in spans}.values())
            self.sources.source.verify(e)
            for rid in item['relation_refs']:
                n=self.work.notice(rid)
                if rid not in self.offered_handles(view): raise ProposalError('relation not offered')
                target_match=any(e['document_id']==self.sources.resolve(t['target'],'PU')['document_id'] and
                    set(self.sources.block_ids(self.sources.resolve(t['target'],'PU'))) & {p['block_id'] for p in spans} for t in n['targets'])
                if e['evidence_id'] not in n['source_evidence'] and not target_match: raise ProposalError('selection relation endpoint mismatch')
            if item['interpretation_status']=='REVIEWED':
                reviewed=any(h['payload']['verdict']=='SUPPORTED' and e['evidence_id'] in h['payload']['evidence'] for h in self.work.heads('review',current=True))
                if not reviewed: raise ProposalError('REVIEWED requires independent legal review')
            key='SS'+digest([self.goal_id,e['generation_id'],e['source_artifact_hash'],e['document_id'],
                [(p['block_id'],p['start_cp'],p['end_cp']) for p in spans]])[:28]
            if key in seen: raise ProposalError('duplicate range across tiers; choose one tier')
            seen.add(key); selected.add(e['evidence_id'])
            plans.append((key,{**item,'basis_spans':spans,'status':'SELECTED','goal_id':self.goal_id,
                'question_revision':1,'view_id':view['view_id'],'binding_hash':self.context.binding_hash}))
        for field,status in [('pending','PENDING'),('rejected','REJECTED')]:
            for item in d[field]:
                ident=item['evidence_id']
                if ident in selected: raise ProposalError('conflicting source disposition')
                selected.add(ident); self.work.visible(view['view_id'],[ident])
                plans.append(('SD'+digest([self.goal_id,ident])[:28],{**item,'status':status,'goal_id':self.goal_id,
                    'question_revision':1,'view_id':view['view_id'],'binding_hash':self.context.binding_hash}))
        replaced={p['evidence_id'] for _,p in plans}
        prospective=[h['payload'] for h in self.work.heads('source_selection',current=True)
                     if h['payload']['evidence_id'] not in replaced]+[p for _,p in plans]
        for tier,cap in [('CORE','max_core_sources'),('SUPPLEMENTAL','max_supplemental_sources')]:
            if sum(p.get('tier')==tier and p['status']=='SELECTED' for p in prospective)>self.profile[cap]:
                raise ProposalError('tier limit exceeded; prioritize and explicitly replace or reject earlier selections')
        return plans

    def persist_selection(self,view,d,plans):
        key='source-selection:'+view['view_id']
        old=self.work.db.execute('SELECT payload_json FROM event WHERE event_id=?',(key,)).fetchone()
        if old:
            if json.loads(old[0])['decision']!=d: raise ProposalError('view selection conflict')
            return
        seq=self.work.event('SOURCE_SELECTION',{'decision':d},event_id=key,advance=True)
        replacing={p['evidence_id'] for _,p in plans}
        keys={k for k,_ in plans}
        for h in self.work.heads('source_selection',current=True):
            if h['payload']['evidence_id'] in replacing and h['entity_id'] not in keys:
                self.work.invalidate('source_selection',h['entity_id'],h['version'])
                self.work.event('SOURCE_SELECTION_EXCLUDED',{'selection_id':h['entity_id'],'version':h['version'],'reason':'MODEL_REPLACED'})
        for key,p in plans:
            self.work.put('source_selection',key,p,seq,evidence_ids=[p['evidence_id']])
        self.work.db.execute('UPDATE stage_artifact SET valid=0')

    def translate_choices(self,view,decision):
        protocol.validate_wire('SourceSelectionDecision',decision)
        legacy={'goal_id':self.goal_id,'question_revision':1,'view_id':view['view_id'],
                'selections':[],'pending':[],'rejected':[]}
        errors=[];seen=set()
        for i,item in enumerate(decision['choices']):
            try:
                protocol.Draft202012Validator(protocol.CHOICE).validate(item)
                ident=item['source']
                if ident in seen: raise ProposalError('one disposition per source is required')
                seen.add(ident)
                if ident not in {e['evidence'] for e in view['exact_evidence']}:
                    raise ProposalError('source not delivered in this view; READ or view_page first')
                if item['decision'].startswith('KEEP_'):
                    e=self.work.evidence(ident)
                    legacy['selections'].append({'evidence_id':ident,'tier':item['decision'][5:],
                        'basis_span_ids':[p['span_id'] for p in span_choices(e,self.profile['max_source_excerpt_chars'])],
                        'relevance_reason':item['reason'],'relation_refs':[],'interpretation_status':'UNASSESSED'})
                else:
                    legacy['pending' if item['decision']=='DEFER' else 'rejected'].append({'evidence_id':ident,'reason':item['reason']})
            except (ProposalError,protocol.ValidationError) as exc:
                errors.append({'field':f'choices[{i}]','actual':item,'expected':'delivered source + KEEP_CORE/KEEP_SUPPLEMENTAL/DEFER/REJECT + reason','message':str(exc)[:800]})
        return legacy,errors

    def source_plans(self,view,d):
        legacy,errors=self.translate_choices(view,d)
        # Exact server-side mapping; never ask the model to reconstruct block offsets.
        bound={**view,'selectable_spans':[p for e in view['exact_evidence'] for p in span_choices(self.work.evidence(e['evidence']),self.profile['max_source_excerpt_chars'])]}
        plans=self.validate_selection(bound,legacy)
        return legacy,plans,errors

    def repair_record(self,view,errors):
        record={'code':'OPERATION_REJECTED','owner':'MODEL','state':'OPEN','errors':errors,
                'valid_sources':[e['evidence'] for e in view['exact_evidence']],
                'preserved_selections':self.selection_summary(),
                'message':'Correct only rejected operations using this view. Successful source choices remain stored.'}
        self.errors.append(record)
        with self.work.transaction(): self.work.event('WORKFLOW_REPAIR',record)
        return record

    def commit_selection(self,view,d):
        legacy,plans,errors=self.source_plans(view,d)
        if plans:
            with self.work.transaction(): self.persist_selection(view,legacy,plans)
        if errors:
            self.repair_record(view,errors)
            raise ProposalError('source operations rejected; inspect errors and current source choices')

    def corrective_actions(self,view,action):
        if (action.get('tool')=='search' and action.get('args',{}).get('mode')=='fulltext'
                and not self.sources.capabilities.get('fulltext')):
            alternative={**action,'args':{**action['args'],'mode':'title'},
                         'reason':'수정: 현재 세대에서 지원하는 제목 검색 사용'}
            try:self.sources.validate_action(alternative,set(view['offered_handles']))
            except ProposalError:return []
            return [alternative]
        if action.get('tool')!='read':return []
        target=action.get('args',{}).get('target')
        if not target or target not in view['offered_handles']:return []
        # A page cursor can look like a P source handle. Recover the exact
        # server-supplied continuation instead of guessing a target or scope.
        for continuation in view.get('next_actions',[]):
            if continuation.get('args',{}).get('cursor')==target:
                try:self.sources.validate_action(continuation,set(view['offered_handles']))
                except ProposalError:continue
                return [continuation]
        alternatives=[{**action,'args':{'target':target,'extent':'exact' if target.startswith('E') else 'subtree','cursor':None},
                       'reason':'수정: 현재 대상에 맞는 범위로 원문 읽기'}]
        if target.startswith('D'):
            alternatives.append({**action,'tool':'browse','args':{'target':target,'relation':'self','view':'children','depth':1,'cursor':None},
                                 'reason':'수정: 문서 구조에서 읽을 조 위치 찾기'})
        valid=[]
        for alternative in alternatives:
            try:self.sources.validate_action(alternative,set(view['offered_handles']));valid.append(alternative)
            except ProposalError:pass
        return valid

    def apply_turn(self,view,d):
        self.gateway.protocol.validate_wire('TurnDecision',d)
        key='workflow-turn:'+view['view_id']
        old=self.work.db.execute('SELECT payload_json FROM event WHERE event_id=?',(key,)).fetchone()
        if old:
            if json.loads(old[0])['hash']!=digest(d): raise ProposalError('view reused with different decision')
            return False
        self.work.check_view(view['view_id'],'investigate')
        plans=[];errors=[];legacy=None
        if d['source_selection'] is not None:
            try: legacy,plans,errors=self.source_plans(view,d['source_selection'])
            except (ProposalError,protocol.ValidationError) as exc:
                errors.append({'field':'source_selection','message':str(exc)[:800]})
        valid=[]
        for i,action in enumerate(d['actions']):
            try:
                protocol.Draft202012Validator(protocol.v3.TOOL).validate(action)
                self.sources.validate_action(action,set(view['offered_handles']))
                valid.append((i,action))
            except (ProposalError,protocol.ValidationError) as exc:
                errors.append({'field':f'actions[{i}]','actual':action,'message':str(exc)[:800],
                    'expected':'use a current candidate read_action; document D needs subtree or locate a P/U article first',
                    'corrective_actions':self.corrective_actions(view,action)})
        # All validations use the same original view. Independent selections survive bad actions.
        with self.work.transaction():
            if hasattr(self, 'commit_question_plan'): self.commit_question_plan(view, d)
            if plans: self.persist_selection(view,legacy,plans)
            self.work.event('WORKFLOW_TURN',{'hash':digest(d),'decision':d},event_id=key,advance=True)
        if d['assessments'] or d['relation_assessments']:
            errors.append({'field':'assessments','message':'Use source choices for relevance. Legal claims are composed and independently reviewed after source selection.'})
        self.intent='CONTINUE' if valid or errors else d['intent']
        for i,a in valid:
            observation=self.sources.execute(a,f'{view["view_id"]}:{i}',actor='MODEL',view_id=view['view_id'])
            if observation.get('status')=='ERROR':
                errors.append({'field':f'actions[{i}]','actual':a,'observation_id':observation['observation_id'],
                    'message':observation.get('server_reason') or 'tool execution failed; inspect target and scope',
                    'corrective_actions':self.corrective_actions(view,a)})
        if not valid and self.intent=='DRAFT' and not self.work.evidence():
            candidates=self.work.db.execute("SELECT count(*) FROM navigation_handle WHERE kind IN ('P','U')").fetchone()[0]
            if candidates:
                errors.append({'field':'intent','message':'Candidates exist but none read. Choose a candidate read_action or explicitly CLARIFY; no-read is not no-source.'})
        if errors:
            self.repair_record(view,errors)
            raise ProposalError('workflow operations rejected '+digest([(e.get('field'),e.get('message')) for e in errors])[:12]+'; inspect structured errors and retry; valid selections preserved')
        return True

    def progress_key(self):
        # Reason rewrites and empty search argument variations do not count as progress.
        shown=[tuple(r) for r in self.work.db.execute("SELECT DISTINCT p.evidence_id,p.delivered_text_hash FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED' ORDER BY 1")]
        judgments=[]
        for h in self.work.heads(current=True):
            if h['kind'] not in ('source_selection','assessment','relation_assessment'): continue
            p={k:v for k,v in h['payload'].items() if k not in ('reason','relevance_reason','summary','view_id')}
            judgments.append([h['entity_id'],p])
        discovered=sorted({r[0] for r in self.work.db.execute("SELECT identity_json FROM navigation_handle WHERE kind IN ('P','U','D')")})
        return digest({'discovered':discovered,'shown':shown,'judgments':judgments,'relations':[n.get('semantic_hash',n['notice_hash']) for n in self.work.notices()]})

    def investigate(self):
        result=super().investigate()
        if not self.metadata_only and self.gateway:
            for _ in range(self.profile['source_selection_attempts']):
                try:
                    view=self.view('select_sources')
                    if not view['exact_evidence']: break
                    d=self.gateway.generate('select_sources',view,'SourceSelectionDecision')
                    self.commit_selection(view,d)
                    if d['choices']: break
                except (ProposalError,BudgetExhausted,DeadlineExceeded,TransportError) as exc:
                    self.errors.append({'code':exc.code,'message':str(exc)})
                    with self.work.transaction(): self.work.event('SOURCE_SELECTION_RECOVERY',self.errors[-1])
                    if not isinstance(exc,ProposalError): break
            result=self.retrieval()
        return result

    def select(self,retrieved):
        # This evidence pack permits drafting; it does not create an ADOPT judgment.
        heads=[h for h in self.work.heads('source_selection',current=True) if h['payload']['status']=='SELECTED']
        ids=list(dict.fromkeys(h['payload']['evidence_id'] for h in heads))
        contexts={}
        for ident in ids:
            e=self.work.evidence(ident)
            c=contexts.setdefault(e['source_id'],{'id':e['source_id'],'document_id':e['document_id'],
                'document_name':e['metadata']['document_name'],'unit_id':e['unit_id'],'text':'','evidence_ids':[]})
            c['text']+=('\n' if c['text'] else '')+e['text'];c['evidence_ids'].append(ident)
        self.packed={'support':ids,'challenge':[],'contextual':[],'evidence_ids':ids,'contexts':list(contexts.values()),'unresolved':[]}
        return {'selected':list(contexts.values()),'discarded_ids':[c['id'] for c in retrieved['retrieval']['candidates'] if c['id'] not in contexts],
                'method':'term-agent','term_agent':self.metadata()}

    def relation_requirements(self,p,view):
        # Only a claim's explicit dependencies are asserted; unrelated outgoing links are not proof obligations.
        joint=set(p['evidence']);deps=[]
        for rid in p['relation_dependencies']:
            n=self.work.notice(rid)
            self.work.item_visible(view['view_id'],'relation',rid,n['notice_hash'])
            state=self.relation_state(n,p['evidence'])
            if not state['witness_presented'] or not state['target_read_coverage'] or n.get('unresolved'):
                raise ProposalError('declared relation requires exact witness and target; read missing sources or defer claim')
            deps.append(('relation',rid))
        self.work.visible(view['view_id'],joint)
        return list(p['relation_dependencies']),deps,sorted(joint)

    def commit_draft(self,view,draft):
        self.gateway.protocol.validate('Draft',draft);self.work.check_view(view['view_id'],'compose')
        heads=[h for h in self.work.heads('source_selection',current=True) if h['payload']['status']=='SELECTED']
        selected={h['payload']['evidence_id']:h['entity_id'] for h in heads}
        accepted=[]
        for paragraph in draft['paragraphs']:
            self.qrefs(paragraph['question_refs']);self.work.visible(view['view_id'],paragraph['evidence'])
            if set(paragraph['evidence'])-set(selected):raise ProposalError('draft may cite selected delivered sources only')
            _,deps,_=self.relation_requirements(paragraph,view)
            if hasattr(self, 'obligation_view'): deps += [('question_plan', self.goal_id)]
            accepted.append((paragraph,deps+[('source_selection',selected[e]) for e in paragraph['evidence']]))
        with self.work.transaction():
            seq=self.work.event('WORKFLOW_DRAFT',{'draft':draft},advance=True)
            for old in self.work.heads('claim',current=True):self.work.invalidate('claim',old['entity_id'],old['version'])
            for paragraph,deps in accepted:
                ident='C'+str(self.work.db.execute("SELECT count(*) FROM entity_head WHERE kind='claim'").fetchone()[0]+1)
                self.work.put('claim',ident,paragraph,seq,dependencies=deps,evidence_ids=paragraph['evidence'])
        self.blocked_claims=0;self.question_review=None

    def build_bundle(self):
        cards=[];excluded=[];pending=0;rejected=0
        heads=self.work.heads('source_selection')
        for h in heads:
            p=h['payload']; ident=h['entity_id']
            if h['validity']!='CURRENT':
                excluded.append({'selection_id':ident,'version':h['version'],'reason':h['validity']});continue
            if p['status']!='SELECTED':
                pending+=p['status']=='PENDING'; rejected+=p['status']=='REJECTED';continue
            e=self.work.evidence(p['evidence_id'])
            try: self.sources.source.verify(e)
            except ContractError:
                excluded.append({'selection_id':ident,'version':h['version'],'reason':'SOURCE_STALE_OR_RESTRICTED'});continue
            spans=[]
            for sp in p['basis_spans']:
                raw=self.sources.store.source(e['document_id'],sp['block_id'])
                text=raw['text'][sp['start_cp']:sp['end_cp']]
                if text_hash(raw['text'])!=sp['block_hash']: raise ContractError('selected source span changed')
                spans.append({**sp,'text':text,'span_hash':text_hash(text)})
            unit=self.sources.matcher.units.get((e['document_id'],str(e['unit_id'])),{})
            chain=[self.sources.matcher.units[(e['document_id'],uid)] for uid in self.sources.ancestors(e['document_id'],e['unit_id'])]
            labels=[' '.join(str(u[k]) for k in ('surface','title') if u.get(k)) for u in chain]
            coordinate_label=' > '.join(label for label in labels if label) or str(e['metadata'].get('heading') or e['unit_id'])
            from urllib.parse import urlencode
            open_url='/v1/rag/source?'+urlencode({'run_id':self.context.run_id,'selection_id':ident})
            card={'coordinate_label':coordinate_label,'open_url':open_url,'selection_id':ident,'selection_version':h['version'],'goal_id':self.goal_id,'question_revision':1,
                'view_id':p['view_id'],'evidence_id':e['evidence_id'],'tier':p['tier'],
                'relevance_reason':p['relevance_reason'],'relation_refs':p['relation_refs'],
                'interpretation_status':p['interpretation_status'],'document_id':e['document_id'],
                'document_name':e['metadata']['document_name'],'coordinate':self.sources.location(e['evidence_id']),
                'generation_id':e['generation_id'],'source_store_sha256':self.context.binding['store_sha256'],
                'source_artifact_hash':e['source_artifact_hash'],'source_id':e['source_id'],'spans':spans,
                'excerpt':'\n'.join(sp['text'] for sp in spans),'coverage':'PARTIAL',
                'remaining_range':'선택한 범위 밖의 문맥은 원문에서 확인',
                'open_target':{'generation_id':e['generation_id'],'document_id':e['document_id'],
                               'unit_id':e['unit_id'],'source_artifact_hash':e['source_artifact_hash']}}
            cards.append(card)
        cards.sort(key=lambda c:c['tier']!='CORE')
        from .source_candidates import inventory
        candidates=inventory(self.work)
        bundle={'schema_version':'source-tiers-v4','goal_id':self.goal_id,'question_revision':1,
            'selection_revision':digest(heads),'binding_hash':self.context.binding_hash,
            'status':'SOURCE_SELECTED' if cards else 'NO_SELECTION','sources':cards,'excluded':excluded,
            'candidates_url':'/v1/rag/source-candidates?run_id='+self.context.run_id,
            'candidate_counts':{'pending':pending,'rejected':rejected,
                'unselected':len(candidates)}}
        bundle['bundle_hash']=digest(bundle)
        protocol.validate('FinalSourceBundle',bundle)
        with self.work.transaction():
            seq=self.work.event('SOURCE_BUNDLE',{'bundle_hash':bundle['bundle_hash'],'selection_revision':bundle['selection_revision']})
            self.work.put('source_bundle',self.goal_id,bundle,seq)
        return bundle

    def metadata(self,*,final=False,gate=None):
        meta=super().metadata(final=final,gate=gate);meta['implementation']=IMPLEMENTATION
        meta['source_workflow']={'version':'adr0489-v1','source_status':'SELECTED' if any(h['payload']['status']=='SELECTED' for h in self.work.heads('source_selection',current=True)) else 'NOT_SELECTED','absence_confirmed':False,'errors':self.errors[-4:]}
        return meta

    def answer_and_review(self,assembled):
        result,control=super().answer_and_review(assembled)
        if control['decision']=='FINAL':
            bundle=self.build_bundle()
            result['assembly']['term_agent']['source_bundle']=bundle
            result['assembly']['term_agent']['source_selection_status']=bundle['status']
            result['answer']['provider_receipt']['implementation']=IMPLEMENTATION
        return result,control
