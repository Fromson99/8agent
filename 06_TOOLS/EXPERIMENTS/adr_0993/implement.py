from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
meta=read(DES/'candidate.json');P=ROOT/meta['path'];S=P/'snapshot'/meta['selected_code_relative'];L=S/'02_BACKEND/semantic_runtime/legal_agent'
code='''"""Bound source knowledge originals to the existing assessment evidence pack.

A prepared original is a review candidate, never an adopted legal conclusion.
Native read receipts, budgets, authorization and publication remain authoritative.
"""
from copy import deepcopy
from ..contracts import digest
from .errors import ContractError, BudgetExhausted
from .repository import text_hash

LIMIT_CHARS = 16000
LIMIT_ITEMS = 12


def enabled(execution):
    transport = execution.host.pipeline.term_agent.transport
    plan = getattr(execution.host, 'knowledge_plan', None)
    return bool(getattr(transport, 'knowledge_delivery_enabled', False) and plan and plan['mode'] == 'consume')


def enrich(execution, selection):
    if not enabled(execution): return selection
    from . import unit_reading as ur
    from .unit_relations import hit_for
    from . import query_scope as qs
    from .evidence_inventory import covers, intervals
    s = execution.s.sources
    value = execution.host.knowledge_plan
    binding = {k: execution.host.binding.get(k) for k in ('generation', 'store_sha256', 'unit_index_sha256')}
    if value['plan']['binding']['source_binding'] != binding:
        raise ContractError('knowledge delivery source binding changed')
    result = deepcopy(selection)
    originals = {r['source_id']: r for r in result.get('selected_originals', [])}
    evidence = {e['evidence_id']: e for e in result.get('selected_evidence', [])}
    items = []; used = 0
    state = ur.read_state(s)
    for index, item in enumerate(value['plan']['items']):
        refs = item['source_refs']
        if not refs: continue
        receipt = {'ref': item['ref'], 'title': item['title'], 'status': 'OMITTED', 'reason': None,
                   'source_refs': refs, 'source_ids': [], 'evidence_ids': [], 'automatic_adoption': False}
        if index >= LIMIT_ITEMS:
            receipt['reason'] = 'ITEM_LIMIT'; items.append(receipt); continue
        hits = {}; exclusion = None
        for ref in refs:
            did, bid = ref['document_id'], str(ref['locator'])
            if did not in s.scope or ref['version'] != did:
                raise ContractError('knowledge delivery source permission/version changed')
            raw = s.store.source(did, bid)
            if text_hash(raw['text']) != ref['content_hash']:
                raise ContractError('knowledge delivery source hash changed')
            ids = [sid for sid in s.matcher._unit_sources(did, str(raw['unit_id']))
                   if sid in s.tools.sources and any(str(b['block_id']) == bid for b in s.tools.sources[sid]['blocks'])]
            if len(ids) != 1: raise ContractError('knowledge source anchor is not unique')
            sid = ids[0]
            groups = [g for g in selection.get('investigation_state', {}).get('groups', {}).values() if g['source_id'] == sid]
            if groups and all(g['status'] == 'EXCLUDED' for g in groups):
                exclusion = 'MODEL_EXCLUDED'; break
            if qs.active(s) and bid not in qs.permitted_blocks(s, sid):
                exclusion = 'OUTSIDE_REQUEST_SCOPE'; break
            h = hit_for(s, sid, raw['unit_id']); hits[h['key']] = h
        if exclusion:
            receipt['reason'] = exclusion; items.append(receipt); continue
        # Group all named units in a source; native grouped offers include their
        # ancestor introductions, retaining governing conditions without siblings.
        grouped = ur.group_hits(s, list(hits.values()))
        planned = []
        for h in grouped:
            offers, _ = ur.offer_plan(s, h)
            own = next((o for o in offers if o['extent'] == 'exact'), None)
            if own is None: exclusion = 'NO_AUTHORIZED_READ_OFFER'; break
            planned.append((h, own))
        size = sum(o['chars'] for _, o in planned)
        if exclusion or used + size > LIMIT_CHARS:
            receipt['reason'] = exclusion or 'DELIVERY_CHAR_LIMIT'; items.append(receipt); continue
        records = []
        try:
            for h, offer in planned:
                r = ur.read(s, h, offer, action_state=state)
                if not r['complete']:
                    exclusion = 'INCOMPLETE_READ'; break
                records.append(r)
        except BudgetExhausted:
            exclusion = 'NATIVE_READ_BUDGET'
        if exclusion:
            receipt['reason'] = exclusion; items.append(receipt); continue
        # The complete source-method bundle must cover every declared anchor.
        additions = {e['evidence_id']: e for r in records for e in r['evidence']}
        for ref in refs:
            spans = [p for e in additions.values() if e['document_id'] == ref['document_id'] for p in e['spans']]
            text = s.store.source(ref['document_id'], ref['locator'])['text']
            if not covers([{'block_id': str(ref['locator']), 'start_cp': 0, 'end_cp': len(text)}], spans):
                raise ContractError('knowledge bundle lacks declared original')
        for sid, row in ur.original_map(records).items():
            extra = [{**p, 'evidence_id': e['evidence_id']} for e in additions.values() if e['source_id'] == sid for p in e['spans']]
            previous = originals.get(sid)
            if previous:
                old_spans = previous.get('adopted_spans')
                if old_spans is None:
                    old_spans = [{**p, 'evidence_id': e['evidence_id']} for eid in previous['evidence_ids'] for e in [evidence[eid]] for p in e['spans']]
                extra = old_spans + extra
            merged = intervals(extra)
            text = '\\n'.join(s.store.source(row['document_id'], bid)['text'][lo:hi]
                for bid in sorted(merged, key=int) for lo, hi in merged[bid])
            originals[sid] = {**(previous or row), 'text': text, 'adopted_spans': extra,
                'evidence_ids': list(dict.fromkeys(p['evidence_id'] for p in extra)),
                'knowledge_review_candidate': True, 'article_complete': bool(row['article_complete'] or previous and previous.get('article_complete'))}
        evidence.update(additions); used += size
        receipt.update(status='PREPARED', source_ids=list(dict.fromkeys(r['source_id'] for r in records)), evidence_ids=list(additions))
        items.append(receipt)
    receipt = {'contract': 'knowledge-original-delivery-v1', 'binding': binding,
               'plan_hash': value['plan'].get('plan_hash'), 'items': items, 'supplemental_chars': used,
               'source_pack_hash': digest(list(originals.values())), 'automatic_adoption': False}
    result.update(selected_originals=list(originals.values()), selected_evidence=list(evidence.values()),
        final_ids=list(originals), final_evidence_ids=list(evidence),
        final_packets=[{'packet_id': 'knowledge-review-originals', 'evidence': list(evidence.values())}],
        knowledge_original_delivery=receipt)
    for row in items:
        if row['status'] == 'OMITTED':
            result.setdefault('completion_limitations', []).append('검토 원문 미전달: '+row['title']+' ('+row['reason']+')')
    execution.s.work.event('KNOWLEDGE_ORIGINALS_PREPARED', receipt)
    execution.knowledge_delivery = receipt
    return result


def model_input(execution, data, phase):
    if not enabled(execution) or not phase.startswith('memory-assess'): return data, None
    receipt = getattr(execution, 'knowledge_delivery', None)
    if not receipt: return data, None
    summary = {'items': [{k: r[k] for k in ('ref', 'title', 'status', 'reason', 'source_ids')} for r in receipt['items']],
        'instruction': 'PREPARED 원문은 sources/evidence_options에 전달한 검토 후보다. 현재 질문에 관련된 조건·수치·예외를 확인해 답하고, 무관한 항목은 적용하지 않는다. 연결이나 전달 자체는 법률 적용의 증명이 아니다. OMITTED 원문을 읽었다고 주장하지 않는다.'}
    view = {**data, 'knowledge_original_review': summary}
    event = {'contract': receipt['contract'], 'phase': phase, 'input_hash': digest(view),
             'receipt_hash': digest(receipt), 'items': summary['items'], 'legal_adoption': False}
    return view, event
'''
(L/'knowledge_delivery.py').write_text(code)
ac.register_file(P,str((L/'knowledge_delivery.py').relative_to(P/'snapshot')),upstream_state='absent')
p=L/'unified_rag.py';s=p.read_text().replace("'knowledge_bridge.py','wiki_recall.py'","'knowledge_bridge.py','knowledge_delivery.py','wiki_recall.py'")
s=s.replace('        return super().invoke(system,data,schema,phase,timeout=timeout)', '''        from .knowledge_delivery import model_input
        data, delivery = model_input(self, data, phase)
        try:
            result = super().invoke(system,data,schema,phase,timeout=timeout)
        except Exception:
            if delivery:self.s.work.event('KNOWLEDGE_INPUT_FAILED', delivery)
            raise
        if delivery:self.s.work.event('KNOWLEDGE_INPUT_RETURNED', delivery)
        return result''')
s=s.replace('        self.record(stage,payload)\n        return payload', '''        if stage == 'SELECT':
            from .knowledge_delivery import enrich
            payload = enrich(self, payload)
        elif stage == 'ASSESS':
            self.knowledge_delivery = parts.get('SELECT', {}).get('payload', {}).get('knowledge_original_delivery')
        self.record(stage,payload)
        return payload''')
# Restore a saved receipt before assessment, including resume; not after invocation.
s=s.replace('        try:\n            payload=super().stage',"        if stage == 'ASSESS':\n            self.knowledge_delivery = parts.get('SELECT', {}).get('payload', {}).get('knowledge_original_delivery')\n        try:\n            payload=super().stage")
p.write_text(s)
config=read(S/'00_SYSTEM/PIPELINE.json')
for entry in config['engines'].values():
 p=S/entry['manifest'];engine=read(p);engine['files']={n:sha(S/n) for n in engine['files']}
 if '02_BACKEND/semantic_runtime/legal_agent/unified_rag.py' in engine['files']:
  engine['files']['02_BACKEND/semantic_runtime/legal_agent/knowledge_delivery.py']=sha(L/'knowledge_delivery.py')
 put(p,engine);entry['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',config)
m=read(ADR/'실험/manifest.json');m['integration']['rationale']=m['integration'].pop('reason');put(ADR/'실험/manifest.json',m)
print('Implemented source bundle delivery in candidate SELECT -> ASSESS; MAIN untouched')
