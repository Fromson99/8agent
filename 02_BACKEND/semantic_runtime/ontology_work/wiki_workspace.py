"""Profile-free authoring with immutable objects and one SQL commit per change."""
from copy import deepcopy

from ..contracts import digest
from ..legal_agent.errors import ContractError
from .domain_workflow import DomainWorkflow, SaveUnconfirmed
from . import wiki_contracts as wc, wiki_index as wi


class Workspace(DomainWorkflow):
    job_attempt_limit = 5

    def __init__(self, *args, can_publish=False, **kwargs):
        kwargs.setdefault('glossary', None)
        super().__init__(*args, **kwargs)
        self.can_publish = can_publish
        self.catalog_id = wi.catalog_id(self.scope())

    def catalog(self):
        row = self.repo.latest(self.catalog_id)
        if not row:
            return wi.empty(self.scope()), {'revision': 0, 'work_hash': None}
        doc = self.load(self.catalog_id)
        if doc['kind'] != 'WIKI_CATALOG' or len(doc['shards']) > wi.SHARDS:
            raise ContractError('workspace catalog contract')
        return self._document(doc), {k: row[k] for k in ('revision', 'work_hash')}

    def item(self, bid, revision=None):
        doc = self.load(bid, revision)
        if doc.get('workspace_version') != wc.VERSION or doc['kind'] not in wc.KINDS:
            raise ContractError('workspace item required')
        wc.validate_content(doc['kind'], doc['content'])
        if doc['kind'] == 'STATEMENT' and wc.semantic_hash(doc) != doc['semantic_hash']:
            raise ContractError('workspace semantic fingerprint changed')
        return doc

    def list_items(self, **kwargs):
        return wi.page(self, **kwargs)

    def _object(self, bid, document):
        return {'version': 'ontology-domain-work-v1', 'bundle_id': bid, **deepcopy(document)}

    def _origins(self, ids):
        wc.strings(ids, maximum=32)
        result = {}
        for bid in ids:
            raw = self.load(bid)
            if raw['kind'] != 'RAW':
                raise ContractError('workspace origin must be immutable raw record')
            result[bid] = raw
        return result

    def apply(self, *, change_id, operations, expected=None, raw_ids=(), proposal_receipt=None, _validate_only=False):
        wc.meaningful(change_id, 160)
        wc.validate({'operations': operations}, wc.CHANGE_SCHEMA)
        request = {'change_id': change_id, 'operations': deepcopy(operations),
                   'expected': deepcopy(expected or {}), 'raw_ids': list(raw_ids),
                   'actor': self.actor, 'scope': self.scope(self.document_ids),
                   'proposal_receipt': deepcopy(proposal_receipt)}
        request_hash = digest(request)
        operation_id = 'ws-op-' + digest([wc.scope_key(self.scope()), change_id])
        existing = self.repo.latest(operation_id)
        if existing:
            operation = self.load(operation_id)
            if operation['request_hash'] != request_hash:
                raise ContractError('workspace operation ID reused with different input')
            if _validate_only: return {'status': 'ALREADY_COMMITTED'}
            return self.reconcile_change(existing['work_hash'])
        raws = self._origins(list(raw_ids))
        catalog, catalog_pin = self.catalog()
        pins = {self.catalog_id: catalog_pin, operation_id: {'revision': 0, 'work_hash': None}}
        documents, handles = {}, {}
        creates = {'CREATE_ENTRY': 'ENTRY', 'ADD_STATEMENT': 'STATEMENT', 'CREATE_VIEW': 'VIEW'}
        for op in operations:
            if op['op'] in creates:
                if op['target'] in handles:
                    raise ContractError('workspace handle repeated')
                handles[op['target']] = wc.identifier(creates[op['op']], self.scope(), change_id, op['target'])
        def resolve(value):
            if not isinstance(value, str):
                raise ContractError('workspace target reference')
            if value.startswith('@'):
                if value not in handles:
                    raise ContractError('workspace handle not reserved')
                return handles[value]
            return value
        def get(bid):
            if bid in documents:
                return documents[bid]
            doc = self.item(bid)
            actual = {k: doc[k] for k in ('revision', 'work_hash')}
            if (expected or {}).get(bid) != actual:
                raise ContractError('workspace exact expected revision required: ' + bid)
            pins[bid] = actual
            return self._document(doc)
        # Pre-create empty objects so references can point forward in this change.
        for op in operations:
            if op['op'] in creates:
                bid = resolve(op['target']); kind = creates[op['op']]
                documents[bid] = {'kind': kind, 'workspace_version': wc.VERSION,
                                  'scope': self.scope(self.document_ids), 'state': 'DRAFT_UNVERIFIED',
                                  'content': wc.default_content(kind)}
                pins[bid] = {'revision': 0, 'work_hash': None}
        withdrawn = set()
        for op in operations:
            action, value = op['op'], deepcopy(op['value']); bid = resolve(op['target'])
            doc = documents[bid] if action in creates else get(bid)
            if action in creates or action.startswith('REVISE_'):
                kind = creates.get(action, action.removeprefix('REVISE_'))
                if doc['kind'] != kind or set(value) - set(wc.default_content(kind)):
                    raise ContractError('workspace edit fields or kind')
                if doc['state'] in ('DISPUTED', 'RETRACTED'):
                    raise ContractError('withdrawn meaning requires a new statement')
                doc['content'].update(value)
            elif action in ('LINK', 'UNLINK'):
                if doc['kind'] != 'ENTRY':
                    raise ContractError('navigation requires entry')
                wc.exact(value, ('label', 'target'))
                link = {**value, 'target': resolve(value['target']), 'navigation_only': True}
                links = doc['content']['navigation_links']
                if action == 'LINK':
                    if link not in links: links.append(link)
                elif link not in links:
                    raise ContractError('workspace link no longer present')
                else: links.remove(link)
            elif action == 'MOVE_MEMBERSHIP':
                wc.exact(value, ('member', 'target'))
                if doc['kind'] != 'VIEW':
                    raise ContractError('membership move requires view')
                member, target = resolve(value['member']), resolve(value['target'])
                destination = get(target)
                if destination['kind'] != 'VIEW' or member not in doc['content']['member_refs']:
                    raise ContractError('workspace membership changed')
                doc['content']['member_refs'].remove(member)
                if member not in destination['content']['member_refs']: destination['content']['member_refs'].append(member)
                documents[target] = destination
            elif action in ('MARK_DISPUTED', 'RETRACT'):
                if not self.can_publish:
                    raise ContractError('workspace publication management permission required')
                wc.exact(value, ('reason',)); wc.meaningful(value['reason'])
                doc.update(state='DISPUTED' if action == 'MARK_DISPUTED' else 'RETRACTED', withdrawal_reason=value['reason'])
                if doc['kind'] == 'STATEMENT': withdrawn.add(bid)
            documents[bid] = doc
        for bid, doc in documents.items():
            content = doc['content']; kind = doc['kind']
            for key in ('statement_refs', 'member_refs'):
                if key in content: content[key] = [resolve(x) for x in content[key]]
            for link in content.get('navigation_links', []):
                link['target'] = resolve(link['target'])
            wc.validate_content(kind, content)
            if kind == 'STATEMENT':
                origins = self._origins(content['origin_refs'])
                if not set(origins) <= set(raws) and pins[bid]['revision'] == 0:
                    raise ContractError('new statement origins were not supplied')
                for raw in origins.values():
                    if not set(raw['scope']['document_ids']) <= set(doc['scope']['document_ids']):
                        raise ContractError('workspace origin scope cannot be widened')
                for basis in content['source_basis']:
                    wc.validate_basis(basis, self.source_reader, doc['scope']['document_ids'])
            for target in content.get('statement_refs', []) + content.get('member_refs', []) + [r['target'] for r in content.get('navigation_links', [])]:
                other = get(target)
                if kind == 'ENTRY' and target in content['statement_refs'] and other['kind'] != 'STATEMENT':
                    raise ContractError('entry references must identify statements')
                # Mixed-scope views stay restricted to every contributing document.
                if not set(other['scope']['document_ids']) <= set(doc['scope']['document_ids']):
                    raise ContractError('workspace reference scope cannot be widened')
        withdraw = [(p['bundle_id'], pid) for pid, p in catalog['publications'].items()
                    if withdrawn & set(p['statement_ids'])]
        if _validate_only:
            return {'status': 'VALIDATED_NOT_COMMITTED', 'handles': handles}
        for _, pid in withdraw: catalog['publications'][pid]['state'] = 'WITHDRAWN'
        writes, shards = {}, {}
        for bid, doc in documents.items():
            if doc['kind'] == 'STATEMENT': doc['semantic_hash'] = wc.semantic_hash(doc)
            value = self._object(bid, doc); key = self.store.put(value); writes[bid] = key
            shard = wi.shard_for(bid)
            if shard not in shards:
                shards[shard] = deepcopy(self.store.get(catalog['shards'][shard])) if shard in catalog['shards'] else {'items': {}}
            shards[shard]['items'][bid] = wi.row(value, pins[bid]['revision'] + 1, key)
            if len(shards[shard]['items']) > wi.SHARD_LIMIT:
                raise ContractError('workspace index partition limit; explicit migration required')
        for shard, value in shards.items(): catalog['shards'][shard] = self.store.put(value)
        writes[self.catalog_id] = self.store.put(self._object(self.catalog_id, catalog))
        transaction = {'catalog_id': self.catalog_id, 'operation_id': operation_id,
                       'request_hash': request_hash, 'expected': pins, 'writes': writes,
                       'withdraw': withdraw, 'actor': self.actor}
        operation = self._object(operation_id, {'kind': 'WIKI_OPERATION', 'scope': self.scope(self.document_ids),
            'request_hash': request_hash, 'request': request, 'handles': handles, 'transaction': transaction})
        operation_hash = self.store.put(operation)
        transaction = {**transaction, 'writes': {**writes, operation_id: operation_hash}}
        try:
            result = self.repo.commit_workspace_change(**transaction)
        except ContractError:
            raise
        except Exception as exc:
            raise SaveUnconfirmed(operation_hash) from exc
        return {**result, 'handles': handles, 'operation_hash': operation_hash}

    def reconcile_change(self, key):
        doc = self.store.get(key); self.check_scope(doc)
        if doc.get('kind') != 'WIKI_OPERATION' or doc['request']['actor'] != self.actor or digest(doc['request']) != doc['request_hash']:
            raise ContractError('workspace reconciliation requires exact authorized operation')
        tx = deepcopy(doc['transaction'])
        if tx['catalog_id'] != self.catalog_id or tx['operation_id'] != doc['bundle_id']:
            raise ContractError('workspace reconciliation binding')
        if tx['request_hash'] != doc['request_hash'] or tx['actor'] != self.actor:
            raise ContractError('workspace reconciliation request identity')
        for bid, object_hash in tx['writes'].items():
            item = self.store.get(object_hash); self.check_scope(item)
            if item.get('kind') == 'STATEMENT' and not self.repo.latest(doc['bundle_id']):
                for basis in item['content']['source_basis']:
                    wc.validate_basis(basis, self.source_reader, self.document_ids)
            if item.get('state') in ('DISPUTED', 'RETRACTED') and not self.can_publish:
                raise ContractError('workspace withdrawal permission changed')
        tx['writes'][doc['bundle_id']] = key
        result = self.repo.commit_workspace_change(**tx)
        return {**result, 'handles': doc['handles'], 'operation_hash': key}

    def propose(self, *, change_id, raw_ids, item_ids=(), query='', originals=()):
        raws = self._origins(list(raw_ids))
        if originals: self._originals(list(originals))
        search = self.list_items(query=query)
        ids = list(dict.fromkeys([*item_ids, *(r['bundle_id'] for r in search['items'])]))
        if len(ids) > 64: raise ContractError('workspace proposal item limit')
        items = [self.item(bid) for bid in ids]
        # Referenced statements are offered with their real current revisions.
        for item in list(items):
            for bid in item['content'].get('statement_refs', []):
                if bid not in ids:
                    ids.append(bid); items.append(self.item(bid))
                    if len(ids) > 128: raise ContractError('workspace proposal reference limit')
        expected = {d['bundle_id']: {k: d[k] for k in ('revision', 'work_hash')} for d in items}
        # Offer original business content once. Stored envelopes/indexes are
        # provenance, not additional observations for the model to turn into facts.
        raw_pins = {bid: {k: row[k] for k in ('revision', 'work_hash')} for bid, row in raws.items()}
        record_view = {bid: {k: deepcopy(row['raw'][k]) for k in ('payload', 'format_description', 'origin')}
                       for bid, row in raws.items()}
        context = {'raw_records': record_view, 'raw_record_bindings': raw_pins,
                   'items': items, 'candidate_search': search,
                   'originals': list(originals), 'change_id': change_id}
        schema, expand = wc.proposal_contract(raws, items, originals)
        contract = wc.PROPOSAL_VERSION
        prompt = wc.PROMPT
        if raws and not items:
            schema, expand, materials = wc.content_selection_contract(raws, originals)
            context.pop('raw_records')
            context['material_options'] = materials
            contract = wc.CONTENT_VERSION
            prompt = wc.CONTENT_PROMPT
        context['proposal_contract'] = contract
        def unchanged():
            for bid, pin in raw_pins.items():
                current = self.load(bid)
                if any(current[k] != value for k, value in pin.items()):
                    raise ContractError('workspace proposal raw record changed')
            for bid, pin in expected.items():
                current = self.item(bid)
                if any(current[k] != v for k, v in pin.items()):
                    raise ContractError('workspace proposal input changed')
            if originals: self._originals(list(originals))
        def verify(raw):
            value = expand(raw)
            wc.validate(value, wc.CHANGE_SCHEMA)
            if any(o['op'] in ('MARK_DISPUTED', 'RETRACT') for o in value['operations']):
                raise ContractError('model cannot withdraw active knowledge')
            # No state mutation while a model response is being validated.
            for op in value['operations']:
                if not op['target'].startswith('@') and op['target'] not in expected:
                    raise ContractError('model workspace target was not offered')
                offered_origins=set(raws) | {ref for item in items for ref in item['content'].get('origin_refs',[])}
                if not set(op['value'].get('origin_refs',[])) <= offered_origins:
                    raise ContractError('model workspace origin was not offered')
                offered_anchors={digest(s['anchor']) for s in originals} | {digest(b['anchor']) for item in items for b in item['content'].get('source_basis',[])}
                for basis in op['value'].get('source_basis',[]):
                    if not isinstance(basis,dict) or digest(basis.get('anchor')) not in offered_anchors:
                        raise ContractError('model workspace source was not offered')
            self.apply(change_id=change_id, operations=value['operations'], expected=expected,
                       raw_ids=list(raw_ids), _validate_only=True)
        raw, receipt = self._job('WIKI_PROPOSE', context, prompt, schema, verify, unchanged)
        value = expand(raw)
        return {'change_id': change_id, 'operations': value['operations'], 'expected': expected,
                'raw_ids': list(raw_ids), 'proposal_receipt': {'model': receipt, 'candidate_search': search,
                    'contract': contract, 'original_proposal_hash': digest(raw),
                    'canonical_proposal_hash': digest(value)}}

    def lint(self, bid):
        doc = self.item(bid); missing = []
        for basis in doc['content'].get('source_basis', []):
            try: wc.validate_basis(basis, self.source_reader, self.document_ids)
            except ContractError as exc: missing.append(str(exc))
        for target in doc['content'].get('statement_refs', []) + doc['content'].get('member_refs', []) + [x['target'] for x in doc['content'].get('navigation_links', [])]:
            try: self.item(target)
            except ContractError: missing.append('REFERENCE_UNAVAILABLE')
        return {'bundle_id': bid, 'revision': doc['revision'], 'issues': missing,
                'open_items': doc['content'].get('open_items', []), 'legal_truth_verified': False}
