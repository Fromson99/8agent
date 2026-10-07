"""ADR-0465 candidate rev-001 deterministic parts (no model). Run with PYTHONDONTWRITEBYTECODE=1."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(ROOT / '02_BACKEND/lawrag/research/candidates/adr_0465/legal-agent/revisions/rev-001/snapshot/02_BACKEND'))
from legal_agent.contracts import EvidenceUnit
from legal_agent.citations import render
from legal_agent.checker import check
from legal_agent.composer import compose, NO_EVIDENCE, ledger_schema
from legal_agent.replay import load_run_case
from legal_agent.harness import TASK_TYPES, INVARIANTS

U = [EvidenceUnit('E1', 'a1', 'd1', '상법', '제628조(납입가장죄등)',
                  '①제622조제1항에 게기한 자가 납입 또는 현물출자의 이행을 가장하는 행위를 한 때에는 5년 이하의 징역 또는 1천500만원 이하의 벌금에 처한다.', 'law')]

def test_render_replaces_handles_with_labels_and_reports_unknown():
    text, cites, unknown = render('납입가장죄가 된다 [E1]. 형은 5년 이하 징역이다 [E1, E7].', U)
    assert '(상법 제628조)' in text and '[E' not in text and text.endswith('근거: 상법 제628조')
    assert [c['handle'] for c in cites] == ['E1'] and unknown == ['E7']
    assert cites[0]['text'].startswith('①제622조')

def test_checker_flags_numbers_missing_from_cited_source_only():
    ok = check('형은 5년 이하의 징역이다 [E1].', U, [])
    assert ok == []
    bad = check('형은 7년 이하의 징역이다 [E1]. 벌금은 1천500만원 이하다.', U, [])
    kinds = sorted(f.kind for f in bad)
    assert kinds == ['number_not_in_cited_source', 'uncited_number_sentence']

def test_no_evidence_makes_no_model_call():
    class Boom:
        def generate(self, *a, **k): raise AssertionError('called')
    assert compose(Boom(), 'q', [], mode='ledger', phase='p').answer == NO_EVIDENCE

def test_replay_keeps_only_public_origins(tmp_path):
    run = {'question': 'q', 'output': {'assembly': {'context': [
        {'id': 's1', 'document_id': 'pub', 'document_name': '상법', 'text': '제628조(납입가장죄등)\n①…'},
        {'id': 's2', 'document_id': 'int', 'document_name': '내부지침', 'text': '제1조(목적)\n…'},
        {'id': 's3', 'document_id': 'unk', 'document_name': '?', 'text': '제2조\n…'}]}}}
    p = tmp_path / 'run.json'; p.write_text(json.dumps(run, ensure_ascii=False))
    q, units, excluded = load_run_case(p, {'pub': 'law', 'int': 'internal'})
    assert [u.handle for u in units] == ['E1'] and units[0].label == '상법 제628조'
    assert [e['origin'] for e in excluded] == ['internal', 'unknown']

def test_prompt_rules_carry_no_golden_values():
    text = json.dumps([TASK_TYPES, INVARIANTS], ensure_ascii=False)
    for golden_value in ('3분의 1', '100분의 30', '100분의 10', '6개월'):
        assert golden_value not in text
    assert set(ledger_schema()['properties']) == {'task_types', 'ledger', 'answer'}
