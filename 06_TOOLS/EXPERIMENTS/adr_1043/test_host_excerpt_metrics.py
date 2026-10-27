"""Pure fixtures: no model, generation, SQLite, or experiment artifacts opened.

Run explicitly with the repository Python; this file is not an experiment run.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_metrics import OriginalStore, digest, public_host_excerpts, target_coverage, text_hash


class FixtureStore(OriginalStore):
    def __init__(self):
        self.text = '제1조(범위) A < B\n다음 원문'

    def block(self, did, bid):
        if (did, str(bid)) != ('D1', '10'):
            raise ValueError('FIXTURE_SOURCE_BLOCK_MISSING')
        return {'text':self.text, 'source_artifact_sha256':'source-version', 'unit_id':'10'}

    def coordinate(self, did, bid):
        return {'doc_id':did, 'node':10, 'coordinate_key':'body:제1조'}


def fixture():
    store = FixtureStore()
    span = {'id':'S1', 'source_id':'source-1', 'document_id':'D1', 'block_id':'10',
        'evidence_id':'E1', 'start_cp':0, 'end_cp':len(store.text),
        'text':store.text, 'text_hash':digest(store.text)}
    acquired = [{**span, 'source_artifact_sha256':'source-version'}]
    assessment = {'claims':[], 'disposition':'LIMITED_ANSWER', 'answer_coverage':'INSUFFICIENT',
        'issue_assessments':[{'status':'INSUFFICIENT'}], 'stop_reason':'ASSESSMENT_INPUT_LIMIT',
        'model_proposal':{'review_status':'INCOMPLETE', 'failure_code':'MODEL_INPUT_BUDGET_EXHAUSTED'},
        'source_excerpt_reply':{'schema_version':'verified-source-excerpt-reply-v1',
            'legal_conclusion_confirmed':False, 'absence_proven':False,
            'sources':[{'source_id':'source-1', 'document_name':'테스트법', 'heading':'제1조',
                'span_receipts':[span]}]}}
    text = ('원문은 확보했으나 답변 검토를 완료하지 못했습니다. 확인한 원문을 제공합니다.\n\n'
        '**확인한 원문: 테스트법 · 제1조**\n\n> 제1조(범위) A &lt; B\n> 다음 원문'
        '\n\n확인 범위\n\n- 판단 미완료')
    composition = {'assessment_hash':digest(assessment), 'claims':[], 'text':text,
        'source_excerpt_reply':deepcopy(assessment['source_excerpt_reply'])}
    answer = {'claims':[], 'text':text}
    meta = {'case':{'judgment_refs':{}}, 'accepted_outcome':{},
        'text_integrity':'VERIFIED_SOURCE_EXCERPTS', 'source_reply_contract':'verified-source-excerpt-reply-v1'}
    values = [assessment, composition, answer, meta, acquired, store, {'D1'}]
    rebind(values)
    return values


def rebind(values):
    assessment, composition, _, meta = values[:4]
    composition['assessment_hash'] = digest(assessment)
    composition['source_excerpt_reply'] = deepcopy(assessment['source_excerpt_reply'])
    meta['case']['judgment_refs'] = {'ASSESS':{'payload_hash':digest(assessment)},
        'COMPOSE':{'payload_hash':digest(composition)}}
    meta['accepted_outcome']['assessment_hash'] = digest(assessment)


class HostExcerptMetricsTest(unittest.TestCase):
    def test_acquired_only_display_has_separate_coverage_and_preserves_inputs(self):
        values = fixture()
        before = deepcopy(values[:5])
        rows = public_host_excerpts(*values)
        self.assertEqual(values[:5], before)
        self.assertEqual(len(rows), 1)
        # Delivery and legal-citation collections are deliberately not inputs.
        store = values[5]
        binding = {'status':'BOUND', 'document_id':'D1', 'unit_id':'10', 'blocks':[
            {'block_id':'10', 'start_cp':0, 'end_cp':len(store.text), 'text_sha256':text_hash(store.text)}]}
        self.assertEqual(target_coverage(binding, rows, store)['ratio'], 1)
        self.assertEqual(target_coverage(binding, [], store)['ratio'], 0)
        unavailable = target_coverage({'status':'MISSING_DOCUMENT'}, rows, store)
        self.assertIsNone(unavailable['ratio'])
        self.assertEqual(unavailable['status'], 'UNAVAILABLE_IN_FROZEN_CORPUS')

    def test_missing_or_unbound_committed_judgment_is_rejected(self):
        for index in (0, 1):
            with self.subTest(index=index):
                values = fixture()
                values[index] = None
                with self.assertRaisesRegex(ValueError, 'MISSING_COMMITTED_JUDGMENT'):
                    public_host_excerpts(*values)
        values = fixture()
        values[3]['case']['judgment_refs']['COMPOSE']['payload_hash'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'JUDGMENT_HASH_BINDING_MISMATCH'):
            public_host_excerpts(*values)

    def test_actual_public_answer_must_match_saved_text(self):
        values = fixture()
        values[2]['text'] = '다른 답변'
        with self.assertRaisesRegex(ValueError, 'PUBLIC_TEXT_BINDING_MISMATCH'):
            public_host_excerpts(*values)

    def test_rehashed_composition_cannot_omit_displayed_original(self):
        values = fixture()
        values[1]['text'] = values[2]['text'] = '원문 없는 답변'
        rebind(values)
        with self.assertRaisesRegex(ValueError, 'PUBLIC_EXCERPT_RENDER_MISMATCH'):
            public_host_excerpts(*values)

    def test_missing_or_denied_scope_is_rejected(self):
        for scope in (None, {'another-document'}):
            with self.subTest(scope=scope):
                values = fixture()
                values[-1] = scope
                with self.assertRaises(ValueError):
                    public_host_excerpts(*values)

    def test_acquisition_identity_and_version_must_match(self):
        for key, value in (('evidence_id','other-evidence'), ('source_id','other-source'),
                ('source_artifact_sha256','wrong-version')):
            with self.subTest(key=key):
                values = fixture()
                values[4][0][key] = value
                with self.assertRaises(ValueError):
                    public_host_excerpts(*values)

    def test_acquisition_gaps_cannot_be_filled_by_host_display(self):
        values = fixture()
        span = values[4][0]
        values[4][:] = [{**span, 'end_cp':2}, {**span, 'start_cp':3}]
        with self.assertRaisesRegex(ValueError, 'HOST_SPAN_NOT_EXACT_ACQUIRED_SOURCE'):
            public_host_excerpts(*values)

    def test_raw_source_or_span_hash_drift_is_rejected(self):
        values = fixture()
        values[5].text = 'X' + values[5].text[1:]
        with self.assertRaisesRegex(ValueError, 'HOST_SPAN_NOT_EXACT_ACQUIRED_SOURCE'):
            public_host_excerpts(*values)
        values = fixture()
        values[0]['source_excerpt_reply']['sources'][0]['span_receipts'][0]['text_hash'] = 'wrong-hash'
        rebind(values)
        with self.assertRaisesRegex(ValueError, 'HOST_SPAN_NOT_EXACT_ACQUIRED_SOURCE'):
            public_host_excerpts(*values)

    def test_legal_claims_cannot_be_counted_as_host_excerpts(self):
        values = fixture()
        values[0]['claims'] = [{'text':'법률 결론'}]
        rebind(values)
        with self.assertRaisesRegex(ValueError, 'INVALID_HOST_SOURCE_REPLY_CONTRACT'):
            public_host_excerpts(*values)


if __name__ == '__main__':
    unittest.main()
