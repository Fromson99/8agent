"""r8 (ADR-1519): the relation store is loaded under the release package name, so its BasisError is not the class
the capture code imported. A rejected candidate must still be recorded and left out (not stop the 대사), an
unavailable store must still mean 'pending', and a 409 ledger error must still stay an error."""
from semantic_runtime.basis_links.integration import finish_workflow

import test_compare_pairing_input as pairing


class BasisError(ValueError):
    """Same name, other module: as the release-loaded store raises it."""

    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, status


class BasisUnavailable(BasisError):
    def __init__(self):
        super().__init__('BASIS_UNAVAILABLE', '승인 관계 저장소를 사용할 수 없습니다.', 503)


class ForeignStore(pairing.FakeRelationStore):
    def __init__(self, log, error):
        super().__init__(log)
        self.error = error

    def propose(self, who, body):
        self.log.append('propose')
        raise self.error


def ctx(log, state, error):
    value = pairing.relation_ctx(log, state)
    value.rag.port.services.pipeline.basis_factory = ForeignStore(log, error)
    return value


def pairs():
    return {'basis': {'pairs': [{'pair_id': 'P1', 'basis_relation': 'DIRECT', 'internal': ['E1'], 'external': ['E2'],
                                 'reason': '관계', 'basis_path': []}]}}


def test_a_store_rejection_from_another_package_is_recorded_not_a_stop():
    log, state = [], pairs()
    value = finish_workflow(ctx(log, state, BasisError('BASIS_INPUT', '양쪽 원문 선택이 필요합니다.')),
                            {'status': 'complete', 'answer': {'text': '답'}})
    assert log == ['propose'] and value['answer']['text'] == '답'
    assert state['basis_capture_rejected'][0]['code'] == 'BASIS_INPUT' and state['basis_capture_complete'] is True


def test_an_unavailable_store_from_another_package_is_pending():
    log, state = [], pairs()
    value = finish_workflow(ctx(log, state, BasisUnavailable()), {'status': 'complete', 'answer': {'text': '답'}})
    assert value['basis_capture_status'] == 'pending' and value['basis_capture_error'] == 'BasisUnavailable'
    assert not state.get('basis_capture_complete')


def test_other_errors_are_not_taken_for_basis_errors():
    from semantic_runtime.basis_links.integration import is_basis_error
    assert is_basis_error(BasisError('X', 'y')) and is_basis_error(BasisUnavailable(), 'BasisUnavailable')
    assert not is_basis_error(ValueError('x')) and not is_basis_error(BasisError('X', 'y'), 'BasisUnavailable')
    from workflow.runtime import kept
    from workflow.contracts import WorkflowError
    assert kept(BasisError('BASIS_LEDGER', '무결성', 409), WorkflowError) is True
    assert kept(BasisError('BASIS_INPUT', '입력', 422), WorkflowError) is False
