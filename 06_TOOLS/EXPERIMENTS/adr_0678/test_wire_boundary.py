"""Declared T10: adapter format errors must retain their model-output class."""
import pytest
from test_investigation_completion_adr0678 import tree,session,inv_for
from semantic_runtime.legal_agent import completion_contracts as cc
from semantic_runtime.legal_agent.errors import ProposalError


def test_truncated_success_response_is_format_error_not_transport(session,monkeypatch):
    native,_=session;inv_for(native)
    class ExperimentFormatError(RuntimeError):
        response={'status_code':200,'body_json':{'choices':[{'finish_reason':'length','message':{'content':'{"ok":'}}]}}
    ExperimentFormatError.response['body_json']['model']=native.gateway.transport.binding['model']
    def send_once(**kwargs):raise ExperimentFormatError('Incomplete or blocked response')
    monkeypatch.setattr(native.gateway.transport,'send_once',send_once)
    with pytest.raises(ProposalError):
        native.structured('synthetic',{},cc.obj({'ok':{'type':'boolean'}}),'memory-assess',30)
