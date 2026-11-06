from copy import deepcopy
import uuid
from ..contracts import digest
from ..legal_agent.errors import ContractError
from ..legal_agent import ontology_scenarios as scenarios
from . import schema

class Workflow:
    def __init__(self,repo,store,*,actor,source_reader,generate=None,review_generate=None):
        if not isinstance(actor,str) or not actor.strip():raise ContractError('authenticated reviewer identity required')
        self.repo,self.store,self.actor,self.source_reader,self.generate=repo,store,actor,source_reader,generate
        self.review_generate=review_generate
    def verify_sources(self,work):
        schema.validate_input(work)
        for original in work['originals']:
            actual=self.source_reader(original['anchor'])
            if actual!=original['text']:raise ContractError('source missing, changed or unauthorized')
    def save(self,work,proposal,*,bundle_id=None,expected_revision=0):
        self.verify_sources(work)
        bid=bundle_id or 'cb-'+uuid.uuid4().hex
        if not __import__('re').fullmatch(r'cb-[a-zA-Z0-9_-]{1,80}',bid):raise ContractError('invalid bundle ID')
        schema.recipe_for(work,proposal,bid)
        document={'version':schema.VERSION,'bundle_id':bid,'input':deepcopy(work),'proposal':deepcopy(proposal),'created_at':schema.now()}
        key=self.store.put(document)
        rev=self.repo.draft(bid,key,expected_revision,self.actor)
        return {'bundle_id':bid,'revision':rev,'work_hash':key,'status':'DRAFT'}
    def enqueue(self,work):
        self.verify_sources(work)
        bid='cb-'+digest(work)[:40]
        previous=self.repo.latest(bid)
        if previous:return {'bundle_id':bid,**previous,'reused':True}
        key=self.store.put({'version':schema.VERSION,'bundle_id':bid,'input':deepcopy(work),
            'proposal':None,'created_at':schema.now()})
        rev=self.repo.draft(bid,key,0,self.actor,status='INPUT')
        return {'bundle_id':bid,'revision':rev,'work_hash':key,'status':'INPUT'}
    def propose(self,work,*,bundle_id=None,expected_revision=0):
        from .reason_review import Ledger
        from ..legal_agent import reason_decision_review as review, output_contract as output
        import time
        self.verify_sources(work)
        if self.generate is None:raise ContractError('ontology authoring model not configured')
        bid=bundle_id or 'cb-'+digest([self.actor,work,review.VERSION])[:40]
        binding={'actor':self.actor,'input_hash':digest(work),'bundle_id':bid,
                 'expected_revision':expected_revision,'review_version':review.VERSION}
        ledger=Ledger(self,binding)
        admission_key=digest([binding,'admission'])
        admission=ledger.output_decision_state(admission_key)
        if admission is None:
            admission={'decision_key':admission_key,'deadline':time.time()+360}
            ledger.output_decision_event(admission)
        deadline=admission['deadline']
        def current():
            self.verify_sources(work)
            old=self.repo.latest(bid)
            if old and old['revision'] not in (expected_revision,expected_revision+1):
                raise ContractError('scenario work revision changed')
        def generate(prompt,payload,wire,*,reviewing=False):
            current()
            if time.time()>=deadline:raise review.ReviewUnavailable('scenario generation deadline exhausted')
            model=(self.review_generate or self.generate) if reviewing else self.generate
            attempt_deadline=min(deadline,time.time()+180)
            result=model(prompt,{**payload,'call_budget':{
                'maximum':4,'absolute_deadline':attempt_deadline}},wire)
            if time.time()>=attempt_deadline:raise review.ReviewUnavailable('late scenario model result rejected')
            current()
            return result
        def propose(payload,attempt):
            value,receipt=generate(schema.PROMPT+'\n'+review.RECONSIDER,payload,schema.PROPOSAL_SCHEMA)
            return {'proposal':value,'provider_receipt':receipt}
        def validate(value):
            try:schema.recipe_for(work,value['proposal'],'cb-proposal-check')
            except ContractError as exc:
                raise output.DecisionConflict(str(exc)) from exc
            current()
            review.review(ledger,stage='ONTOLOGY_SCENARIO',context=work,proposal=value['proposal'],
                binding=binding,invoke=lambda p,b,s:generate(p,b,s,reviewing=True),check_current=current)
        result=output.bounded_decision(ledger,'scenario-author',work,schema.PROPOSAL_SCHEMA,
            propose,validate,identity=binding)
        current()
        old=self.repo.latest(bid)
        if old and old['revision']==expected_revision+1:
            saved=self.load(bid)
            if saved['input']==work and saved['proposal']==result['proposal']:
                return {'bundle_id':bid,**old,'reused':True}
            raise ContractError('scenario saved result differs from accepted proposal')
        return self.save(work,result['proposal'],bundle_id=bid,expected_revision=expected_revision)
    def load(self,bid):
        row=self.repo.latest(bid)
        if row is None:raise ContractError('unknown work bundle')
        document=self.store.get(row['work_hash'])
        if document['bundle_id']!=bid:raise ContractError('work identity mismatch')
        if document.get('version')!=schema.VERSION:raise ContractError('use the domain-profile reader for this work version')
        return {**row,**document}
    def preview(self,bid):
        d=self.load(bid);self.verify_sources(d['input'])
        return scenarios.compile_package(schema.recipe_for(d['input'],d['proposal'],bid),d['input']['originals'])
    def review(self,bid,revision,work_hash,approve,reason):
        d=self.load(bid)
        if d['revision']!=revision or d['work_hash']!=work_hash:raise ContractError('reviewed screen is stale')
        if not reason.strip():raise ContractError('review reason required')
        if approve:self.preview(bid)
        return self.repo.review(bid,revision,work_hash,self.actor,approve,reason)
    def publish(self,bid,revision,work_hash,expected_sequence):
        d=self.load(bid)
        if d['revision']!=revision or d['work_hash']!=work_hash or d['status']!='APPROVED':raise ContractError('publication requires exact approved screen')
        self.verify_sources(d['input'])
        # Deterministic authoring timestamp: retries after unknown commit must resolve
        # the same publication ID, not compile a new receipt with a fresh timestamp.
        payload=schema.published(d['input'],d['proposal'],bid,revision,d['approval'])
        bundle=payload['snapshot']['bundles'][0]
        bundle['proposed_by']['at']=d['created_at']
        bundle['history'][0]['time_note']='Actual creation/review/publication times are immutable DB events.'
        payload['snapshot_sha256']=digest(payload['snapshot'])
        return self.repo.publish(bid,revision,work_hash,d['approval'],payload,expected_sequence,self.actor)
