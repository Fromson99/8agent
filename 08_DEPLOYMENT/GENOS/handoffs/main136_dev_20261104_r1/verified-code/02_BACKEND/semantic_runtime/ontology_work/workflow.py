from copy import deepcopy
import uuid
from jsonschema import ValidationError
from ..contracts import digest
from ..legal_agent.errors import ContractError
from ..legal_agent import ontology_scenarios as scenarios
from . import schema

class Workflow:
    def __init__(self,repo,store,*,actor,source_reader,generate=None):
        if not isinstance(actor,str) or not actor.strip():raise ContractError('authenticated reviewer identity required')
        self.repo,self.store,self.actor,self.source_reader,self.generate=repo,store,actor,source_reader,generate
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
        self.verify_sources(work)
        if self.generate is None:raise ContractError('ontology authoring model not configured')
        context=deepcopy(work);attempts=[];request_id=uuid.uuid4().hex
        # Store a reservation before the call. A failed/unknown transport is never retried.
        self.store.put({'request_id':request_id,'status':'STARTED','input':work,'actor':self.actor})
        for attempt in range(2):
            try:proposal,receipt=self.generate(schema.PROMPT,context,schema.PROPOSAL_SCHEMA)
            except Exception as e:
                self.store.put({'request_id':request_id,'status':'UNKNOWN','error_type':type(e).__name__,'attempts':attempts})
                raise
            try:
                schema.recipe_for(work,proposal,'cb-proposal-check')
            except (ContractError,ValidationError) as e:
                attempts.append({'proposal':proposal,'receipt':receipt,'error':str(e)[:1600]})
                self.store.put({'request_id':request_id,'status':'INVALID','attempt':attempt+1,'detail':attempts[-1]})
                if attempt:raise
                context={**work,'previous_proposal':proposal,'structural_error':str(e)[:1600],
                    'repair':'원문과 의미를 유지하며 지적된 구조·참조·인용 오류만 한 번 보완한다.'}
                continue
            # A source/SQL/storage failure is not a model formatting failure.
            try:
                result=self.save(work,proposal,bundle_id=bundle_id,expected_revision=expected_revision)
            except Exception as exc:
                self.store.put({'request_id':request_id,'status':'SAVE_UNCONFIRMED','proposal':proposal,
                    'provider_receipt':receipt,'error_type':type(exc).__name__})
                raise
            self.store.put({'request_id':request_id,'status':'DRAFT_CREATED','draft':result,'attempts':attempts,'provider_receipt':receipt})
            return result
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
