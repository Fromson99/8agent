#!/usr/bin/env python3
"""Prepare draft MVP cases with evaluator data physically separated.

Only bounded SQLite metadata/selected-section reads are used. No runtime, full
index, model, answer synthesis, or judgment policy is loaded by this builder.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import resource
import sqlite3


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler'
GENERATION = ROOT / '01_DATA/TERM_RELEASES/latest-selection-20261015-r1/generation'
INPUTS = {
    'seed_selection': ROOT / '07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/SEED_ARTICLES_20261024.json',
    'cm': ROOT / '01_DATA/review/cm_core_e2e_v3.json',
    'cm_rebind': ROOT / '09_ARTIFACTS/AUDITS/20261024-cm-rebind/CM51_SOURCE_PACKAGE_SELECTION_20261015.json',
    'cm_rebind_report': ROOT / '09_ARTIFACTS/AUDITS/20261024-cm-rebind/REBIND_REPORT.json',
    'fsc': ROOT / '01_DATA/review/fsc_hard_retrieval_v3.json',
    'risk_cm': ROOT / '01_DATA/GOLDEN/risk_cm/v1/questions.json',
    'risk_evidence': ROOT / '01_DATA/GOLDEN/risk_cm/v1/evidence-index.json',
    'adr_1037': ROOT / '04_EXPERIMENTS/ADR/ADR-1037-uncapped-judgment-live-question/artifacts/known-request.json',
    'seed_review': ROOT / '01_DATA/ONTOLOGY_WORK/review/ADR-1041/SEED_REVIEW.json',
    'cm_export': ROOT / '01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json',
    'risk_export': ROOT / '01_DATA/GOLDEN/risk_cm/EXPORT_AUTHORIZATION_20261024.json',
}
ANNEX_DOCUMENTS = {
    '금융투자회사의 리스크관리 모범규준 별표 17-1': '4b6659619110921b',
    '금융투자회사의 리스크관리 모범규준 별표 17-2': 'd15cde8add9a9d74',
}
LEGACY_PUBLIC_IDS = {'527731af0a9a554c', '8f93eda174f02974'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def receipt(path):
    path = Path(path)
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size}


def exact_write(path, value):
    raw = encoded(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('refusing to overwrite different frozen data: ' + str(path))
    else:
        with path.open('xb') as stream:
            stream.write(raw)


class SourceBinding:
    def __init__(self, generation, *, include_text=False):
        self.path = generation / 'store.sqlite'
        self.before = self.path.stat()
        self.include_text = include_text
        self.db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        self.db.execute('PRAGMA cache_size=-4096')

    def close(self):
        self.db.close()
        after = self.path.stat()
        if (after.st_size, after.st_mtime_ns) != (self.before.st_size, self.before.st_mtime_ns):
            raise ValueError('source store changed during freeze')

    def document(self, did):
        row = self.db.execute(
            "SELECT document_id,name,source_artifact_sha256,"
            "json_extract(json,'$.document_metadata.source_metadata') AS metadata, "
            "json_extract(json,'$.document_metadata.relative_path') AS relative_path, "
            "json_extract(json,'$.document_metadata.original_path') AS original_path "
            'FROM document WHERE document_id=?', (did,)).fetchone()
        if row is None:
            raise ValueError('source document unavailable: ' + did)
        return {'document_id': row['document_id'], 'document_name': row['name'],
                'source_artifact_sha256': row['source_artifact_sha256'],
                'source_metadata': json.loads(row['metadata']) if row['metadata'] else None,
                'source_relative_path': row['relative_path'], 'source_original_path': row['original_path']}

    def locate(self, name, coordinate):
        docs = self.db.execute('SELECT document_id FROM document WHERE name=? OR name LIKE ?',
                               (name, '% > ' + name)).fetchall()
        found = []
        for doc in docs:
            found.extend(self.db.execute(
                "SELECT document_id,unit_id,json FROM source_unit WHERE document_id=? "
                "AND json_extract(json,'$.coordinate_key')=?", (doc['document_id'], coordinate)))
        if not found:
            return {'status': 'MISSING_DOCUMENT' if not docs else 'MISSING_COORDINATE',
                    'document_name': name, 'coordinate_key': coordinate}
        if len(found) != 1:
            raise ValueError('ambiguous current coordinate: ' + name + ' ' + coordinate)
        return self.section(found[0]['document_id'], found[0]['unit_id'], coordinate)

    def section(self, did, uid, coordinate):
        row = self.db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',
                              (did, str(uid))).fetchone()
        if row is None:
            raise ValueError('selected source unit unavailable')
        unit = json.loads(row['json'])
        if unit.get('coordinate_key') != coordinate:
            raise ValueError('selected source coordinate changed')
        lo, hi = unit['span']
        return self._extent(did, str(uid), coordinate, (lo, hi),
            self.db.execute('SELECT block_id,unit_id,text,source_artifact_sha256 FROM block_payload '
                'WHERE document_id=? AND CAST(block_id AS INTEGER)>=? AND CAST(block_id AS INTEGER)<? '
                'ORDER BY CAST(block_id AS INTEGER)', (did, lo, hi)))

    def annex(self, label):
        did = ANNEX_DOCUMENTS[label]
        return self._extent(did, None, None, None, self.db.execute(
            'SELECT block_id,unit_id,text,source_artifact_sha256 FROM block_payload WHERE document_id=? '
            'ORDER BY CAST(block_id AS INTEGER)', (did,)))

    def _extent(self, did, uid, coordinate, bounds, cursor):
        doc = self.document(did)
        blocks, texts = [], []
        for row in cursor:
            if row['source_artifact_sha256'] != doc['source_artifact_sha256']:
                raise ValueError('block/document version mismatch')
            texts.append(row['text'])
            blocks.append({'block_id': row['block_id'], 'start_cp': 0, 'end_cp': len(row['text']),
                           'text_sha256': text_sha(row['text']),
                           **({'text': row['text'], 'owner_unit_id': row['unit_id'],
                               'owned_by_selected_unit': row['unit_id'] == uid} if self.include_text else {})})
        if not blocks:
            raise ValueError('source extent has no blocks')
        return {'status': 'BOUND', **doc, 'unit_id': uid, 'coordinate_key': coordinate,
                'extent_kind': 'ARTICLE_SECTION' if uid is not None else 'STANDALONE_ANNEX_DOCUMENT',
                'block_span': list(bounds) if bounds is not None else None, 'blocks': blocks,
                'section_text_sha256': text_sha('\n'.join(texts))}

    def seed_target(self, label):
        if label in ANNEX_DOCUMENTS:
            bound = self.annex(label)
        else:
            match = re.fullmatch(r'(.+) (제[0-9]+(?:-[0-9]+)?조(?:의[0-9]+)?)', label)
            if match is None:
                raise ValueError('unsupported literal seed coordinate: ' + label)
            bound = self.locate(match[1], 'body:' + match[2])
        return {'origin': 'SEED_SELECTION', 'label': label, 'current_binding': bound,
                'requiredness': 'NOT_INFERRED_FROM_SEED', 'answer_gold': False}

    def public_corpus(self, parent):
        query = ("SELECT document_id FROM document WHERE "
                 "json_extract(json,'$.document_metadata.source_category')='external' AND "
                 "json_extract(json,'$.document_metadata.source_metadata.security_class')='public' AND "
                 "json_extract(json,'$.document_metadata.source_metadata.export_allowed')=1")
        explicit = {r[0] for r in self.db.execute(query)}
        legacy = set(parent['json']['document_ids']) - explicit
        if legacy != LEGACY_PUBLIC_IDS:
            raise ValueError('legacy public scope drift; review authorization before extending')
        for did in legacy:
            self.document(did)
        return {'policy': 'EXPLICIT_EXTERNAL_PUBLIC_EXPORT_TRUE_PLUS_EXACT_PARENT_PUBLIC_IDS',
                'selection_sql': query, 'explicit_metadata_documents': len(explicit),
                'legacy_parent_public_document_ids': sorted(legacy),
                'legacy_authority': receipt(INPUTS['adr_1037']),
                'document_ids': sorted(explicit | legacy),
                'document_count': len(explicit | legacy), 'case_specific_gold_scope': False}


def build(generation, output):
    data = {key: load(path) for key, path in INPUTS.items()}
    source_receipts = {key: receipt(path) for key, path in INPUTS.items()}
    manifest = load(generation / 'manifest.json')
    cm = {c['id']: c for c in data['cm']['cases']}
    fsc = {c['id']: c for c in data['fsc']['cases']}
    risk = {c['id']: c for c in data['risk_cm']['cases']}
    rebind = {c['case_id']: c for c in data['cm_rebind']['cases']}
    risk_evidence = {e['id']: e for e in data['risk_evidence']['evidence']}
    cm_binding = data['cm_rebind']['built_against']
    if (cm_binding['generation'] != manifest['generation_id'] or
            cm_binding['store_sha256'] != manifest['store_sha256']):
        raise ValueError('CM rebind is not for the selected source generation')
    if source_receipts['cm']['sha256'] != data['cm_rebind']['source']['sha256']:
        raise ValueError('CM source changed after rebind')
    products, evaluators, gaps = [], [], []
    seen = set()
    sources = SourceBinding(generation)
    try:
        corpus = {'status': 'PENDING_SHARED_SCOPE_DECISION', 'authorization_confirmed': False,
                  'document_ids': None, 'case_specific_gold_scope': False}
        for seed_index, seed in enumerate(data['seed_selection']['seeds'], 1):
            seed_targets = [sources.seed_target(label) for label in
                            [seed['anchor'], *[r['article'] for r in seed['connections']]]]
            for selected in seed['questions']:
                cid, collection = selected['case_id'], selected['collection']
                if cid in seen:
                    raise ValueError('duplicate selected case: ' + cid)
                seen.add(cid)
                reference = None
                targets = []
                provenance = {'seed_index': seed_index, 'seed_excerpt': selected['question'],
                              'seed_anchor': seed['anchor'], 'seed_connections': deepcopy(seed['connections'])}
                if collection == 'cm':
                    case = cm[cid]
                    question, reference = case['question'], case['reference_answer']
                    package = rebind[cid]
                    if package['question'] != question or package['reference_answer'] != reference:
                        raise ValueError('CM original/rebind question or answer changed')
                    if text_sha(case['source_question'] + '\n' + reference) != case['reference_sha256']:
                        raise ValueError('CM reference hash mismatch')
                    original_targets = {(e['law'], e['coordinate_key']): e for e in case['evidence_articles']}
                    for entry in package['entries']:
                        current = sources.section(entry['selected_document_id'], entry['selected_unit_id'], entry['coordinate_key'])
                        if (current['source_artifact_sha256'] != entry['source_artifact_sha256'] or
                                current['section_text_sha256'] != entry['section_text_sha256']):
                            raise ValueError('CM selected source bytes changed: ' + cid)
                        targets.append({'origin': 'CM_EVIDENCE_ARTICLES_REBOUND', 'role': entry['evidence_role'],
                            'original_target': deepcopy(original_targets[(entry['document_name'], entry['coordinate_key'])]),
                            'current_binding': current})
                    provenance.update(source='cm', source_record='cases/' + cid,
                        source_question=case['source_question'], topic=case['topic'],
                        source_reference_sha256=case['reference_sha256'],
                        source_reference_hash_rule='SHA256(UTF-8(source_question + newline + reference_answer))',
                        reference_kind=case['reference_answer_kind'],
                        reference_status=package['reference_provenance']['status'],
                        rebind_provenance=deepcopy(package['reference_provenance']),
                        current_interpretation_revalidated=False)
                elif collection == 'fsc':
                    case = fsc[cid]
                    question, reference = case['question'], case['reference_answer']
                    for target in case['current_evidence_articles']:
                        targets.append({'origin': 'FSC_CURRENT_EVIDENCE_ARTICLES', 'role': target['evidence_role_v3'],
                            'original_target': deepcopy(target),
                            'current_binding': sources.locate(target['law'], target['coordinate_key'])})
                    external = [{'original_target': deepcopy(target),
                        'current_binding': sources.locate(target['law'], 'body:' + target['article'])}
                        for target in case['required_external_evidence']]
                    provenance.update(source='fsc', source_record='cases/' + cid,
                        published=case['published'], reference_answer_as_of=case['answer_as_of'],
                        legacy_current_as_of=case['current_as_of'], source_file=case['source_file'],
                        source_sha256=case['source_sha256'], historical_evidence=deepcopy(case['answer_time_evidence_articles']),
                        required_external_evidence=external, current_interpretation_revalidated=False)
                    gaps.append({'case_id': cid, 'code': 'HISTORICAL_FSC_REFERENCE_CURRENT_INTERPRETATION_UNVERIFIED',
                                 'reference_answer_as_of': case['answer_as_of']})
                    for target in external:
                        if target['current_binding']['status'] != 'BOUND':
                            gaps.append({'case_id': cid, 'code': 'REQUIRED_EXTERNAL_EVIDENCE_UNAVAILABLE',
                                         'target': deepcopy(target['current_binding'])})
                elif collection == 'risk_cm':
                    case = risk[cid]
                    question = case['question']
                    if case['reference_answer'] is not None or case['gold_approved']:
                        raise ValueError('risk question-only contract changed')
                    for eid in case['scope_assessment']['evidence_refs']:
                        target = risk_evidence[eid]
                        targets.append({'origin': 'RISK_CLASSIFICATION_SUPPORT_NOT_APPROVED_GOLD',
                            'reference_id': eid, 'original_target': deepcopy(target),
                            'current_binding': sources.locate(target['document_name'], target['coordinate_key'])})
                    provenance.update(source='risk_cm', source_record='cases/' + cid,
                        reference_status='QUESTION_ONLY', gold_approved=False,
                        transcription=case['transcription'], transcription_note=case['transcription_note'],
                        original_scope_assessment=deepcopy(case['scope_assessment']))
                    gaps.append({'case_id': cid, 'code': 'EVIDENCE_TARGETS_ARE_DIAGNOSTIC_NOT_APPROVED_ANSWER_GOLD'})
                elif cid == 'ADR-1037' and collection == 'adr':
                    question = data['adr_1037']['json']['question']
                    provenance.update(source='adr_1037', source_record='json/question', reference_status='NO_REFERENCE_ANSWER')
                    targets = deepcopy(seed_targets)
                    gaps.append({'case_id': cid, 'code': 'SEED_COVERAGE_ONLY_NO_REFERENCE_ANSWER'})
                else:
                    raise ValueError('unknown case collection: ' + cid)
                if not question or (reference is not None and not reference):
                    raise ValueError('empty question or reference')
                products.append({'case_id': cid, 'question': question})
                evaluators.append({'case_id': cid, 'collection': collection, 'question': question,
                    'question_sha256': text_sha(question), 'reference_answer': reference,
                    'reference_answer_sha256': text_sha(reference) if reference is not None else None,
                    'evaluation_class': ('FSC_HISTORICAL_REFERENCE_PENDING_CURRENT_REVIEW' if collection == 'fsc'
                        else 'CM_EXISTING_REFERENCE' if reference is not None else 'EVIDENCE_ONLY'),
                    'current_gold_approved': False if collection != 'cm' else None,
                    'source_provenance': provenance, 'evidence_targets': targets,
                    'seed_coverage_targets': deepcopy(seed_targets)})
        selected_docs = set()
        bundle_receipts = []
        for row in data['seed_review']['bundles']:
            path = ROOT / '01_DATA/ONTOLOGY_WORK' / row['path']
            if sha(path) != row['sha256']:
                raise ValueError('historical seed draft changed')
            bundle_receipts.append(receipt(path))
            selected_docs.update(p['anchor']['document_id'] for p in load(path)['provisions'])
        corpus.update(seed_bundle_document_count=len(selected_docs), seed_bundle_documents=sorted(selected_docs),
                      seed_bundle_documents_outside_shared_corpus=None)
    finally:
        sources.close()
    counts = Counter(row['collection'] for row in evaluators)
    if counts != {'cm': 27, 'fsc': 7, 'risk_cm': 2, 'adr': 1} or len(products) != 37:
        raise ValueError('expected exact 37 case composition')
    if sum(row['reference_answer'] is not None for row in evaluators) != 34:
        raise ValueError('expected exactly 34 preserved reference answers')
    for key, path in INPUTS.items():
        if receipt(path) != source_receipts[key]:
            raise ValueError('input changed during freeze: ' + key)
    product = {'schema_version': 'ontology-mvp-product-cases-v1', 'cases': products}
    evaluator = {'schema_version': 'ontology-mvp-evaluator-cases-v1', 'product_visible': False,
        'status': 'DRAFT_FSC_CURRENT_REFERENCE_REVIEW_PENDING',
        'cases': evaluators, 'unresolved_evaluation_decisions': gaps,
        'rules': ['No generated or repaired reference answers.',
                  'Historical source dates and current source binding are separate.',
                  'Seed coverage and question-only classification support do not establish answer gold.',
                  'This file does not select answer correctness thresholds or unrelated-reading semantics.']}
    exact_write(output / 'cases-product.json', product)
    exact_write(output / 'cases-evaluator.json', evaluator)
    freeze = {'schema_version': 'ontology-mvp-dataset-freeze-v1', 'experiment_id': 'ADR-1041-experiment-v1',
        'status': 'DRAFT_NOT_APPROVED_FOR_PRODUCT_EXECUTION', 'approved_for_live_execution': False,
        'case_order': [row['case_id'] for row in products],
        'counts': {'cases': 37, 'reference_answers': 34, 'evidence_only': 3, 'by_collection': dict(counts)},
        'source_inputs': source_receipts, 'seed_bundle_inputs': bundle_receipts,
        'generation': {'path': str(generation.relative_to(ROOT)), 'manifest': receipt(generation / 'manifest.json'),
            'generation_id': manifest['generation_id'], 'store_sha256_declared': manifest['store_sha256'],
            'store_full_hash_recomputed': False, 'source_store_unchanged_during_selected_reads': True},
        'public_corpus': corpus,
        'product': receipt(output / 'cases-product.json'), 'evaluator': receipt(output / 'cases-evaluator.json'),
        'builder': receipt(Path(__file__)), 'product_case_allowlist': ['case_id', 'question'],
        'source_mapping_method': 'CM exact pre-existing rebind; other source names plus exact stored coordinates; standalone annex IDs from reviewed seed provenance.',
        'source_text_hash_rule': 'SHA256(UTF-8(newline.join(selected section blocks ordered by numeric block_id)))',
        'unresolved_evaluation_decisions': gaps, 'gold_visible_to_product': False,
        'live_model_calls': 0, 'full_index_loaded': False, 'decision_eligible': False}
    exact_write(output / 'dataset-freeze.json', freeze)
    return freeze


def prepare_fsc_review(generation, output):
    """Preserve old replies and complete selected source sections for human review."""
    seed = load(INPUTS['seed_selection'])
    selected = [q['case_id'] for item in seed['seeds'] for q in item['questions'] if q['collection'] == 'fsc']
    if selected != ['fsc-hard-002', 'fsc-hard-003', 'fsc-hard-005', 'fsc-hard-006',
                    'fsc-hard-010', 'fsc-hard-008', 'fsc-hard-009']:
        raise ValueError('selected FSC case IDs/order changed')
    original = load(INPUTS['fsc'])
    cases = {case['id']: case for case in original['cases']}
    manifest = load(generation / 'manifest.json')
    sections, reviews, supplemental = {}, [], []
    sources = SourceBinding(generation, include_text=True)
    try:
        for cid in selected:
            case = cases[cid]
            reply = ROOT / case['source_file'].replace('data/wiki/', '01_DATA/wiki/', 1)
            if sha(reply) != case['source_sha256']:
                raise ValueError('historical FSC reply source hash changed: ' + cid)
            reply_text = reply.read_text(encoding='utf-8')
            targets = []
            for target in case['current_evidence_articles']:
                current = sources.locate(target['law'], target['coordinate_key'])
                section_id = None
                if current['status'] == 'BOUND':
                    section_id = current['document_id'] + ':' + current['unit_id']
                    old = sections.setdefault(section_id, current)
                    if old != current:
                        raise ValueError('same section has differing source bytes')
                historical = [deepcopy(e) for e in case['answer_time_evidence_articles']
                              if e['law'] == target['law'] and e['coordinate_key'] == target['coordinate_key']]
                targets.append({'role': target['evidence_role_v3'], 'benchmark_current_target': deepcopy(target),
                    'historical_targets': historical, 'selected_section_id': section_id,
                    'binding_status': current['status'],
                    'unavailable_binding': current if section_id is None else None})
            unavailable = []
            for target in case['required_external_evidence']:
                current = sources.locate(target['law'], 'body:' + target['article'])
                section_id = None
                if current['status'] == 'BOUND':
                    section_id = current['document_id'] + ':' + current['unit_id']
                    sections.setdefault(section_id, current)
                unavailable.append({'original_requirement': deepcopy(target), 'binding_status': current['status'],
                    'selected_section_id': section_id, 'unavailable_binding': current if section_id is None else None})
            reviews.append({'case_id': cid, 'question': case['question'], 'question_sha256': text_sha(case['question']),
                'historical_reference_answer': case['reference_answer'],
                'historical_reference_sha256': text_sha(case['reference_answer']),
                'published': case['published'], 'answer_as_of': case['answer_as_of'],
                'benchmark_current_as_of': case['current_as_of'], 'source_record': case['source_record'],
                'historical_reply': {**receipt(reply), 'text': reply_text,
                    'recorded_urls': sorted(set(re.findall(r'https?://[^\s<>]+', reply_text))),
                    'detail_url_recorded': False},
                'evidence_targets': targets, 'required_external_evidence': unavailable,
                'current_reference_answer': None, 'current_reference_status': 'REVIEW_PENDING',
                'current_gold_approved': False})
        for name, coordinate, review_case in (
            ('개인정보 보호법', 'body:제26조', 'fsc-hard-010'),
            ('신용정보의 이용 및 보호에 관한 법률', 'body:제32조', 'fsc-hard-010'),
            ('신용정보의 이용 및 보호에 관한 법률', 'body:제40조의2', 'fsc-hard-010'),
            ('자본시장과 금융투자업에 관한 법률 시행령', 'body:제47조', 'fsc-hard-009'),
        ):
            current = sources.locate(name, coordinate)
            section_id = None
            if current['status'] == 'BOUND':
                section_id = current['document_id'] + ':' + current['unit_id']
                sections.setdefault(section_id, current)
            supplemental.append({'review_case_id': review_case, 'document_name': name,
                'coordinate_key': coordinate, 'selected_section_id': section_id,
                'binding_status': current['status'], 'required_gold': False,
                'selection_reason': 'Reviewer-requested current-law context; not an approved seed or required gold.',
                'unavailable_binding': current if section_id is None else None})
    finally:
        sources.close()
    report = {'schema_version': 'fsc-current-reference-review-source-v1', 'status': 'SOURCE_EXTRACTION_ONLY',
        'purpose': 'User requested current-reference review before the 37x3 experiment; no product execution.',
        'case_count': len(reviews), 'source_section_count': len(sections), 'cases': reviews,
        'supplemental_review_targets': supplemental,
        'source_sections': [{'section_id': key, **value} for key, value in sorted(sections.items())],
        'source_inputs': {'fsc': receipt(INPUTS['fsc']), 'seed_selection': receipt(INPUTS['seed_selection'])},
        'generation': {'path': str(generation.relative_to(ROOT)), 'manifest': receipt(generation / 'manifest.json'),
            'generation_id': manifest['generation_id'], 'store_sha256_declared': manifest['store_sha256'],
            'store_full_hash_recomputed': False},
        'temporal_contract': deepcopy(original['temporal_contract']),
        'validity': {'meaning_of_current': 'SELECTED_LOCAL_GENERATION',
            'official_web_currentness_checked': False, 'legal_interpretation_performed': False,
            'historical_reference_relabelled_as_current': False,
            'selected_source_dates': 'source_sections[].source_metadata.enforce/revised, preserved as recorded',
            'current_source_urls': 'No exact current legal page URL was recorded in these selected source metadata; historical official endpoints remain in historical_targets.authority_source.endpoint.',
            'source_extent': 'Complete stored article span, including own and descendant blocks in original order; no summary or truncation.'},
        'live_model_calls': 0, 'full_index_loaded': False}
    exact_write(output / 'fsc-current-review-source.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation', type=Path, default=GENERATION)
    parser.add_argument('--output', type=Path, default=ADR / 'artifacts')
    parser.add_argument('--fsc-review-only', action='store_true')
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    if args.fsc_review_only:
        report = prepare_fsc_review(args.generation.resolve(), args.output.resolve())
        print(json.dumps({'case_count': report['case_count'], 'sections': report['source_section_count'],
            'status': report['status'], 'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}, ensure_ascii=False))
        return
    result = build(args.generation.resolve(), args.output.resolve())
    print(json.dumps({'counts': result['counts'], 'public_corpus_status': result['public_corpus']['status'],
        'evaluation_gaps': len(result['unresolved_evaluation_decisions']),
        'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}, ensure_ascii=False))


if __name__ == '__main__':
    main()
