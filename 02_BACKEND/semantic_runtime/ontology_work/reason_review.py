"""Adapt the common review ledger to existing ontology work CAS and object storage."""
from copy import deepcopy

from ..contracts import digest
from ..legal_agent import reason_decision_review as review
from ..legal_agent.errors import ContractError


class Ledger:
    def __init__(self, workflow, binding):
        self.workflow = workflow
        self.binding = deepcopy(binding)
        self.revisions = {}

    def output_decision_state(self, key):
        bid = 'rc-' + key
        row = self.workflow.repo.latest(bid)
        self.revisions[key] = row['revision'] if row else 0
        if not row:return None
        document = self.workflow.store.get(row['work_hash'])
        if (document.get('version') != review.VERSION or document.get('bundle_id') != bid
                or document.get('scope_binding') != self.binding):
            raise ContractError('ontology consistency ledger binding changed')
        value = document['value']
        if digest(value) != document['value_hash']:
            raise ContractError('ontology consistency ledger hash mismatch')
        return deepcopy(value)

    def output_decision_event(self, value):
        key = value['decision_key'];bid = 'rc-' + key
        # Use the revision observed by state(), never silently rebase a reservation.
        if key not in self.revisions:
            raise ContractError('ontology review write requires a read revision')
        document = {'version': review.VERSION, 'bundle_id': bid, 'scope_binding': self.binding,
                    'value': deepcopy(value), 'value_hash': digest(value)}
        object_hash = self.workflow.store.put(document)
        revision = self.workflow.repo.draft(bid, object_hash, self.revisions[key],
                                            self.workflow.actor, status='INPUT')
        self.revisions[key] = revision


def check(workflow, *, stage, context, proposal, identity, deadline, max_reviews, binding_check=None):
    binding = {'actor': workflow.actor, 'job': identity,
        'scope': workflow.scope(workflow.document_ids), 'producer': workflow.producer_binding}
    ledger = Ledger(workflow, binding)

    def current():
        if workflow.clock() >= deadline:
            raise review.ReviewUnavailable('ontology review reached the original job deadline')
        if binding_check:binding_check()

    def invoke(prompt, body, schema):
        current()
        generate=workflow.review_generate or workflow.generate
        if generate is None:
            raise review.ReviewUnavailable('ontology consistency model is not configured')
        return generate(prompt, {**body, 'operation': 'REASON_DECISION_REVIEW',
            'call_budget': {'maximum': max_reviews, 'absolute_deadline': min(deadline,workflow.clock()+180)}}, schema)

    return review.review(ledger, stage=stage, context=context, proposal=proposal,
        binding=binding, invoke=invoke, max_reviews=max_reviews, check_current=current)
