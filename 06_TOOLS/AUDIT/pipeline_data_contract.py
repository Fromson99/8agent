"""Offline source, review, storage, card and feedback consistency checks.

These checks authenticate neither reviewers nor legal correctness and never
admit data or activate MAIN. Referenced schemas are local and hash-bound.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

H = module(ROOT / '02_BACKEND/PIPELINE/engine_host.py', 'stage_schema_host')
L = module(ROOT / '06_TOOLS/AUDIT/legal_semantic_contract.py', 'stage_semantic_contract')

def digest(value): return L.digest(value)

def validate(contract, value, *, context=None, root=ROOT):
    context = context or {}; errors = []; config = H.load(root)
    def check(ok, reason):
        if not ok: errors.append(reason)
    try: H.validate_value(config, contract, value, root)
    except Exception as exc: return ['schema: ' + str(exc)]
    def unique(rows, key, label):
        ids = [r[key] for r in rows]; check(len(ids) == len(set(ids)), 'duplicate ' + label)
        return {r[key]: r for r in rows}
    def artifact(reference):
        found = context.get('artifacts', {}).get(reference['id'])
        if found is None:
            errors.append('artifact context missing: ' + reference['id']); return None
        raw = found['raw']; actual = hashlib.sha256(raw.encode()).hexdigest()
        check(reference == found['ref'], 'artifact reference drift: ' + reference['id'])
        check(actual == reference['sha256'], 'artifact byte hash drift: ' + reference['id'])
        return json.loads(raw)
    def scope_equal(a, b): check(a == b, 'scope mismatch')
    canonical = context.get('canonical'); query = context.get('query')
    templates = context.get('templates', [])
    entities = {}
    if canonical:
        for collection, typ in L.COLLECTIONS.items():
            for entity in canonical['payload'][collection]: entities[entity['id']] = (typ, entity)
    def entity(identifier, typ=None):
        result = entities.get(identifier)
        check(result is not None, 'canonical entity missing: ' + identifier)
        if result is not None and typ: check(result[0] == typ, 'canonical entity type mismatch: ' + identifier)
        return result[1] if result else None
    def bound():
        if canonical is None:
            errors.append('canonical context required'); return
        scope_equal(value['scope'], canonical['scope'])
        check(value['canonical_generation_id'] == canonical['generation_id'], 'canonical generation mismatch')
        check(value['canonical_payload_sha256'] == digest(canonical['payload']), 'canonical payload hash mismatch')
    def card_ids(rows):
        unique(rows, 'query_card_id', 'query card')
        if query is None:
            errors.append('query context required'); return {}
        check(value['query_plan_id'] == query['id'], 'query identity mismatch')
        scope_equal(value['scope'], query['scope'])
        expected = {r['id']: r for r in query['cards']}
        check(set(expected) == {r['query_card_id'] for r in rows}, 'query cards omitted or invented')
        return expected
    kind = value.get('record_kind')
    if contract.startswith('semantic.'):
        return L.validate(value, canonical=canonical if contract not in ('semantic.observation','semantic.canonical') else None, templates=templates, sources=context.get('sources'), root=root)
    if contract == 'source.corrected':
        raw = unique(value['raw_blocks'], 'id', 'raw block'); blocks = unique(value['blocks'], 'id', 'block')
        units = unique(value['units'], 'id', 'unit'); corrections = unique(value['corrections'], 'id', 'correction')
        unique(value['references'], 'id', 'reference'); unique(value['issues'], 'id', 'issue')
        inputs = unique(value['input_artifacts'], 'id', 'source artifact')
        check(value['document_version_id'] in value['scope']['document_version_ids'], 'document outside scope')
        for r in raw.values(): check(r['source_artifact_id'] in inputs, 'raw block source missing')
        def text_span(span, raw_input=False, empty=False):
            source = raw if raw_input else blocks; key = span['raw_block_id'] if raw_input else span['block_id']
            row = source.get(key)
            if row is None:
                errors.append('span block missing'); return None
            a, b = span['start'], span['end']
            check(0 <= a <= b <= len(row['text']) and (empty or a < b), 'span range invalid')
            return row['text'][a:b]
        for correction in corrections.values():
            check(text_span(correction['source_span'], True, True) == correction['before'], 'correction before differs from raw')
            if correction['review_status'] == 'APPROVED': check(correction['review_receipt'] is not None, 'correction approval receipt missing')
        raw_coverage = {key: [] for key in raw}
        for b in blocks.values():
            cursor = 0
            for mapping in b['mappings']:
                lo, hi = mapping['start'], mapping['end']
                check(lo == cursor and lo <= hi <= len(b['text']), 'corrected block mapping gap or overlap')
                cursor = hi; old = text_span(mapping['source_span'], True, True); new = b['text'][lo:hi]
                sp = mapping['source_span']
                if sp['raw_block_id'] in raw_coverage: raw_coverage[sp['raw_block_id']].append((sp['start'], sp['end']))
                if mapping['correction_id'] is None: check(old == new, 'unrecorded source text correction')
                else:
                    correction = corrections.get(mapping['correction_id'])
                    check(correction is not None, 'correction missing')
                    if correction:
                        check(correction['source_span'] == sp and correction['after'] == new, 'correction mapping mismatch')
                        check(correction['review_status'] != 'REJECTED', 'rejected correction applied')
                        if value['status'] == 'VALIDATED': check(correction['review_status'] == 'APPROVED', 'unreviewed correction in validated source')
            check(cursor == len(b['text']), 'corrected text not fully mapped')
        for key, ranges in raw_coverage.items():
            cursor = 0
            for a, b in sorted(ranges):
                check(a == cursor, 'raw text omitted or duplicated'); cursor = b
            check(cursor == len(raw[key]['text']), 'raw text not fully accounted for')
        for u in units.values():
            seen = {u['id']}; parent = u['parent_id']
            while parent is not None:
                if parent in seen:
                    errors.append('structure parent cycle'); break
                seen.add(parent); node = units.get(parent)
                if node is None:
                    errors.append('structure parent missing'); break
                parent = node['parent_id']
            for span in u['spans']: text_span(span)
            if u['parent_id'] in units:
                spans = units[u['parent_id']]['spans']
                for child in u['spans']:
                    check(any(p['block_id'] == child['block_id'] and p['start'] <= child['start'] <= child['end'] <= p['end'] for p in spans), 'child span outside parent')
        for r in value['references']:
            check(text_span(r['source_span']) == r['surface'], 'reference surface differs from source')
            check((r['target'] is not None and r['reason'] is None) if r['resolution'] == 'RESOLVED' else (r['target'] is None and bool(r['reason'])), 'reference resolution inconsistent')
            if r['target'] and r['target']['document_version_id'] == value['document_version_id']:
                check(r['target']['structural_unit_id'] in units, 'reference unit missing')
        if value['status'] == 'VALIDATED': check(not any(x['blocking'] for x in value['issues']), 'blocking source issue remains')
    elif contract == 'data.review':
        subject = artifact(value['subject'])
        if subject:
            scope_equal(value['scope'], subject['scope'])
            selected = subject
            try:
                for token in value['field_pointer'].split('/')[1:]:
                    token = token.replace('~1','/').replace('~0','~')
                    selected = selected[int(token)] if isinstance(selected, list) else selected[token]
                check(value['subject_payload_sha256'] == digest(selected), 'review payload mismatch')
            except (KeyError, IndexError, ValueError, TypeError):
                errors.append('review field pointer missing')
        if value['decision'] == 'APPROVE': check(all(x['result'] == 'PASS' for x in value['checks']), 'approval with failed or unknown checks')
        reviewer = value['reviewer']
        check((reviewer['model'] == 'claude-haiku-4-5-20251001') if reviewer['kind'] == 'MODEL' else reviewer['model'] is None, 'reviewer model identity inconsistent')
    elif contract == 'storage.generation':
        groups = ['structure_artifacts','observation_artifacts','canonical_artifacts','review_artifacts','projection_artifacts','index_artifacts']
        expected_contracts = {'structure_artifacts':{'source.corrected','source.structure'}, 'observation_artifacts':{'semantic.observation'}, 'canonical_artifacts':{'semantic.canonical'}, 'review_artifacts':{'data.review'}, 'projection_artifacts':{'storage.projection'}, 'index_artifacts':{'index.lexical'}}
        loaded = {}
        for group in groups:
            loaded[group] = []
            for reference in value[group]:
                check(reference['contract'] in expected_contracts[group], 'wrong storage artifact contract: ' + group)
                item = artifact(reference)
                if item is None: continue
                try: H.validate_value(config, reference['contract'], item, root)
                except Exception as exc:
                    errors.append('invalid storage artifact: ' + str(exc)); continue
                loaded[group].append(item)
                if reference['contract'] == 'source.corrected':
                    errors.extend(validate('source.corrected', item, context=context, root=root))
                elif reference['contract'] in ('semantic.observation', 'semantic.canonical'):
                    errors.extend(L.validate(item, sources=context.get('sources'), root=root))
                if 'scope' in item:
                    s = item['scope']; whole = value['scope']
                    check(set(s['document_version_ids']) <= set(whole['document_version_ids']), 'storage document outside scope')
                    check({k:v for k,v in s.items() if k != 'document_version_ids'} == {k:v for k,v in whole.items() if k != 'document_version_ids'}, 'storage scope mismatch')
        for row in loaded['canonical_artifacts']:
            check(row['generation_id'] == value['generation_id'], 'loaded canonical generation mismatch')
            observations = {r['id']: r for r in loaded['observation_artifacts']}
            check(set(row['source_observation_ids']) <= set(observations), 'canonical observation lineage missing')
            for receipt in row['review_receipts']:
                check(any(r['id'] == receipt['id'] and r['sha256'] == receipt['sha256'] for r in value['review_artifacts']), 'canonical review receipt not bound')
            if value['status'] == 'VALIDATED':
                matching = [r for r in loaded['review_artifacts'] if r['decision'] == 'APPROVE' and r['subject_payload_sha256'] == digest(row['payload']) and r['subject']['id'] in row['source_observation_ids'] and r['field_pointer'] == '/payload']
                check(bool(matching), 'canonical payload lacks matching whole-payload approval')
                for review in matching: errors.extend(validate('data.review', review, context=context, root=root))
        for row in loaded['projection_artifacts']:
            check(row['canonical_generation_id'] == value['generation_id'], 'projection generation mismatch')
            candidates = [c for c in loaded['canonical_artifacts'] if c['scope'] == row['scope'] and digest(c['payload']) == row['canonical_payload_sha256']]
            check(len(candidates) == 1, 'projection canonical payload not bound')
            if len(candidates) == 1:
                errors.extend(validate('storage.projection', row, context={**context,'canonical':candidates[0]}, root=root))
        for row in loaded['index_artifacts']:
            check(row['semantic_generation'] == value['generation_id'] and row['source_set_sha256'] == value['scope']['source_set_sha256'], 'index generation or source mismatch')
        if value['status'] == 'VALIDATED': check(value['validation_receipt'] is not None, 'storage validation receipt missing')
        if value['migration']:
            check(value['migration']['from_generation_id'] == value['parent_generation_id'], 'migration parent mismatch')
    elif contract == 'storage.projection':
        bound(); unique(value['entries'], 'id', 'projection entry')
        for row in value['entries']:
            check(row['document_version_id'] in value['scope']['document_version_ids'], 'projection document outside scope')
            for r in row['entity_refs']: entity(r['id'], r['type'])
            for eid in row['evidence_ids']:
                evidence = entity(eid, 'Evidence')
                if evidence: check(evidence['document_version_id'] == row['document_version_id'] and evidence['structural_unit_id'] == row['structural_unit_id'], 'projection evidence coordinate mismatch')
    elif contract == 'rag.templates':
        unique([r['template'] for r in value['templates']], 'id', 'template')
        for template in value['templates']: errors.extend(L.validate(template, root=root))
    elif contract in ('rag.hits','rag.cards'):
        bound(); expected = card_ids(value['cards'])
        for row in value['cards']:
            qcard = expected.get(row['query_card_id'])
            if contract == 'rag.hits':
                for hit in row['hits']:
                    check(hit['document_version_id'] in value['scope']['document_version_ids'], 'hit document outside scope')
                    if qcard: check(hit['document_version_id'] in qcard['document_version_ids'], 'hit outside query card documents')
                    for rule in hit['canonical_rule_ids']: entity(rule, 'Rule')
                    for eid in hit['evidence_ids']:
                        evidence = entity(eid, 'Evidence')
                        if evidence: check(evidence['document_version_id'] == hit['document_version_id'] and evidence['structural_unit_id'] == hit['structural_unit_id'], 'hit evidence coordinate mismatch')
            elif row['bundle'] is None: check(bool(row['reason']), 'missing card bundle needs reason')
            else:
                check(row['reason'] is None, 'assembled bundle has unavailable reason')
                check(row['bundle']['canonical_generation_id'] == value['canonical_generation_id'] and row['bundle']['canonical_payload_sha256'] == value['canonical_payload_sha256'], 'card bundle generation or payload mismatch')
                scope_equal(row['bundle']['scope'], value['scope'])
                if qcard: check(row['bundle']['template_id'] == qcard['template_id'], 'query card template mismatch')
                errors.extend(L.validate(row['bundle'], canonical=canonical, templates=templates, root=root))
    elif contract == 'rag.answer':
        bound(); cards = context.get('cards')
        if cards is None: errors.append('card set context required')
        else:
            check(value['card_set_id'] == cards['id'], 'answer card set identity mismatch')
            check(value['query_plan_id'] == cards['query_plan_id'], 'answer query identity mismatch')
            errors.extend(validate('rag.cards', cards, context=context, root=root))
            allowed = {}
            for row in cards['cards']:
                evidence = set(); bundle = row['bundle']
                if bundle:
                    refs = [r for s in bundle['slots'] for r in s['refs']]
                    refs += [{'type':'Rule','id':rid} for rid in bundle['entry_rule_ids']]
                    for r in refs:
                        found = entities.get(r['id'])
                        if found: evidence.update([r['id']] if found[0] == 'Evidence' else found[1]['evidence_ids'])
                allowed[row['query_card_id']] = evidence
            accounted = set(); unique(value['claims'], 'id', 'answer claim')
            for claim in value['claims']:
                ids = set(claim['query_card_ids']); accounted.update(ids)
                check(ids <= set(allowed), 'answer references unknown card')
                check(set(claim['evidence_ids']) <= set().union(*(allowed.get(k,set()) for k in ids)), 'answer citation outside named cards')
                check(claim['text'] in value['text'], 'claim missing from answer text')
            for row in value['unresolved']:
                check(row['query_card_id'] in allowed, 'unknown unresolved card'); accounted.add(row['query_card_id'])
            check(accounted == set(allowed), 'answer silently drops query card')
    elif contract in ('feedback.event','feedback.proposal'):
        if value['target']['entity_ref']:
            r = value['target']['entity_ref']; entity(r['id'], r['type'])
        if contract == 'feedback.proposal':
            if value['action'] in ('CHANGE_SCHEMA','CHANGE_ENGINE','CHANGE_TEMPLATE'):
                check(value['proposed_artifact'] is not None, 'concrete proposed artifact required')
            if value['semantic_feedback'] is not None:
                scope_equal(value['scope'], value['semantic_feedback']['scope'])
                errors.extend(L.validate(value['semantic_feedback'], canonical=canonical, root=root))
    return errors


def check_examples(root=ROOT):
    folder = root / '01_DATA/CONTRACTS/PIPELINE_STAGES'
    examples = json.loads((folder / 'examples.json').read_text())
    results = {}
    for name, row in examples.items():
        value = json.loads((folder / row['file']).read_text())
        context = json.loads((folder / row['context_file']).read_text()) if 'context_file' in row else None
        results[name] = validate(row['contract'], value, context=context, root=root)
    return results


def main():
    errors = check_examples()
    print(json.dumps({'checks':errors,'ok':not any(errors.values()),'reviewer_authenticated':False,'main_changed':False},ensure_ascii=False,indent=2))
    raise SystemExit(int(any(errors.values())))

if __name__ == '__main__': main()
