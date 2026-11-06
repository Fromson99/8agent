"""The v2 authoring path on the existing SQL work/event and content store.

No DDL or automatic publication is required. INPUT/DRAFT remain SQL envelope
states; phase/status inside immutable job objects describes computation outcomes.
"""
from copy import deepcopy
import re
import time
import uuid
from ..contracts import digest
from ..legal_agent.errors import ContractError
from .workflow import Workflow
from . import profile as profiles, observations as obs, accumulation as acc
from . import assembly_compiler as compiler
from .assembly_ir import validate_originals
from . import recorded_fields, authoring_semantics as semantics


class SaveUnconfirmed(ContractError):
    def __init__(self, key):
        self.object_hash = key
        super().__init__('SAVE_UNCONFIRMED: same stored result can be reconciled: ' + key)


class DomainWorkflow(Workflow):
    # Existing records without a stored limit were admitted for two attempts.
    job_attempt_limit = 2

    def __init__(self, *args, namespace, source_snapshot, acl_ref, document_ids, glossary,
                 producer_binding, clock=time.time, **kwargs):
        super().__init__(*args, **kwargs)
        if not all(isinstance(x, str) and x.strip() for x in
                   (namespace, source_snapshot, acl_ref, producer_binding)):
            raise ContractError('operator-managed domain workflow binding required')
        self.namespace, self.source_snapshot, self.acl_ref = namespace, source_snapshot, acl_ref
        self.document_ids, self.glossary = frozenset(document_ids), glossary
        self.producer_binding, self.clock = producer_binding, clock

    def scope(self, document_ids=()):
        if not set(document_ids) <= self.document_ids:
            raise ContractError('domain object outside operator scope')
        return {'namespace': self.namespace, 'acl_ref': self.acl_ref,
                'document_ids': sorted(set(document_ids)), 'source_snapshot': self.source_snapshot}

    def check_scope(self, document):
        s = document['scope']
        if s != self.scope(s['document_ids']):
            raise ContractError('object scope/snapshot changed')

    def _save(self, bid, document, expected, *, state='DRAFT'):
        key = self.store.put({'version': 'ontology-domain-work-v1', 'bundle_id': bid,
                              **deepcopy(document)})
        old = self.repo.latest(bid)
        if old and old['work_hash'] == key:
            return {'bundle_id': bid, **old, 'reused': True}
        if (old['revision'] if old else 0) != expected:
            raise ContractError('stale domain work revision')
        try:
            rev = self.repo.draft(bid, key, expected, self.actor, status=state)
        except ContractError:
            raise
        except Exception as exc:
            raise SaveUnconfirmed(key) from exc
        return {'bundle_id': bid, 'revision': rev, 'work_hash': key, 'status': state, 'reused': False}

    def load(self, bid, revision=None):
        row = self.repo.revision(bid, revision) if revision else self.repo.latest(bid)
        if row is None:
            raise ContractError('unknown domain object')
        document = self.store.get(row['work_hash'])
        if document.get('version') != 'ontology-domain-work-v1' or document.get('bundle_id') != bid:
            raise ContractError('domain object identity/version')
        self.check_scope(document)
        return {**document, **row}

    def save_profile(self, domain, business=None, *, expected_revision=0):
        profile = profiles.compile_profile(domain, business)
        bid = 'dp-' + digest([self.namespace, domain['profile_id'], (business or {}).get('profile_id')])
        return self._save(bid, {'kind': 'PROFILE', 'scope': self.scope(), 'profile': profile}, expected_revision)

    def review_profile(self, bid, revision, work_hash, approve, reason):
        d = self.load(bid)
        if d['kind'] != 'PROFILE' or not reason.strip() or (d['revision'], d['work_hash']) != (revision, work_hash):
            raise ContractError('exact profile review required')
        profiles.verify_profile(d['profile'])
        return self.repo.review(bid, revision, work_hash, self.actor, approve, reason)

    def selected_profile(self, bid, work_hash):
        d = self.load(bid)
        if d['kind'] != 'PROFILE' or d['work_hash'] != work_hash or d['status'] != 'APPROVED':
            raise ContractError('exact approved profile required')
        profiles.verify_profile(d['profile'])
        selected = (d['profile'].get('business') or {}).get('glossary', {}).get('selected_concept_refs', [])
        if selected:
            for ref in selected:
                card = self.glossary.restore(ref['source'], ref['node_id'])
                if ref['concept_id'] != card['concept_id']:
                    raise ContractError('business glossary selection changed')
                self.glossary.check(ref['binding'])
        return d['profile']

    def ingest(self, raw):
        obs.check_envelope(raw)
        if (raw['namespace'], raw['source_snapshot'], raw['acl_ref']) != (self.namespace, self.source_snapshot, self.acl_ref):
            raise ContractError('raw exporter scope mismatch')
        scope = self.scope(raw['document_ids'])
        bid = 'raw-' + digest([raw['namespace'], raw['run_id'], raw['raw_event_id']])
        old = self.repo.latest(bid)
        document = {'kind': 'RAW', 'scope': scope, 'raw': deepcopy(raw)}
        if old and self.load(bid)['raw'] != raw:
            raise ContractError('immutable event ID reused with different content')
        self.store.put(raw)
        return self._save(bid, document, 0)

    def import_payload(self, payload, *, event_id, run_id, sequence=0, format_description=''):
        # Imported prose cannot assert real read/delivery receipts.
        raw = obs.envelope(payload, namespace=self.namespace, run_id=run_id, event_id=event_id,
            sequence=sequence, source_snapshot=self.source_snapshot, producer_binding=self.producer_binding,
            acl_ref=self.acl_ref, document_ids=self.document_ids, format_description=format_description)
        return self.ingest(raw)

    def _job_write(self, bid, document, expected):
        return self._save(bid, document, expected, state='INPUT')

    def _job(self, stage, context, prompt, output_schema, validator, binding_check=None):
        from . import reason_review
        from ..legal_agent import reason_decision_review as common_review
        identity = digest([self.namespace, self.actor, stage, context, prompt, output_schema,
                           self.producer_binding, common_review.VERSION])
        bid = 'job-' + identity
        old = self.repo.latest(bid)
        if old:
            job = self.load(bid)
            if job['phase'] == 'READY':
                if binding_check:binding_check()
                validator(job['response'])
                # READY is written only after a bound PASS. Old job identities
                # cannot be promoted merely by loading them under this version.
                saved_review=job.get('consistency_review',{})
                if (saved_review.get('proposal_hash')!=digest(job['response']) or
                        saved_review.get('version')!=common_review.VERSION or
                        saved_review.get('decision')!={'decision':'PASS'}):
                    raise ContractError('authoring consistency receipt missing or changed')
                return job['response'], job['receipt']
            if job['phase'] not in ('RESPONSE_RECEIVED', 'RESERVED', 'REPAIR_READY'):
                raise ContractError('job is ' + job['phase'] + '; no automatic model replay: ' + bid)
            # A persisted response can be validated again after a process restart.
            start_attempt = job['attempt'] + int(job['phase'] == 'REPAIR_READY')
            attempt_limit = job.get('attempt_limit', 2)
        else:
            if self.generate is None:
                raise ContractError('domain authoring model is not configured')
            attempt_limit = self.job_attempt_limit
            job = {'kind': 'JOB', 'scope': self.scope(self.document_ids), 'stage': stage,
                   'identity': identity, 'context_hash': digest(context), 'phase': 'RESERVED',
                   'deadline': self.clock() + 180 * attempt_limit, 'attempt_limit': attempt_limit, 'attempt': 0, 'attempts': [],
                   'actor': self.actor, 'response': None, 'receipt': None}
            saved = self._job_write(bid, job, 0); job['revision'] = saved['revision']
            start_attempt = 0
        revision = job['revision']
        for attempt in range(start_attempt, attempt_limit):
            if binding_check:
                try:binding_check()
                except Exception as exc:
                    job.update(phase='BINDING_FAILED',error_type=type(exc).__name__)
                    self._job_write(bid,self._document(job),revision);raise
            if job['phase'] != 'RESPONSE_RECEIVED':
                if self.generate is None:
                    raise ContractError('domain authoring model is not configured')
                if self.clock() >= job['deadline']:
                    job['phase'] = 'BUDGET_EXHAUSTED'
                    self._job_write(bid, self._document(job), revision)
                    raise ContractError('job deadline exhausted')
                job.update(phase='SENT', attempt=attempt, attempt_deadline=min(job['deadline'], self.clock() + 180),
                           owner_token=uuid.uuid4().hex)
                saved = self._job_write(bid, self._document(job), revision); revision = saved['revision']
                payload = {**deepcopy(context), 'call_budget': {'attempt': attempt + 1, 'maximum': attempt_limit,
                    'absolute_deadline': job['attempt_deadline']}}
                if job['attempts']:
                    payload['repair'] = {'previous': job['attempts'][-1],
                        'prior_errors': [item['error'] for item in job['attempts']],
                        'instruction': common_review.RECONSIDER if job['attempts'][-1].get('review_issues') else ('원본 입력을 유지하고 나열한 오류를 한 번 보완한다. 원문 분석·비교의 불일치도 고치되 원래 관찰 기록은 고쳐 쓰지 않는다.'
                                        if stage in ('SOURCE_ANALYSIS','ACCUMULATE') else
                                        '같은 입력과 의미를 유지하고 나열한 형식·참조 오류만 한 번 보완한다.')}
                try:
                    response, receipt = self.generate(prompt, payload, output_schema)
                except Exception as exc:
                    from .authoring_model import AuthoringFailure
                    job.update(phase=exc.status if isinstance(exc,AuthoringFailure) else 'UNKNOWN', error_type=type(exc).__name__)
                    if isinstance(exc,AuthoringFailure):job['receipt']=exc.receipt
                    self._job_write(bid, self._document(job), revision)
                    raise
                job.update(phase='RESPONSE_RECEIVED', response=response, receipt=receipt)
                saved = self._job_write(bid, self._document(job), revision); revision = saved['revision']
            if self.clock() >= min(job['deadline'], job.get('attempt_deadline', job['deadline'])):
                job['phase'] = 'BUDGET_EXHAUSTED'
                self._job_write(bid, self._document(job), revision)
                raise ContractError('late model result rejected')
            if binding_check:
                try:binding_check()
                except Exception as exc:
                    job.update(phase='BINDING_FAILED',error_type=type(exc).__name__)
                    self._job_write(bid,self._document(job),revision);raise
            try:
                validator(job['response'])
                try:
                    consistency=reason_review.check(self,stage=stage,context=context,proposal=job['response'],
                        identity=identity,deadline=job['deadline'],max_reviews=attempt_limit,binding_check=binding_check)
                except common_review.ReviewConflict:
                    raise
                except Exception as exc:
                    job.update(phase='REVIEW_UNAVAILABLE',error_type=type(exc).__name__,error=str(exc))
                    self._job_write(bid,self._document(job),revision)
                    raise
                job['consistency_review']=consistency
                job['receipt']={**(job['receipt'] or {}),'reason_decision_review':consistency}
            except ContractError as exc:
                # Scope/ACL/CAS errors and unknown reviewer outcomes are never
                # converted to another primary-model attempt.
                if job['phase']=='REVIEW_UNAVAILABLE':raise
                job['attempts'].append({'response': deepcopy(job['response']), 'receipt': deepcopy(job['receipt']),
                                        'error': str(exc)[:4000],
                                        **({'review_issues':deepcopy(exc.issues)} if isinstance(exc,common_review.ReviewConflict) else {})})
                repeated_review=False
                if isinstance(exc,common_review.ReviewConflict):
                    signature=digest([(r['code'],r['path'],r['related_paths']) for r in exc.issues])
                    repeated_review=any(r.get('review_conflict_signature')==signature for r in job['attempts'][:-1])
                    job['attempts'][-1]['review_conflict_signature']=signature
                exhausted = attempt + 1 >= attempt_limit or repeated_review
                job['phase'] = 'INVALID' if exhausted else 'REPAIR_READY'
                saved = self._job_write(bid, self._document(job), revision); revision = saved['revision']
                if exhausted:
                    raise
                continue
            job['phase'] = 'READY'
            self._job_write(bid, self._document(job), revision)
            return job['response'], job['receipt']

    @staticmethod
    def _document(value):
        return {k: deepcopy(v) for k, v in value.items() if k not in
                ('version', 'bundle_id', 'revision', 'work_hash', 'status', 'reviewer', 'approval', 'reused')}

    def reconcile(self, key, expected_revision):
        document = self.store.get(key); self.check_scope(document)
        if document.get('version') != 'ontology-domain-work-v1':
            raise ContractError('reconcile requires stored domain result')
        # It only saves already stored bytes; it never restarts a model call.
        return self._save(document['bundle_id'], self._document(document), expected_revision,
                          state='INPUT' if document['kind'] == 'JOB' else 'DRAFT')

    def normalize(self, raw_id, *, profile_id, profile_work_hash, labels=None):
        raw = self.load(raw_id)['raw']; profile = self.selected_profile(profile_id, profile_work_hash)
        omitted = 0
        if not labels:labels, omitted = obs.lookup_queries(raw)
        candidates = self.glossary.candidates(labels)
        candidates['query_omissions'] = omitted
        candidates['query_origin'] = 'BOUNDED_LITERAL_CANDIDATES'
        candidates['unsearched'] = candidates['unsearched'] or bool(omitted)
        candidates['candidate_receipt'] = digest({k: v for k, v in candidates.items() if k != 'candidate_receipt'})
        selected = (profile.get('business') or {}).get('glossary', {}).get('selected_concept_refs', [])
        if selected:
            ids = {r['concept_id'] for r in selected}
            candidates['candidates'] = [r for r in candidates['candidates'] if r['concept_id'] in ids]
            candidates['candidate_receipt'] = digest({k: v for k, v in candidates.items() if k != 'candidate_receipt'})
        context = {'raw': raw, 'glossary_candidates': candidates, 'profile_hash': profile['profile_hash']}
        mentions = recorded_fields.glossary_mentions(raw, candidates)
        if mentions:
            context['glossary_mention_options'] = mentions
        output_schema = recorded_fields.request_schema(obs.normalization_schema(raw, profile), raw, mentions)
        def validate(proposal):
            canonical, _ = recorded_fields.restore(proposal, raw, output_schema, obs.restore_normalization, mentions)
            obs.validate_observations(canonical, raw, profile, candidates)
        proposal, receipt = self._job('NORMALIZE', context,
            profile['prompt'] + obs.NORMALIZATION_INSTRUCTIONS + recorded_fields.INSTRUCTIONS +
            ('\n용어를 실제 언급한 경우 glossary_refs.mention_refs에는 glossary_mention_options에서 그 위치의 '
             'M 참조를 고른다. 번호는 해당 원문 안의 위치이며 관찰 순번이 아니다. 이 관찰에서 언급되지 '
             '않은 용어는 연결하지 않는다. 목록에 없는 실제 구절은 기존 정확 인용으로 지정할 수 있다.'
             if mentions else ''), output_schema, validate,
            lambda:self.glossary.verify_candidates(candidates))
        canonical, assembly = recorded_fields.restore(proposal, raw, output_schema, obs.restore_normalization, mentions)
        # The job/provider retain the original proposal; the stored observation keeps
        # the existing canonical contract plus a source-bound assembly receipt.
        receipt = {**receipt, 'normalization_assembly': assembly}
        normalized = obs.normalized(canonical, raw, profile, candidates, receipt)
        bid = 'obs-' + digest([digest(raw), profile['profile_hash'], digest(candidates), self.producer_binding])
        return self._save(bid, {'kind': 'OBSERVATION', 'scope': self.scope(raw['document_ids']),
            'normalized': normalized, 'profile_id': profile_id, 'profile_work_hash': profile_work_hash}, 0)

    def _originals(self, originals):
        validate_originals(originals)
        self.scope([s['anchor']['document_id'] for s in originals])
        for source in originals:
            if self.source_reader(source['anchor']) != source['text']:
                raise ContractError('source version/content/permission changed')

    def _observations(self, ids, profile):
        result = []
        for bid in ids:
            n = self.load(bid)['normalized']
            if n['profile_hash'] != profile['profile_hash']:
                raise ContractError('observation profile differs')
            self.glossary.verify_candidates(n['glossary_candidates'])
            raw = self.store.get(n['raw_event_ref'])
            obs.validate_observations(n['proposal'], raw, profile, n['glossary_candidates'])
            result.append(n)
        acc.observation_rows(result)
        return result

    def save_accumulation(self, *, bundle_id, expected_revision, profile_id, profile_work_hash,
                          observation_ids, originals, proposal, model_receipt=None, matching_receipt=None):
        if bundle_id.startswith('cb-kb-ws-') and not getattr(self, 'workspace_projection_binding', None):
            raise ContractError('workspace bundles require selected-statement projection')
        if not re.fullmatch(r'cb-kb-[A-Za-z0-9_-]{1,77}', bundle_id):
            raise ContractError('knowledge bundle ID required (cb-kb-...)')
        profile = self.selected_profile(profile_id, profile_work_hash); self._originals(originals)
        observations = self._observations(observation_ids, profile)
        base = self.load(bundle_id) if expected_revision else None
        if base and base['revision'] != expected_revision:
            raise ContractError('stale accumulation base revision')
        if base and base['profile_hash'] != profile['profile_hash']:
            raise ContractError('profile migration requires an explicit new bundle')
        checks = acc.validate_proposal(proposal, profile, originals, observations, base)
        candidates = {c['concept_id']: c for n in observations for c in n['glossary_candidates']['candidates']}
        if base:
            candidates.update({c['concept_id']: c for c in base['glossary_refs']})
        selected = {cid for n in proposal['graph']['nodes'] for cid in n['glossary_refs']}
        if not selected <= candidates.keys():
            raise ContractError('knowledge glossary ID was not offered')
        refs = [candidates[k] for k in sorted(selected)]
        compiler.compile_package(proposal['graph'], profile, originals, bundle_id=bundle_id,
                                 revision=expected_revision + 1, glossary_refs=refs)
        document = {'kind': 'KNOWLEDGE', 'scope': self.scope([s['anchor']['document_id'] for s in originals]),
            'profile_id': profile_id, 'profile_work_hash': profile_work_hash, 'profile_hash': profile['profile_hash'],
            'originals': deepcopy(originals), 'proposal': deepcopy(proposal), 'glossary_refs': deepcopy(refs),
            'base_work_hash': base['work_hash'] if base else None, 'model_receipt': model_receipt,
            'matching_receipt': deepcopy(matching_receipt or {'status':'OPERATOR_SELECTED_BASE','exhaustive':False}),
            'observation_ids': sorted(set((base or {}).get('observation_ids', []) + observation_ids)), **checks}
        return self._save(bundle_id, document, expected_revision)

    def accumulate(self, **kwargs):
        profile = self.selected_profile(kwargs['profile_id'], kwargs['profile_work_hash'])
        self._originals(kwargs['originals'])
        observations = self._observations(kwargs['observation_ids'], profile)
        base = self.load(kwargs['bundle_id']) if kwargs['expected_revision'] else None
        if base and base['revision'] != kwargs['expected_revision']:
            raise ContractError('stale accumulation reservation')
        source_schema = semantics.source_schema(profile, kwargs['originals'])
        # This independent call deliberately cannot see observations or the base.
        source_context = {'operation': 'SOURCE_ANALYSIS', 'originals': kwargs['originals'],
                          'profile_hash': profile['profile_hash']}
        analysis, source_receipt = self._job('SOURCE_ANALYSIS', source_context,
            semantics.SOURCE_PROMPT, source_schema,
            lambda p: semantics.validate_source(p, source_schema, kwargs['originals']),
            lambda: self._originals(kwargs['originals']))
        matching = self.match(observations, kwargs['originals'])
        context = {'source_analysis': analysis,
                   'profile': profile['effective'], 'profile_hash': profile['profile_hash'],
                   'originals': kwargs['originals'], 'observations': acc.observation_rows(observations),
                   'base': base, 'candidate_matching': matching,
                   'expected_revision': kwargs['expected_revision'],
                   'reference_contract': acc.reference_contract(observations, base)}
        output_schema = semantics.request_schema(
            acc.accumulation_schema(profile, observations, base, kwargs['originals']), analysis)
        def validate(proposal):
            canonical, _ = semantics.restore(proposal, output_schema, analysis, kwargs['originals'])
            acc.validate_proposal(canonical, profile, kwargs['originals'], observations, base)
        proposal, receipt = self._job('ACCUMULATE', context, acc.PROMPT + semantics.ACCUMULATION_PROMPT,
            output_schema, validate,
            lambda:(self._originals(kwargs['originals']),self._observations(kwargs['observation_ids'],profile)))
        canonical, assembly = semantics.restore(proposal, output_schema, analysis, kwargs['originals'])
        receipt = {**receipt, 'semantic_assembly': assembly,
                   'source_analysis': deepcopy(analysis), 'source_analysis_receipt': source_receipt}
        return self.save_accumulation(**kwargs, proposal=canonical, model_receipt=receipt, matching_receipt=matching)

    def match(self, observations, originals):
        concepts = {l['concept_id'] for n in observations for o in n['proposal']['observations'] for l in o['glossary_refs']}
        anchors = {digest(s['anchor']) for s in originals}; candidates = []
        for row in self.repo.list(prefix='cb-kb-'):
            try:
                d = self.load(row['bundle_id'])
            except ContractError:
                continue
            routes = []
            if concepts & {r['concept_id'] for r in d['glossary_refs']}:
                routes.append('GLOSSARY')
            if anchors & {digest(s['anchor']) for s in d['originals']}:
                routes.append('SOURCE_ANCHOR')
            if routes:
                candidates.append({'bundle_id': row['bundle_id'], 'revision': d['revision'], 'work_hash': d['work_hash'],
                                   'routes': routes, 'graph': d['proposal']['graph']})
        return {'candidates': candidates, 'unsearched': ['UNREGISTERED_BUNDLES', 'EXPLICIT_SOURCE_REFERENCES'],
                'same_glossary_id_implies_same_rule': False}

    def preview(self, bid):
        d = self.load(bid)
        if bid.startswith('cb-kb-ws-'):
            from .wiki_projection import check_selection, workspace_for
            if 'workspace_projection' not in d:
                raise ContractError('workspace projection lineage missing')
            check_selection(workspace_for(self), d['workspace_projection'])
        profile = self.selected_profile(d['profile_id'], d['profile_work_hash'])
        self._originals(d['originals'])
        for ref in d['glossary_refs']:
            if ref != self.glossary.restore(ref['source'], ref['node_id']):
                raise ContractError('knowledge glossary drift')
        return compiler.compile_package(d['proposal']['graph'], profile, d['originals'], bundle_id=bid,
            revision=d['revision'], approval_ref=d['approval'] if d['status'] == 'APPROVED' else None,
            glossary_refs=d['glossary_refs'], evaluation_spec=d.get('evaluation_spec'))

    def save_evaluation_spec(self, bid, revision, work_hash, spec):
        """Create a new draft; requires ordinary review and publication again."""
        d = self.load(bid)
        if (d['revision'], d['work_hash']) != (revision, work_hash) or d['kind'] == 'PROFILE':
            raise ContractError('exact knowledge revision required')
        from .evaluation_plan import compile_plan
        compile_plan(spec, self.preview(bid))
        document = self.store.get(work_hash)
        document['evaluation_spec'] = deepcopy(spec)
        return self._save(bid, document, revision)

    def review(self, bid, revision, work_hash, approve, reason):
        d = self.load(bid)
        if d['kind'] == 'PROFILE':
            return self.review_profile(bid, revision, work_hash, approve, reason)
        if (d['revision'], d['work_hash']) != (revision, work_hash) or not reason.strip():
            raise ContractError('exact reviewed revision and reason required')
        if approve:
            self.preview(bid)
        return self.repo.review(bid, revision, work_hash, self.actor, approve, reason)

    def stage_publication(self, bid, revision, work_hash, expected_sequence):
        from .publication import publication_context
        d = self.load(bid)
        if (d['revision'], d['work_hash'], d['status']) != (revision, work_hash, 'APPROVED'):
            raise ContractError('exact approved knowledge required')
        context = publication_context(self.preview(bid), approved_at=self.repo.event_record(d['approval'])['at'])
        return self.repo.stage(bid, revision, work_hash, d['approval'], context, expected_sequence, self.actor)

    def verify_publication(self, pid):
        from .publication import verify_consumer
        row = self.repo.publication(pid, self.document_ids)
        if row['bundle_id'].startswith('cb-kb-ws-'):
            self.load(row['bundle_id'], row['revision'])
        package = row['context']['assembly_package']
        self._originals(package['originals'])
        for ref in package['glossary_refs']:
            if ref != self.glossary.restore(ref['source'], ref['node_id']):
                raise ContractError('staged glossary drift')
        binding = verify_consumer(row['context'])
        receipt = self.repo.consumer_receipt(pid, row['package_sha256'], binding, self.actor)
        return {'publication_id': pid, 'receipt_id': receipt, 'binding': binding, 'status': 'CONSUMER_VERIFIED'}

    def activate_publication(self, pid, expected_sequence, receipt, *, rollback=False):
        from .publication import verify_consumer
        row = self.repo.publication(pid, self.document_ids); package = row['context']['assembly_package']
        if row['bundle_id'].startswith('cb-kb-ws-'):
            self.load(row['bundle_id'], row['revision'])
        self._originals(package['originals'])
        for ref in package['glossary_refs']:
            if ref != self.glossary.restore(ref['source'], ref['node_id']):
                raise ContractError('activation glossary drift')
        binding = verify_consumer(row['context'])
        if receipt['publication_id'] != pid or receipt['binding'] != binding:
            raise ContractError('activation receipt changed')
        if row['bundle_id'].startswith('cb-kb-ws-'):
            from .wiki_projection import activate
            return activate(self, row, expected_sequence, receipt, binding, rollback=rollback)
        return self.repo.activate_staged(row['bundle_id'], pid, expected_sequence, receipt['receipt_id'], binding,
                                        self.actor, rollback=rollback)
