"""Model-only source adoption, with independent legal claim and publication paths."""
import json
from ..contracts import digest
from .relations_session import RelationsSession
from .session import LegalSession
from . import tiers_protocol as protocol
from .tiers_policy import IMPLEMENTATION
from .tiers_views import build, span_choices
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
        if phase in ('investigate','select_sources'):
            if phase=='investigate' and self.context.remaining()<self.profile['selection_time_reserve_seconds']:
                raise BudgetExhausted('time reserved for final source selection')
            return build(self,phase)
        return super().view(phase,required=required,extra=extra)

    def validate_selection(self,view,d):
        protocol.validate('SourceSelectionDecision',d)
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
            spans=sorted({p['span_id']:p for p in spans}.values(),key=lambda p:(p['block_id'],p['start_cp']))
            if sum(p['end_cp']-p['start_cp'] for p in spans)>self.profile['max_source_excerpt_chars']:
                raise ProposalError('excerpt limit exceeded; select a smaller exact range')
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

    def commit_selection(self,view,d):
        plans=self.validate_selection(view,d)
        with self.work.transaction(): self.persist_selection(view,d,plans)

    def apply_turn(self,view,d):
        protocol.validate('TurnDecision',d)
        for action in d['actions']: self.sources.validate_action(action,set(view['offered_handles']))
        plans=self.validate_selection(view,d['source_selection']) if d['source_selection'] is not None else []
        legacy={k:d[k] for k in ('actions','assessments','relation_assessments','intent','reason')}
        legacy.update(candidate_decisions=[],route_decisions=[],question_updates=[])
        with self.work.transaction():
            applied=super().apply_turn(view,legacy)
            if applied and d['source_selection'] is not None: self.persist_selection(view,d['source_selection'],plans)
        return applied

    def progress_key(self):
        # Reason rewrites and empty search argument variations do not count as progress.
        shown=[tuple(r) for r in self.work.db.execute("SELECT DISTINCT p.evidence_id,p.delivered_text_hash FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED' ORDER BY 1")]
        judgments=[]
        for h in self.work.heads(current=True):
            if h['kind'] not in ('source_selection','assessment','relation_assessment'): continue
            p={k:v for k,v in h['payload'].items() if k not in ('reason','relevance_reason','summary','view_id')}
            judgments.append([h['entity_id'],p])
        return digest({'shown':shown,'judgments':judgments,'relations':[n.get('semantic_hash',n['notice_hash']) for n in self.work.notices()]})

    def investigate(self):
        result=super().investigate()
        if not self.metadata_only and self.gateway:
            for _ in range(self.profile['source_selection_attempts']):
                try:
                    view=self.view('select_sources')
                    if not view['exact_evidence']: break
                    d=self.generate_checked('select_sources','SourceSelectionDecision',self.commit_selection,initial_view=view,required=())
                    if d['selections'] or d['pending'] or d['rejected']: break
                except (ProposalError,BudgetExhausted,DeadlineExceeded,TransportError) as exc:
                    self.errors.append({'code':exc.code,'message':str(exc)})
                    with self.work.transaction(): self.work.event('SOURCE_SELECTION_RECOVERY',self.errors[-1])
                    break  # The owning checked decision already exhausted its correction.
            result=self.retrieval()
        return result

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
        return meta

    def answer_and_review(self,assembled):
        result,control=super().answer_and_review(assembled)
        if control['decision']=='FINAL':
            bundle=self.build_bundle()
            result['assembly']['term_agent']['source_bundle']=bundle
            result['assembly']['term_agent']['source_selection_status']=bundle['status']
            result['answer']['provider_receipt']['implementation']=IMPLEMENTATION
        return result,control
