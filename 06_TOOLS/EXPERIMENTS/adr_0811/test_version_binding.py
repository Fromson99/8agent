from copy import deepcopy
import pytest
from workflow.registry import Registry
from workflow.contracts import WorkflowError,request


def registered(*versions):
    r=Registry()
    for v in versions:r.register({'workflow_id':'risk_team_compare_workflow','version':v,'allowed_teams':['risk_team']},lambda:None)
    return r


def test_omitted_version_uses_unique_explicit_registration_and_unknown_is_not_substituted():
    r=registered('3.7.2')
    assert r.resolve('risk_team_compare_workflow',None,'risk_team').manifest['version']=='3.7.2'
    assert r.resolve('risk_team_compare_workflow','3.7.2','risk_team').manifest['version']=='3.7.2'
    with pytest.raises(WorkflowError):r.resolve('risk_team_compare_workflow','1.1.0','risk_team')
    with pytest.raises(WorkflowError):r.resolve('risk_team_compare_workflow',None,'other')


def test_multiple_registered_versions_require_explicit_choice():
    r=registered('1.2.0','2.0.0')
    with pytest.raises(WorkflowError) as e:r.resolve('risk_team_compare_workflow',None,'risk_team')
    assert e.value.code=='WORKFLOW_VERSION_REQUIRED'
    assert r.resolve('risk_team_compare_workflow','1.2.0','risk_team').manifest['version']=='1.2.0'


@pytest.mark.parametrize('version',[[],{},22,'latest','1.2'])
def test_invalid_version_is_rejected_at_ingress(version):
    principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
    with pytest.raises(WorkflowError):request({'question':'대사: 기준','session_id':'s','request_id':'r','workflow_version':version},principal)
