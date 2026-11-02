"""Pin free statements, then use the existing observation/IR/compiler contracts."""
from copy import deepcopy

from ..contracts import digest
from ..legal_agent.errors import ContractError
from .domain_workflow import DomainWorkflow
from .wiki_workspace import Workspace
from . import wiki_contracts as wc, accumulation as acc, authoring_semantics as semantics
from .schema import obj, arr, text


def workspace_for(domain):
    return Workspace(domain.repo, domain.store, actor=domain.actor, source_reader=domain.source_reader,
        generate=domain.generate, namespace=domain.namespace, source_snapshot=domain.source_snapshot,
        acl_ref=domain.acl_ref, document_ids=domain.document_ids, glossary=domain.glossary,
        producer_binding=domain.producer_binding, clock=domain.clock,
        can_publish=getattr(domain, 'can_publish_workspace', False))


def select(workspace, statement_ids):
    wc.strings(statement_ids, maximum=32)
    if not statement_ids:
        raise ContractError('select workspace statements to compile')
    rows = []
    for bid in statement_ids:
        d = workspace.item(bid)
        if d['kind'] != 'STATEMENT' or d['state'] in ('DISPUTED', 'RETRACTED'):
            raise ContractError('workspace statement is not available for compilation')
        rows.append({'bundle_id': bid, 'revision': d['revision'], 'work_hash': d['work_hash'],
                     'semantic_hash': d['semantic_hash'], 'content': deepcopy(d['content'])})
    return sorted(rows, key=lambda x: x['bundle_id'])


def check_selection(workspace, lineage):
    if lineage.get('version') != 'workspace-projection-v1' or lineage['scope'] != workspace.scope(lineage['scope']['document_ids']):
        raise ContractError('workspace projection scope changed')
    current = select(workspace, [r['bundle_id'] for r in lineage['statements']])
    if current != lineage['statements']:
        raise ContractError('workspace projection statements changed; compile a new projection')
    return current


def verify_mapping(value, statements, originals, observations):
    wc.exact(value, ('accumulation', 'coverage'))
    selected = {s['bundle_id']: s for s in statements}
    coverage_schema = arr(obj({'statement_id': {'enum': list(selected)}, 'decision': {'enum': wc.DECISIONS},
                               'node_ids': arr(text(160)), 'reason': text()}), len(selected), len(selected))
    wc.validate(value['coverage'], coverage_schema)
    rows = {r['statement_id']: r for r in value['coverage']}
    if len(rows) != len(selected):
        raise ContractError('every selected statement requires one coverage decision')
    proposal = deepcopy(value['accumulation'])
    if not isinstance(proposal, dict) or not isinstance(proposal.get('graph'), dict):
        raise ContractError('workspace typed graph required')
    nodes = {n['id']: n for n in proposal['graph']['nodes']}
    sources = {s['id']: s for s in originals}
    provenance = acc.observation_rows(observations)
    used = set()
    for bid, row in rows.items():
        statement = selected[bid]['content']
        if row['decision'] == 'INCLUDED':
            if not row['node_ids'] or not statement['source_basis']:
                raise ContractError('included workspace statement requires typed nodes and original basis')
        elif row['node_ids']:
            raise ContractError('nonincluded statement cannot inject graph nodes')
        for nid in row['node_ids']:
            if nid not in nodes or nid in used or nodes[nid]['text'] != statement['text']:
                raise ContractError('compiled node must preserve one selected statement exactly')
            used.add(nid)
            for basis in nodes[nid]['basis']:
                source = sources.get(basis['source'])
                if source is None or not any(source['anchor'] == b['anchor'] and basis['quote'] in b['quote']
                                             for b in statement['source_basis']):
                    raise ContractError('compiled node basis outside selected statement')
            allowed_raw_hashes = {n['raw_event_ref'] for n in observations
                                  if n['_workspace_raw_id'] in statement['origin_refs']}
            if any(ref not in provenance or provenance[ref]['raw_event_ref'] not in allowed_raw_hashes
                   for ref in nodes[nid]['observation_refs']):
                raise ContractError('compiled node observation lacks statement lineage')
        missing = list(statement['open_items'])
        if row['decision'] in ('UNRESOLVED', 'CONTRADICTED'):
            missing.append(row['decision'] + ': ' + row['reason'])
        for message in missing:
            reason = bid + ': ' + message
            if reason not in proposal['graph']['unresolved']:
                proposal['graph']['unresolved'].append(reason)
    if used != set(nodes):
        raise ContractError('all compiled nodes must map to selected statements')
    return proposal


class ProjectionWorkflow(DomainWorkflow):
    def __init__(self, domain, workspace, statements, purpose):
        super().__init__(domain.repo, domain.store, actor=domain.actor, source_reader=domain.source_reader,
            generate=domain.generate, namespace=domain.namespace, source_snapshot=domain.source_snapshot,
            acl_ref=domain.acl_ref, document_ids=domain.document_ids, glossary=domain.glossary,
            producer_binding=domain.producer_binding, clock=domain.clock)
        self.workspace = workspace
        self.generate = workspace.generate or domain.generate
        self.can_publish_workspace = workspace.can_publish
        self.workspace_projection_binding = {'version': 'workspace-projection-v1',
            'scope': workspace.scope(workspace.document_ids), 'statements': statements, 'purpose': purpose}

    def _save(self, bid, document, expected, *, state='DRAFT'):
        if document.get('kind') == 'KNOWLEDGE':
            check_selection(self.workspace, self.workspace_projection_binding)
            document = {**document, 'workspace_projection': deepcopy(self.workspace_projection_binding)}
        return super()._save(bid, document, expected, state=state)


def compile_selection(domain, workspace, *, statement_ids, purpose, profile_id, profile_work_hash,
                      originals=None, observation_ids=None, proposal=None):
    wc.meaningful(purpose, 2000)
    if workspace.scope() != domain.scope() or workspace.actor != domain.actor:
        raise ContractError('workspace/compiler operator binding differs')
    statements = select(workspace, statement_ids)
    p = ProjectionWorkflow(domain, workspace, statements, purpose)
    profile = p.selected_profile(profile_id, profile_work_hash)
    if originals is None:
        anchors = {digest(b['anchor']): b['anchor'] for s in statements for b in s['content']['source_basis']}
        originals = [{'id': 'S' + key[:24], 'anchor': a, 'text': p.source_reader(a)} for key, a in sorted(anchors.items())]
    p._originals(originals)
    raw_ids = sorted({r for s in statements for r in s['content']['origin_refs']})
    if not raw_ids or len(raw_ids) > 16:
        raise ContractError('projection requires one to sixteen actual raw origins')
    raw_by_hash = {digest(p.load(bid)['raw']): bid for bid in raw_ids}
    # Durable overall deadline bounds new physical calls across normalization and projection.
    identity = digest([p.workspace_projection_binding, profile['profile_hash'], originals, p.producer_binding])
    bid = 'cb-kb-ws-' + wc.scope_key(workspace.scope()) + '-' + identity[:32]
    prior = p.repo.latest(bid)
    if prior:
        d = p.load(bid)
        if proposal is not None and d['workspace_projection'].get('input_proposal_hash') != digest(proposal):
            raise ContractError('projection input differs from stored result')
        p.preview(bid)
        return {'bundle_id': bid, **prior, 'reused': True}
    job_id = 'proj-' + identity
    prior_job = p.repo.latest(job_id)
    if prior_job:
        deadline = p.load(job_id)['deadline']
    else:
        deadline = p.clock() + 600
        p._save(job_id, {'kind': 'PROJECTION_RESERVATION', 'scope': p.scope(p.document_ids),
                        'deadline': deadline, 'statement_hash': digest(statements)}, 0, state='INPUT')
    original_generate = p.generate
    if original_generate:
        def bounded(prompt, context, schema):
            if p.clock() >= deadline:
                from .authoring_model import AuthoringFailure
                raise AuthoringFailure('BUDGET_EXHAUSTED', {'physical_calls': 0})
            context = deepcopy(context)
            context['call_budget']['absolute_deadline'] = min(deadline, context['call_budget']['absolute_deadline'])
            return original_generate(prompt, context, schema)
        p.generate = bounded
    if observation_ids is None:
        observation_ids = [p.normalize(raw, profile_id=profile_id, profile_work_hash=profile_work_hash)['bundle_id'] for raw in raw_ids]
    observations = p._observations(observation_ids, profile)
    if {n['raw_event_ref'] for n in observations} != set(raw_by_hash):
        raise ContractError('projection observations must cover exactly the selected raw origins')
    annotated = [{**n, '_workspace_raw_id': raw_by_hash[n['raw_event_ref']]} for n in observations]
    receipt = None
    if proposal is None:
        source_schema = semantics.source_schema(profile, originals)
        analysis, source_receipt = p._job('SOURCE_ANALYSIS', {'operation': 'SOURCE_ANALYSIS',
            'originals': originals, 'profile_hash': profile['profile_hash']}, semantics.SOURCE_PROMPT,
            source_schema, lambda value: semantics.validate_source(value, source_schema, originals),
            lambda: p._originals(originals))
        typed_schema = semantics.request_schema(acc.accumulation_schema(profile, observations, None, originals), analysis)
        schema = obj({'accumulation': typed_schema, 'coverage': arr(obj({
            'statement_id': {'enum': [s['bundle_id'] for s in statements]}, 'decision': {'enum': wc.DECISIONS},
            'node_ids': arr(text(160)), 'reason': text()}), len(statements), len(statements))})
        context = {'statements': statements, 'purpose': purpose, 'source_analysis': analysis,
                   'originals': originals, 'observations': acc.observation_rows(observations),
                   'profile': profile['effective'], 'profile_hash': profile['profile_hash'],
                   'reference_contract': acc.reference_contract(observations)}
        def restore(value):
            wc.validate(value, schema)
            canonical, assembly = semantics.restore(value['accumulation'], typed_schema, analysis, originals)
            return {**value, 'accumulation': canonical}, assembly
        def verify(value):
            value, _ = restore(value)
            canonical = verify_mapping(value, statements, originals, annotated)
            acc.validate_proposal(canonical, profile, originals, observations)
        value, receipt = p._job('WIKI_PROJECT', context,
            acc.PROMPT + semantics.ACCUMULATION_PROMPT + '\n선택 statement의 정확 text만 노드로 쓴다. 다르게 해석해야 하면 UNRESOLVED로 남기고 새 문장 검토를 요청한다. 모든 statement의 포함/제외/미확인 이유를 coverage에 기록한다. 자유 링크를 실행 간선으로 승격하지 않는다.',
            schema, verify, lambda: (check_selection(workspace, p.workspace_projection_binding), p._originals(originals)))
        proposal, assembly = restore(value)
        receipt = {**receipt, 'source_analysis_receipt': source_receipt, 'semantic_assembly': assembly}
    wc.exact(proposal, ('accumulation', 'coverage'))
    wc.validate(proposal['accumulation'], profile['accumulation_schema'])
    canonical = verify_mapping(proposal, statements, originals, annotated)
    p.workspace_projection_binding.update(coverage=deepcopy(proposal['coverage']), input_proposal_hash=digest(proposal))
    return p.save_accumulation(bundle_id=bid, expected_revision=0, profile_id=profile_id,
        profile_work_hash=profile_work_hash, observation_ids=observation_ids, originals=originals,
        proposal=canonical, model_receipt=receipt,
        matching_receipt={'status': 'WORKSPACE_SELECTED_REVISIONS', 'statement_ids': statement_ids, 'exhaustive': False})


def activate(domain, row, expected_sequence, receipt, binding, *, rollback=False):
    workspace = workspace_for(domain)
    if not workspace.can_publish:
        raise ContractError('workspace publication management permission required')
    d = domain.load(row['bundle_id'], row['revision'])
    lineage = d['workspace_projection']; statements = check_selection(workspace, lineage)
    catalog, pin = workspace.catalog()
    pid = receipt['publication_id']
    catalog['publications'][pid] = {'bundle_id': row['bundle_id'], 'statement_ids': [s['bundle_id'] for s in statements],
                                  'statement_revisions': {s['bundle_id']: s['revision'] for s in statements},
                                  'package_sha256': row['package_sha256'], 'state': 'ACTIVE'}
    key = workspace.store.put(workspace._object(workspace.catalog_id, catalog))
    expected = {workspace.catalog_id: pin, row['bundle_id']: {'revision': d['revision'], 'work_hash': d['work_hash']},
                **{s['bundle_id']: {k: s[k] for k in ('revision', 'work_hash')} for s in statements}}
    return domain.repo.activate_workspace(catalog_id=workspace.catalog_id, expected=expected,
        writes={workspace.catalog_id: key}, bid=row['bundle_id'], pid=pid, expected_sequence=expected_sequence,
        receipt_id=receipt['receipt_id'], binding=binding, actor=domain.actor, rollback=rollback)
