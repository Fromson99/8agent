"""Question-scoped source judgments and relation-dependent claim completion."""
import json
from ..contracts import digest
from .tools_session import ToolsSession, strings
from .session import LegalSession
from . import relations_protocol as protocol
from .relations_policy import IMPLEMENTATION
from .errors import ProposalError


class RelationsSession(ToolsSession):
    def assessment_key(self,a):
        return self.work.assessment_id(a['evidence'],a['question_ref'])

    def relation_key(self,r,q):
        return self.work.assessment_id(r,q)

    def check_spans(self,view,spans):
        for span in spans:
            e=self.work.evidence(span['evidence']); self.work.visible(view['view_id'],[span['evidence']])
            if not any(p['block_id']==span['block_id'] and p['start_cp']<=span['start_cp']<span['end_cp']<=p['end_cp'] for p in e['spans']):
                raise ProposalError('basis span outside exact presented evidence')

    def relation_state(self,n,evidence_ids):
        evidence=[self.work.evidence(e) for e in evidence_ids]
        def covers_witness(w):
            end=w['start_cp']
            for a,b in sorted((p['start_cp'],p['end_cp']) for e in evidence if e['document_id']==w['document_id'] for p in e['spans'] if p['block_id']==w['block_id']):
                if b<=end: continue
                if a>end: break
                end=max(end,b)
            return end>=w['end_cp']
        witness=all(covers_witness(w) for w in n['witness_spans'])
        target_ids=[]; coverage=bool(n['targets'])
        for card in n['targets']:
            target=self.sources.resolve(card['target'],'PU')
            relevant=[e for e in evidence if e['document_id']==target['document_id'] and set(self.sources.block_ids(target)) & {p['block_id'] for p in e['spans']}]
            target_ids.extend(e['evidence_id'] for e in relevant)
            coverage=coverage and self.sources.covers(target,relevant)
        return {'witness_presented':bool(n['witness_spans']) and witness,
                'target_presented':bool(target_ids),'target_read_coverage':coverage,'target_evidence':sorted(set(target_ids))}

    def view(self,phase,*,required=(),extra=None):
        from .relation_views import build_view
        return build_view(self,phase,required,extra)

    def validate_relation_assessment(self,view,a):
        self.qrefs([a['question_ref']]); n=self.work.notice(a['relation_id'])
        self.work.item_visible(view['view_id'],'relation',n['relation_id'],n['notice_hash'])
        self.work.visible(view['view_id'],a['source_evidence']+a['target_evidence'])
        self.check_spans(view,a['basis_spans'])
        if set(p['evidence'] for p in a['basis_spans'])-set(a['source_evidence']+a['target_evidence']):
            raise ProposalError('relation basis must belong to selected endpoints')
        if a['decision']!='DEFER':
            if not a['source_evidence'] or not a['basis_spans']:
                raise ProposalError('resolved relation assessment needs source basis')
            if n['source_evidence'] and not set(n['source_evidence']) & set(a['source_evidence']):
                raise ProposalError('relation assessment source mismatch')
            if a['reason_basis']=='UNRESOLVED': raise ProposalError('resolved relation needs a resolved reason basis')
            if a['reason_basis']=='SOURCE_AND_TARGET' and not a['target_evidence']:
                raise ProposalError('target-content reason requires presented target evidence')
        if a['target_evidence'] and n['targets']:
            allowed=set()
            for card in n['targets']:
                target=self.sources.resolve(card['target'],'PU')
                for e in a['target_evidence']:
                    raw=self.work.evidence(e)
                    if raw['document_id']==target['document_id'] and set(self.sources.block_ids(target)) & {p['block_id'] for p in raw['spans']}: allowed.add(e)
            if set(a['target_evidence'])-allowed: raise ProposalError('relation target evidence mismatch')

    def apply_turn(self,view,decision):
        protocol.validate('TurnDecision',decision)
        key='turn:'+view['view_id']; signature=digest(decision)
        old=self.work.db.execute('SELECT payload_json FROM event WHERE event_id=?',(key,)).fetchone()
        if old:
            if json.loads(old[0])['hash']!=signature: raise ProposalError('view reused with different decision')
            return False
        self.work.check_view(view['view_id'],'investigate'); offered=strings(view)
        for a in decision['actions']: self.sources.validate_action(a,offered)
        seen=set()
        for a in decision['assessments']:
            ident=self.assessment_key(a)
            if ident in seen: raise ProposalError('duplicate question/evidence assessment')
            seen.add(ident); self.qrefs([a['question_ref']]); self.work.visible(view['view_id'],[a['evidence']])
            self.check_spans(view,a['basis_spans'])
            if any(p['evidence']!=a['evidence'] for p in a['basis_spans']): raise ProposalError('assessment basis evidence mismatch')
            for r in a['related_relation_ids']:
                n=self.work.notice(r); self.work.item_visible(view['view_id'],'relation',r,n['notice_hash'])
        seen=set()
        for a in decision['relation_assessments']:
            ident=self.relation_key(a['relation_id'],a['question_ref'])
            if ident in seen: raise ProposalError('duplicate relation/question assessment')
            seen.add(ident); self.validate_relation_assessment(view,a)
        for field,name,kind in [('candidate_decisions','candidate','PU'),('route_decisions','route','L')]:
            for d in decision[field]:
                self.sources.resolve(d[name],kind)
                if d[name] not in offered: raise ProposalError('decision target not offered')
        for q in decision['question_updates']: self.qrefs(q['question_refs'])
        if decision['intent']=='DRAFT' and view.get('omitted_action_results'):
            delivered_before=set()
            for row in self.work.db.execute("SELECT DISTINCT v.body_json FROM model_view v JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED' AND v.view_id!=?",(view['view_id'],)):
                delivered_before.update(o['observation_id'] for o in json.loads(row[0]).get('last_action_results',[]))
            unseen=[o for o in view['omitted_action_results'] if o['observation_id'] not in delivered_before]
            if unseen: raise ProposalError('new tool results omitted from view; inspect before drafting')
        if decision['intent']=='DRAFT' and decision['actions']:
            raise ProposalError('observe new action results before drafting')
        with self.work.transaction():
            seq=self.work.event('TOOL_TURN_V3',{'hash':signature,'decision':decision},event_id=key,advance=True)
            for a in decision['assessments']:
                ident=self.assessment_key(a)
                old=next((h for h in self.work.heads('assessment',current=True) if h['entity_id']==ident),None)
                if old and old['payload']==a: continue
                # A newly introduced challenge affects claims on this question only.
                if a['role']=='CHALLENGE':
                    for c in self.work.heads('claim',current=True):
                        if a['question_ref'] in c['payload']['question_refs']: self.work.invalidate('claim',c['entity_id'],c['version'])
                self.work.put('assessment',ident,a,seq,evidence_ids=[a['evidence']])
            for a in decision['relation_assessments']:
                ident=self.relation_key(a['relation_id'],a['question_ref'])
                old=next((h for h in self.work.heads('relation_assessment',current=True) if h['entity_id']==ident),None)
                if old and old['payload']==a: continue
                self.work.put('relation_assessment',ident,a,seq,dependencies=[('relation',a['relation_id'])],
                    evidence_ids=a['source_evidence']+a['target_evidence'])
            for field,name in [('candidate_decisions','candidate'),('route_decisions','route')]:
                for d in decision[field]: self.work.put('intent',d[name],d,seq)
            for q in decision['question_updates']:
                for ident in q['question_refs']:
                    for h in self.work.heads('assessment',current=True):
                        if h['payload']['question_ref']==ident: self.work.invalidate('assessment',h['entity_id'],h['version'])
                    for h in self.work.heads('relation_assessment',current=True):
                        if h['payload']['question_ref']==ident: self.work.invalidate('relation_assessment',h['entity_id'],h['version'])
                    self.work.put('intent',ident,q,seq)
            self.work.db.execute('UPDATE stage_artifact SET valid=0')
        self.intent=decision['intent']
        for i,a in enumerate(decision['actions']):
            self.sources.execute(a,f'{view["view_id"]}:{i}',actor='MODEL',view_id=view['view_id'])
        return True

    def investigate(self):
        from .tools_policy import metadata_only_request
        if not self.context.request['use_llm'] or metadata_only_request(self.context.request['question']):
            # Reuse catalogue filtering without manufacturing a model purpose.
            original=self.sources.execute
            def metadata(action,ident):
                return original({**action,'question_refs':[],'expected_information':'요청 범위의 자료 목록'},ident,actor='SYSTEM_POLICY')
            self.sources.execute=metadata
            try: return super().investigate()
            finally: self.sources.execute=original
        self.sources._actor='REVIEWER' if self.pending else 'MODEL'
        try: return super().investigate()
        finally: self.sources._actor='MODEL'

    def relation_requirements(self,p,view):
        required=set(p['relation_dependencies']); deps=[]
        for e in p['evidence']:
            scan=self.work.db.execute("SELECT status FROM relation_scan WHERE anchor=? AND family='reference'",(e,)).fetchone()
            if not scan or scan[0]!='COMPLETE': raise ProposalError('reference scan incomplete for adopted evidence')
            for n in self.work.notices():
                if e in n['source_evidence'] and n['completion_required']: required.add(n['relation_id'])
            if any(h['entity_id']==e for h in self.work.heads('relation_set',current=True)): deps.append(('relation_set',e))
        joint=set(p['evidence'])
        for rid in sorted(required):
            n=self.work.notice(rid); self.work.item_visible(view['view_id'],'relation',rid,n['notice_hash'])
            deps.append(('relation',rid))
            for q in p['question_refs']:
                ident=self.relation_key(rid,q); a=self.work.head('relation_assessment',ident)['payload']
                deps.append(('relation_assessment',ident)); joint.update(a['source_evidence']+a['target_evidence'])
                if a['decision']=='DEFER': raise ProposalError('claim depends on deferred relation')
                if a['decision']=='NOT_RELEVANT':
                    if rid in p['relation_dependencies']: raise ProposalError('excluded relation declared as dependency')
                    continue
                if rid not in p['relation_dependencies']: raise ProposalError('relevant relation dependency omitted')
                state=self.relation_state(n,a['source_evidence']+a['target_evidence'])
                if n['family']=='reference' and (not state['witness_presented'] or n.get('unresolved')):
                    raise ProposalError('relation witness or target resolution incomplete')
                if not state['target_read_coverage']: raise ProposalError('relation target coverage incomplete')
        self.work.visible(view['view_id'],joint)
        return sorted(required),deps,sorted(joint)

    def commit_draft(self,view,draft):
        protocol.validate('Draft',draft); self.work.check_view(view['view_id'],'compose')
        accepted=[]
        for p in draft['paragraphs']:
            self.qrefs(p['question_refs']); self.work.visible(view['view_id'],p['evidence'])
            deps=[]
            for q in p['question_refs']:
                support=False
                for e in p['evidence']:
                    ident=self.work.assessment_id(e,q); a=self.work.head('assessment',ident)['payload']
                    if a['disposition']!='ADOPT' or a['role']=='CHALLENGE': raise ProposalError('claim requires question-specific adopted evidence')
                    support=support or a['role']=='SUPPORT'; deps.append(('assessment',ident))
                if not support: raise ProposalError('claim lacks question-specific support')
            try:
                _,relations,_=self.relation_requirements(p,view)
            except ProposalError as exc:
                # Independent paragraphs can be reviewed and published while this one stays bounded.
                self.errors.append({'code':'RELATION_INCOMPLETE','message':str(exc)})
                with self.work.transaction(): self.work.event('CLAIM_DEFERRED',{'paragraph':p,'reason':str(exc)})
                continue
            accepted.append((p,deps+relations))
        with self.work.transaction():
            seq=self.work.event('DRAFT_V3',{'draft':draft,'accepted_count':len(accepted)},advance=True)
            for old in self.work.heads('claim',current=True):
                if old['payload'] not in [p for p,_ in accepted]: self.work.invalidate('claim',old['entity_id'],old['version'])
            for p,deps in accepted:
                if any(h['payload']==p for h in self.work.heads('claim',current=True)): continue
                ident='C'+str(self.work.db.execute("SELECT count(*) FROM entity_head WHERE kind='claim'").fetchone()[0]+1)
                self.work.put('claim',ident,p,seq,dependencies=deps,evidence_ids=p['evidence'])
        self.blocked_claims=len(draft['paragraphs'])-len(accepted)
        self.question_review=None

    def commit_review(self,view,review):
        self.gateway.protocol.validate('ReviewDecision',review); self.work.check_view(view['view_id'],'review')
        claims={h['entity_id']:h for h in self.work.heads('claim',current=True)}
        if len(review['checks'])!=len(claims) or {c['claim'] for c in review['checks']}!=set(claims): raise ProposalError('each current claim needs one review')
        if set(review['question']['question_refs'])!={q['id'] for q in self.context.pieces}: raise ProposalError('review must cover original question')
        commits=[]
        for c in review['checks']:
            p=claims[c['claim']]['payload']; self.work.visible(view['view_id'],c['evidence'])
            relations,deps,joint=self.relation_requirements(p,view)
            if set(relations)-set(c['relation_checks']): raise ProposalError('review relation checks omitted')
            if set(c['relation_checks'])-set(relations): raise ProposalError('review includes unrelated relation')
            challenges=[h for h in self.work.heads('assessment',current=True) if h['payload']['role']=='CHALLENGE' and h['payload']['question_ref'] in p['question_refs']]
            if c['verdict']=='SUPPORTED' and (set(joint)|{a['payload']['evidence'] for a in challenges})-set(c['evidence']): raise ProposalError('review must compare joint source/target and challenge evidence')
            if not c['evidence']: raise ProposalError('review needs exact evidence')
            if c['verdict']=='NEEDS_RESEARCH' and not c['actions']: raise ProposalError('research requires an action')
            for a in c['actions']: self.sources.validate_action(a,strings(view))
            commits.append((c,[('claim',c['claim'])]+deps+[('assessment',h['entity_id']) for h in challenges]))
        with self.work.transaction():
            seq=self.work.event('REVIEW_V3',review,advance=True)
            for c,deps in commits: self.work.put('review',c['claim'],c,seq,dependencies=deps,evidence_ids=c['evidence'])
            if hasattr(self, 'commit_obligation_review'): self.commit_obligation_review(review, seq)
        self.question_review=review['question']
        self.sources._view_id=view['view_id']

    def metadata(self,*,final=False,gate=None):
        meta=LegalSession.metadata(self,final=final,gate=gate); meta['implementation']=IMPLEMENTATION
        limit=min(64,self.profile['max_summary_items']); coverage=self.work.coverage(final=final)
        actions=self.sources.action_summaries(); notices=self.work.notices()
        outstanding=[{'evidence':r['evidence'],'state':r['status']} for r in coverage if r['status']!='ASSESSED']
        scans=[dict(r) for r in self.work.db.execute('SELECT anchor,family,status,next_cursor FROM relation_scan')]
        for r in scans:
            if r['status']!='COMPLETE': outstanding.append({'anchor':r['anchor'],'family':r['family'],'state':r['status']})
        for r in self.work.db.execute("SELECT task_id,status FROM system_task WHERE status!='DONE'"):
            outstanding.append({'task_id':r[0],'state':r[1]})
        for r in coverage:
            if any(a['disposition']=='DEFER' for a in r['assessments']): outstanding.append({'evidence':r['evidence'],'state':'DEFER'})
        presented=[r['evidence'] for r in coverage if r['presented']]
        checks=[]
        for n in notices:
            assessments=[h for h in self.work.heads('relation_assessment') if h['payload']['relation_id']==n['relation_id']]
            state=self.relation_state(n,[e['evidence_id'] for e in self.work.evidence()])
            checks.append({'relation_id':n['relation_id'],'family':n['family'],'predicate':n['predicate'],
                'direction':n['direction'],'resolution':n['resolution'],'target_read':state['target_read_coverage'],
                'target_labels':[(c['document_name']+' '+str(c.get('coordinate') or c.get('title') or '')).strip() for c in n['targets']],
                'target_presented':self.relation_state(n,presented)['target_presented'],
                'witness_presented':self.relation_state(n,presented)['witness_presented'],
                'assessments':[{'version':h['version'],'validity':h['validity'],**h['payload']} for h in assessments]})
            if n['completion_required'] and (not assessments or any(h['validity']!='CURRENT' or h['payload']['decision']=='DEFER' for h in assessments)): outstanding.append({'relation_id':n['relation_id'],'state':'UNASSESSED'})
        history=[]
        for row in self.work.db.execute("SELECT kind,entity_id,version,payload_json FROM entity_version WHERE kind IN ('assessment','relation_assessment') ORDER BY created_seq,entity_id"):
            a=json.loads(row['payload_json'])
            history.append({'kind':row['kind'],'assessment_id':row['entity_id'],'version':row['version'],
                'question_ref':a['question_ref'],'evidence':a.get('evidence'),'relation_id':a.get('relation_id'),
                'decision':a.get('disposition') or a.get('decision'),'reason':a['reason']})
        summary={'schema_version':'tool-exploration-v3','action_summary':actions[:limit],
            'evidence_decisions':coverage[:limit],'relation_checks':checks[:limit], 'outstanding_checks':outstanding[:limit],
            'assessment_history':history[-limit:],
            'totals':{'assessment_versions':len(history),'actions':len(actions),'evidence':len(coverage),'relations':len(checks),'outstanding':len(outstanding)},
            'truncated':any(len(x)>limit for x in (actions,coverage,checks,outstanding,history)),
            'audit':{'run_id':self.context.run_id,'revision':self.work.run()['state_revision'],
                     'hash':digest({'binding':self.context.binding_hash,'actions':actions,'coverage':coverage,'relations':checks,'scans':scans}), 'complete':final}}
        # No source text, wire output, paths or provider credentials in this projection.
        for row in summary['evidence_decisions']:
            for a in row['assessments']: a.pop('basis_spans',None)
        for row in summary['relation_checks']:
            for a in row['assessments']: a.pop('basis_spans',None)
        from .audit_summary import display_lines
        summary['display_lines']=display_lines(summary)
        protocol.validate('AuditSummary',summary)
        meta['exploration_v3']=summary
        return meta

    def answer_and_review(self,assembled):
        result,control=super().answer_and_review(assembled)
        if getattr(self,'blocked_claims',0) and self.cycles<self.profile['max_cycles'] and self.work.budget()['model_reserved']<self.profile['max_model_attempts']-self.profile['finalization_reserve']:
            control['decision']='RESEARCH'; control['gate']='BOUNDED'; self.next_mode='RESEARCH'
        final=control['decision']=='FINAL'
        if final:
            self.work.stop_pending('request finalized; remaining source judgments not fabricated')
            missing=[r for r in self.work.coverage(final=True) if r['status']!='ASSESSED']
            if missing or getattr(self,'blocked_claims',0):
                reason=f'원문 미평가 {len(missing)}건, 관계 확인 미완료 주장 {getattr(self,"blocked_claims",0)}건이 남았습니다.'
                self.limitations.append(reason)
                result['answer']['unresolved'].append({'reason':reason})
                result['answer']['text']+='\n\n확인 한계: '+reason
                if control['gate']=='READY': control['gate']='BOUNDED'
            with self.work.transaction():
                self.work.event('CONTROL',control)
                self.work.db.execute('UPDATE run SET gate=? WHERE singleton=1',(control['gate'],))
        if not final:
            with self.work.transaction():
                self.work.event('CONTROL',control)
                self.work.db.execute('UPDATE run SET gate=? WHERE singleton=1',(control['gate'],))
        result['assembly']['term_agent']=self.metadata(final=final,gate=control['gate'])
        result['answer']['provider_receipt']['implementation']=IMPLEMENTATION
        return result,control
