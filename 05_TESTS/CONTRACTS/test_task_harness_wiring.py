"""Synthetic HTTP wiring through the real source/glossary/index and answer ports."""
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from lawrag.pipeline.term_generation import build_generation
from semantic_runtime.app import create_app
from semantic_runtime.contracts import Contracts, sha
from semantic_runtime.provider import Haiku
from semantic_runtime.task_harness_agent import ServingTaskHarnessAgent
from semantic_runtime import pipeline as pipeline_module, task_policy
from test_document_release import source
from test_task_harness import action

ROOT = Path(__file__).resolve().parents[2]


class Provider(Haiku):
    def __init__(self, output):
        super().__init__(ROOT, output, False, backend='fixture', trust_zone='internal')
        self.calls = 0
        self.verdict = 'SUPPORTED'

    def call(self, role, prompt, data, schema):
        self.calls += 1
        if role == 'task_interpret':
            q = data['question']
            result = {'task_type': 'definition_scope', 'concepts': [
                {'start': 0, 'end': len(q), 'text': q, 'label': '영업일'}], 'question_for_user': ''}
        elif role == 'task_evidence_review':
            result = {'verdict': self.verdict, 'scope_checked': True, 'limitations': [], 'reason': '모의 계약 확인'}
        else:
            concepts = data['task_state']['concepts']
            if not all('definitions' in c for c in concepts):
                actions = [action('OPEN_TERM', term_id=c['term']['id']) for c in concepts if 'definitions' not in c][:4]
            elif any(c['status'] == 'uncertain' for c in concepts):
                actions = [action('CONCEPT', term_id=c['term']['id'], status='selected' if i == 0 else 'rejected')
                           for i, c in enumerate(concepts) if c['status'] == 'uncertain'][:4]
            elif not data['active_segments'] and not data['judgments']:
                previous = [r for r in data['last_results'] if r['tool'] == 'LIST']
                if previous:
                    actions = [action('READ', source_id=previous[0]['result']['items'][0]['id'])]
                else:
                    actions = [action('LIST', term_ids=[concepts[0]['term']['id']])]
            elif data['active_segments']:
                s = data['active_segments'][0]
                actions = [action('JUDGE', segment_id=s['id'], issue_id=ident, status='adopted',
                                  quote=s['text'], claim='모의 영업일 정의와 적용 범위 설명')
                           for ident in data['issues']]
            else:
                sufficient = self.verdict == 'SUPPORTED'
                actions = [action('STOP', status='sufficient' if sufficient else 'incomplete',
                                  unresolved=[] if sufficient else ['근거 검토 미확인'])]
            result = {'actions': actions}
        return result, self.record_local({'fixture': True, 'role': role})


def test_http_candidate_binding_answer_feedback_and_journal(tmp_path, term_glossary, monkeypatch):
    raw = source(tmp_path/'source.sqlite', [('synthetic:v1', '가상법', [
        '영업일은 은행이 영업하는 날이다. 이 규정의 업무에 적용하며 휴일은 제외한다.'])])
    build_generation(raw, term_glossary, tmp_path/'built', serving=True)
    generation = tmp_path/'built/generation'
    db = generation/'task-policy.sqlite'
    proposed = task_policy.propose_definition(db, task_policy.DEFAULT)
    review = task_policy.review_definition(db, 'definition_scope', 1, 'test fixture', 'synthetic wiring only')
    binding = {**{k: proposed[k] for k in ('id', 'version', 'definition_sha256')},
               'path': db.name, 'sha256': sha(db), 'review_sha256': review['review_sha256']}

    class CandidateContracts(Contracts):
        def __init__(self, root):
            super().__init__(root)
            config = self.pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']
            config.update(implementation=task_policy.VERSION, task_policy=binding)

    monkeypatch.setattr(pipeline_module, 'Contracts', CandidateContracts)
    provider = Provider(tmp_path/'provider')
    app = create_app(tmp_path, generation, contracts_root=ROOT, provider=provider)
    with TestClient(app) as client:
        assert isinstance(app.state.pipeline.term_agent, ServingTaskHarnessAgent)
        assert client.get('/health').json()['rag_mode'] == task_policy.VERSION
        q = {'question': '은행이 문을 여는 날의 개념과 범위를 설명해 주세요.', 'document_ids': ['synthetic:v1']}
        result = client.post('/v1/rag/ask', json=q)
        assert result.status_code == 200, result.text
        run = result.json()
        state = run['retrieval']['term_agent']
        assert state['status'] == 'FINISH', state
        assert run['answer']['claims'] and not run['answer']['unresolved']
        assert state['task_spec']['definition_binding'] == binding
        assert run['query']['id'] == state['task_spec']['provenance']['query_id']
        assert run['answer']['source_store_sha256'] == state['task_spec']['provenance']['source_store_sha256']
        assert client.post('/v1/rag/feedback', json={
            'run_id': run['run_id'], 'signal': 'MISSING_EVIDENCE', 'reason': 'synthetic fixture'}).status_code == 200
        assert client.post('/v1/rag/ask', json={**q, 'document_ids': ['outside']}).status_code == 422
        provider.verdict = 'UNKNOWN'
        partial = client.post('/v1/rag/ask', json=q).json()
        assert partial['retrieval']['term_agent']['status'] == 'STOP'
        assert not partial['answer']['claims'] and partial['answer']['unresolved']
        before = provider.calls
        metadata = client.post('/v1/rag/ask', json={**q, 'use_llm': False}).json()
        assert metadata['retrieval']['term_agent']['status'] == 'METADATA_ONLY'
        assert not metadata['answer']['claims'] and provider.calls == before
    with sqlite3.connect(app.state.pipeline.task_harness_journal) as journal:
        payload = json.loads(journal.execute('SELECT payload FROM checkpoint WHERE run_id=? ORDER BY seq DESC LIMIT 1',
                                            (run['query']['id'],)).fetchone()[0])
        assert payload['task_state']['phase'] == 'COMPLETED'
        proposal = json.loads(journal.execute('SELECT payload FROM proposal WHERE run_id=?',
                                             (partial['query']['id'],)).fetchone()[0])
        assert proposal['question_span']['text'] == q['question']
        assert proposal['status'] == 'PROPOSED' and proposal['canonical_approval'] is False
