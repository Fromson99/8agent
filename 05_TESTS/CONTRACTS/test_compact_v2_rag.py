"""Local v6 RAG on compact-v2/unit FTS, with synthetic model transport."""
import json
import pytest
import test_structure_first_search as sources
import test_unified_legal_agent as cases
from test_unified_legal_agent import unified


@pytest.fixture
def structured_generation(tmp_path,term_glossary,monkeypatch):
    original=sources.build_generation
    def build(*args,**kwargs):
        return original(*args,**kwargs,storage_profile='compact-v2',fulltext_granularity='unit')
    monkeypatch.setattr(sources,'build_generation',build)
    base=cases.ScriptedTransport
    class UnitTransport(base):
        def send_once(self,*,body,ticket):
            view=json.loads(body['messages'][1]['content'])['view']
            phase=view.get('source_stage',view['phase'])
            if phase in ('source-unit-triage','source-unit-review'):
                self.phases.append(phase)
                choices=[]
                if phase=='source-unit-triage' and view['units']:
                    unit=view['units'][0]
                    choices=[{'id':unit['id'],'scope':unit['read_options'][0][0],'reason':'모의 원문 확인'}]
                return cases.wire({'issues':['승인'],'choices':choices,'needs_search':False})
            if phase.startswith('source-reference-batch'):
                self.phases.append(phase)
                from test_batch_reference_navigation import decision
                return cases.wire(decision(view))
            return super().send_once(body=body,ticket=ticket)
    monkeypatch.setattr(cases,'ScriptedTransport',UnitTransport)
    return sources.structured_generation.__wrapped__(tmp_path,term_glossary)


def test_new_storage_question_to_cited_answer(unified):
    cases.test_v6_returns_answer_without_assessment_or_composition_judge(unified)


def test_new_storage_correction_restore_and_reuse(unified):
    cases.test_u01_u02_full_question_correction_restore_confirmation_two_wikis_new_session(unified)


def test_new_storage_revoked_scope_hides_evidence(unified):
    cases.test_u09_revoked_document_scope_hides_history_and_experience(unified)
