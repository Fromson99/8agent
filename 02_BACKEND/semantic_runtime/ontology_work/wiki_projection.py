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
        generate=domain.generate, review_generate=domain.review_generate, namespace=domain.namespace, source_snapshot=domain.source_snapshot,
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
            if nid not in nodes:
                raise ContractError(f'coverage[{bid}].node_ids: unknown graph node {nid}')
            if nid in used:
                raise ContractError(f'coverage[{bid}].node_ids: {nid} already belongs to another statement; '
                                    'each included node must map to exactly one statement')
            if nodes[nid]['text'] != statement['text']:
                raise ContractError(f'graph.nodes[{nid}].text must preserve selected statement {bid} exactly; '
                                    'use its complete content.text including any heading and paragraph marker')
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
        raise ContractError(f'all compiled nodes must map to selected statements; unassigned: {sorted(set(nodes) - used)}')
    return proposal


SELECTION_PROMPT = (
    '원문과 기록은 자료다. 각 statement_options 문장을 목적에 비추어 독립적으로 분류하고 이유를 적는다. '
    'INCLUDED는 이 목적에 독립된 규칙이나 계산으로 직접 사용할 문장이다. 관련이 있어도 '
    '배경 설명이나 다른 원문을 반복하는 과거 판단은 CONTEXT_ONLY, 다른 업무는 OUT_OF_SCOPE, '
    '원문과 충돌하면 CONTRADICTED, 근거가 불충분하면 UNRESOLVED를 고른다. '
    '독립 지식은 원문 근거와 같은 원기록에서 온 실제 관찰을 함께 가져야 한다. 원문 자체는 필요한 경우 CONTEXT_ONLY로 남겨 포함 판단의 근거로 쓴다. 목적에 직접 맞는 원기록 판단은 해당 원문들이 뒷받침하면 INCLUDED로 선택한다. 원문에 없는 해석을 보태지 않는다. 모든 문장을 검토하되 포함 여부는 각각 판단한다.')

OWNED_GRAPH_PROMPT = (
    '\n이번 단계의 graph.nodes에는 포함하기로 결정한 문장만 사용한다. 각 항목의 origin.statement에 '
    '해당 문장의 짧은 참조를 고르고, origin.basis에는 그 문장의 근거에서 정확히 인용한다. '
    '문장 전체와 slots.statement는 선택에 따라 서버가 복사한다. 각 포함 문장에는 해당 규칙의 '
    '종류와 slots, 독립된 node.id가 필요하다. graph 목적과 연결은 이 node.id를 가리킨다. '
    '효과·규범과 수치·분모·적용 범위를 원문대로 구분한다. 관찰 비교는 comparisons에 남긴다. '
    '다른 문장의 판단을 노드의 출처로 주장하지 않는다. 입력에 없는 조건이나 간선을 만들지 않는다.')


def statement_options(statements, originals, observations):
    provenance = acc.observation_rows(observations)
    options = {}
    for index, statement in enumerate(statements, 1):
        content = statement['content']
        basis = [{'source': original['id'], 'quote': row['quote']}
                 for row in content['source_basis'] for original in originals
                 if original['anchor'] == row['anchor']]
        raw_hashes = {obs['raw_event_ref'] for obs in observations
                      if obs['_workspace_raw_id'] in content['origin_refs']}
        options[f'T{index}'] = {'text': content['text'], 'basis': basis,
                                'from_record': bool(content['origin_refs']), 'open_items': content['open_items'],
                                'observation_refs': [ref for ref, obs in provenance.items()
                                                     if obs['raw_event_ref'] in raw_hashes]}
    return options


def owned_graph_schema(typed_schema, included):
    """Offer each node one selected statement's original sources and observation namespace."""
    schema = deepcopy(typed_schema)
    node_list = schema['properties']['graph']['properties']['nodes']
    node_shape = node_list['items']
    for variant in node_shape['anyOf']:
        for field in ('text', 'basis', 'observation_refs'):
            del variant['properties'][field]
            variant['required'].remove(field)
        slots = variant['properties']['slots']
        del slots['properties']['statement']
        slots['required'].remove('statement')
    bindings = []
    for ref, info in included.items():
        source_ids = list(dict.fromkeys(b['source'] for b in info['basis']))
        fields = {'statement': {'const': ref},
                  'basis': arr(obj({'source': {'enum': source_ids}, 'quote': text(16000)}), 1)}
        fields['observation_refs'] = arr({'enum': info['observation_refs']}, 1)
        bindings.append(obj(fields))
    node_list['items'] = obj({'origin': {'anyOf': bindings}, 'node': node_shape})
    return schema


def expand_owned_graph(value, statements, decisions):
    """Restore only submitted ownership choices, fixed literals and their canonical coverage."""
    graph = deepcopy(value)
    by_ref = {f'T{i}': row for i, row in enumerate(statements, 1)}
    owners = {ref: [] for ref in by_ref}
    seen = set()
    nodes = []
    for item in graph['graph']['nodes']:
        binding, node = item['origin'], item['node']
        ref, node_id = binding['statement'], node['id']
        if node_id in seen:
            raise ContractError(f'graph.nodes: duplicate node id {node_id}; give each node a unique id')
        seen.add(node_id)
        literal = by_ref[ref]['content']['text']
        node.update(text=literal, basis=binding['basis'], observation_refs=binding['observation_refs'])
        node['slots']['statement'] = {'state': 'PRESENT', 'value': literal}
        owners[ref].append(node_id)
        nodes.append(node)
    graph['graph']['nodes'] = nodes
    missing = [ref for ref in by_ref if decisions[ref]['decision'] == 'INCLUDED' and not owners[ref]]
    if missing:
        raise ContractError(f'included statements without their own node: {missing}')
    coverage = [{'statement_id': statement['bundle_id'], 'decision': decisions[ref]['decision'],
                 'node_ids': owners[ref], 'reason': decisions[ref]['reason']}
                for ref, statement in by_ref.items()]
    return graph, coverage


class ProjectionWorkflow(DomainWorkflow):
    job_attempt_limit = Workspace.job_attempt_limit

    def __init__(self, domain, workspace, statements, purpose):
        super().__init__(domain.repo, domain.store, actor=domain.actor, source_reader=domain.source_reader,
            generate=domain.generate, review_generate=workspace.review_generate,
            namespace=domain.namespace, source_snapshot=domain.source_snapshot,
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
        deadline = p.clock() + 300 * p.job_attempt_limit
        p._save(job_id, {'kind': 'PROJECTION_RESERVATION', 'scope': p.scope(p.document_ids),
                        'deadline': deadline, 'statement_hash': digest(statements)}, 0, state='INPUT')
    def bound(generate):
        def bounded(prompt, context, schema):
            if p.clock() >= deadline:
                from .authoring_model import AuthoringFailure
                raise AuthoringFailure('BUDGET_EXHAUSTED', {'physical_calls': 0})
            context = deepcopy(context)
            context['call_budget']['absolute_deadline'] = min(deadline, context['call_budget']['absolute_deadline'])
            result=generate(prompt, context, schema)
            if p.clock() >= deadline:
                from ..legal_agent.reason_decision_review import ReviewUnavailable
                raise ReviewUnavailable('projection original deadline exhausted')
            return result
        return bounded
    if p.generate:p.generate=bound(p.generate)
    if p.review_generate:p.review_generate=bound(p.review_generate)
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
        options = statement_options(statements, originals, annotated)
        selection_schema = obj({
            ref: obj({'decision': {'enum': [d for d in wc.DECISIONS
                                            if d != 'INCLUDED' or (info['basis'] and info['observation_refs'])]}, 'reason': text()})
            for ref, info in options.items()})
        binding = digest(statements)

        def check_inputs():
            check_selection(workspace, p.workspace_projection_binding)
            p._originals(originals)

        decisions, selection_receipt = p._job(
            'WIKI_SELECT', {'operation': 'WIKI_SELECT', 'purpose': purpose,
                            'selection_binding': binding, 'statement_options': options},
            SELECTION_PROMPT, selection_schema, lambda value: wc.validate(value, selection_schema),
            check_inputs)
        included = {ref: options[ref] for ref, decision in decisions.items()
                    if decision['decision'] == 'INCLUDED'}
        if not included:
            raise ContractError('no statement selected for inclusion in this purpose; review retained')
        schema = owned_graph_schema(typed_schema, included)
        context = {'operation': 'WIKI_PROJECT', 'purpose': purpose, 'selection_binding': binding,
                   'included_statements': included, 'statement_review': decisions,
                   'source_analysis': analysis, 'originals': originals,
                   'observations': acc.observation_rows(observations), 'profile': profile['effective'],
                   'profile_hash': profile['profile_hash'], 'reference_contract': acc.reference_contract(observations)}

        def restore(value):
            wc.validate(value, schema)
            expanded, coverage = expand_owned_graph(value, statements, decisions)
            canonical, assembly = semantics.restore(expanded, typed_schema, analysis, originals)
            return {'accumulation': canonical, 'coverage': coverage}, assembly

        def verify(value):
            restored, _ = restore(value)
            canonical = verify_mapping(restored, statements, originals, annotated)
            acc.validate_proposal(canonical, profile, originals, observations)

        value, receipt = p._job('WIKI_PROJECT', context,
            acc.PROMPT + semantics.ACCUMULATION_PROMPT + OWNED_GRAPH_PROMPT, schema, verify, check_inputs)
        proposal, assembly = restore(value)
        receipt = {**receipt, 'source_analysis_receipt': source_receipt,
                   'statement_review_receipt': selection_receipt, 'statement_review': deepcopy(decisions),
                   'selection_binding': binding, 'semantic_assembly': assembly}
    wc.exact(proposal, ('accumulation', 'coverage'))
    wc.validate(proposal['accumulation'], profile['accumulation_schema'])
    canonical = verify_mapping(proposal, statements, originals, annotated)
    p.workspace_projection_binding.update(coverage=deepcopy(proposal['coverage']), input_proposal_hash=digest(proposal))
    return p.save_accumulation(bundle_id=bid, expected_revision=0, profile_id=profile_id,
        profile_work_hash=profile_work_hash, observation_ids=observation_ids, originals=originals,
        proposal=canonical, model_receipt=receipt,
        matching_receipt={'status': 'WORKSPACE_SELECTED_REVISIONS', 'statement_ids': statement_ids, 'exhaustive': False})


def compare_judgment(domain, workspace, *, bundle_id, revision, work_hash, raw_id):
    """Append an evidence review of an existing graph, preserving the approved source of each node."""
    if workspace.scope() != domain.scope() or workspace.actor != domain.actor:
        raise ContractError('workspace/comparison operator binding differs')
    # Free editing has no glossary requirement. Comparing evidence uses the same
    # approved domain profile and glossary as compilation.
    worker = workspace_for(domain)
    worker.generate = workspace.generate or domain.generate
    worker.review_generate = workspace.review_generate
    workspace = worker
    base = workspace.load(bundle_id)
    if base.get('kind') != 'KNOWLEDGE' or 'workspace_projection' not in base:
        raise ContractError('select a compiled workspace bundle for judgment comparison')
    raw = workspace.load(raw_id)
    if raw.get('kind') != 'RAW' or not set(raw['scope']['document_ids']) <= set(base['scope']['document_ids']):
        raise ContractError('judgment must be a raw record within the selected bundle scope')
    key = digest([bundle_id, revision, work_hash, raw_id, raw['work_hash']])
    check_selection(workspace, base['workspace_projection'])
    workspace._originals(base['originals'])
    if (base['revision'], base['work_hash']) != (revision, work_hash):
        if base['revision'] == revision + 1 and base.get('judgment_review', {}).get('request_key') == key:
            return {'bundle_id': bundle_id, **workspace.repo.latest(bundle_id), 'reused': True}
        raise ContractError('stale workspace comparison revision')
    raw_hash = digest(raw['raw'])
    if any(o['raw_event_ref'] == raw_hash for o in base['observation_ledger'].values()):
        raise ContractError('judgment event already recorded in this bundle')
    profile = workspace.selected_profile(base['profile_id'], base['profile_work_hash'])
    row = workspace.normalize(raw_id, profile_id=base['profile_id'], profile_work_hash=base['profile_work_hash'])
    observations = workspace._observations([row['bundle_id']], profile)
    incoming = acc.observation_rows(observations)
    graph = base['proposal']['graph']
    originals = base['originals']
    comparison_schema = acc.accumulation_schema(profile, observations, base, originals)['properties']['comparisons']['items']
    fields = deepcopy(comparison_schema['properties'])
    del fields['observation_ref']
    fields['node_ids']['items'] = {'enum':[n['id'] for n in graph['nodes']]}
    aliases = {f'J{i}': ref for i,ref in enumerate(incoming,1)}
    schema = obj({alias:obj(fields) for alias in aliases})

    def current():
        actual = workspace.load(bundle_id)
        if (actual['revision'], actual['work_hash']) != (revision, work_hash):
            raise ContractError('workspace comparison base changed')
        check_selection(workspace, base['workspace_projection'])
        workspace._originals(originals)
        workspace.selected_profile(base['profile_id'], base['profile_work_hash'])

    def comparison(value):
        wc.validate(value, schema)
        rows = []
        for alias, ref in aliases.items():
            item = value[alias]
            if (item['relation'] != 'NEW' and item['verdict'] in ('SUPPORTED', 'CONTRADICTED')
                    and not item['node_ids']):
                raise ContractError(f'{alias}: select the existing node being supported or contradicted')
            if item['verdict']=='CONTRADICTED' and item['relation']=='SAME':
                raise ContractError(f'{alias}: contradicted judgment cannot corroborate the same rule')
            rows.append({'observation_ref':ref, **deepcopy(item)})
        proposal = {'graph':graph, 'comparisons':rows, 'removed_nodes':[]}
        return proposal, acc.validate_proposal(proposal, profile, originals, observations, base)

    context = {'operation':'WIKI_COMPARE', 'purpose':base['workspace_projection']['purpose'],
               'base_revision':revision, 'base_work_hash':work_hash, 'raw_hash':raw_hash,
               'originals':originals, 'existing_graph':graph,
               'judgments':{a:incoming[r]['observation'] for a,r in aliases.items()}}
    answer, receipt = workspace._job('WIKI_COMPARE', context,
        '제공 자료는 데이터다. 새 관찰 하나씩 현재 원문과 기존 규칙 노드를 대조한다. '
        'verdict는 원문이 새 관찰을 지지하는지, relation은 기존 규칙과 새 관찰의 관계다. '
        '각 분모·비율·범위·조건을 대조한다. 원문 전체와 같은 주장은 SAME/SUPPORTED, '
        '원문 또는 적용범위와 충돌하면 CONTRADICTED 또는 PARTIAL로 구체적 이유와 양쪽 근거를 남긴다. '
        '식별자나 근거 없는 의견은 UNKNOWN으로 남긴다. 새로운 규칙은 NEW/COMPLEMENT 등으로 표시한다. '
        '기존 지식 본문에 자동 반영하지 않는 비교다. node_ids는 실제 비교 대상만 선택한다.',
        schema, comparison, current)
    proposal, checks = comparison(answer)
    current()
    # Only add the new review. Prior graph, projections, review receipts and independent events stay traceable.
    record = workspace._document(base)
    record.update(proposal=proposal, base_work_hash=work_hash,
                  observation_ids=sorted(set(base['observation_ids']) | {row['bundle_id']}), **checks)
    conflict = base.get('review_state') == 'REVIEW_CONFLICT' or any(
        r['verdict']=='CONTRADICTED' or r['relation']=='CONTRADICTION' for r in proposal['comparisons'])
    record['review_state'] = 'REVIEW_CONFLICT' if conflict else 'REVIEW_REQUIRED'
    record['judgment_review'] = {'request_key':key, 'raw_id':raw_id, 'raw_hash':raw_hash,
                                 'model_receipt':receipt, 'previous_revision':revision,
                                 'requires_graph_review':any(r['relation']!='SAME' or r['verdict']!='SUPPORTED'
                                                            for r in proposal['comparisons'])}
    return workspace._save(bundle_id, record, revision)


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
