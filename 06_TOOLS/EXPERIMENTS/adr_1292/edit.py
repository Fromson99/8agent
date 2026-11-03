from common import *
S=ROOT/read(DES/'candidate-path.json')['snapshot']
def edit(name,old,new):
 p=S/name;s=p.read_text();assert old in s,name;p.write_text(s.replace(old,new))
cfg='02_BACKEND/semantic_runtime/ontology_work/configuration.py'
edit(cfg,'import os,json,sqlite3','import os,json,sqlite3\nfrom contextlib import contextmanager\nfrom contextvars import ContextVar\n\n_AUTHORING = ContextVar("ontology_authoring", default=None)')
edit(cfg,'def workflow(*,actor):\n', '''def _ports(actor):
    bound = _AUTHORING.get()
    if bound is None:
        return {}
    if bound['actor'] != actor or bound['config'] != settings():
        raise ContractError('authoring context identity or configuration changed')
    return bound


@contextmanager
def authoring_context(*, actor, workflow, glossary_factory, config, runtime_probe=None):
    """Trusted host ports for one authenticated render; never browser arguments.

    The host owns its database connections. Each glossary factory call returns
    a fresh binding whose reader is closed by its consumer. No global caching.
    """
    from copy import deepcopy
    if config != settings() or actor not in config.get('operators', {}) or workflow.actor != actor:
        raise ContractError('authoring context identity or configuration mismatch')
    grant = config['operators'][actor]
    if not grant.get('document_ids') or not callable(glossary_factory):
        raise ContractError('authoring document scope and glossary factory required')
    selected = config.get('domain_profile')
    workspace = config.get('workspace') or selected
    if not selected or not workspace or any(workspace.get(k) != selected.get(k) for k in ('namespace','source_snapshot','acl_ref')):
        raise ContractError('authoring workspace and domain scope mismatch')
    if any(not selected.get(k) for k in ('namespace','source_snapshot','acl_ref')):
        raise ContractError('authoring namespace snapshot ACL required')
    token = _AUTHORING.set({'actor':actor, 'config':deepcopy(config), 'workflow':workflow,
        'glossary_factory':glossary_factory, 'runtime_probe':runtime_probe})
    try:
        yield
    finally:
        _AUTHORING.reset(token)


def connection_status(*, actor):
    """Report a checked reader separately from the operator's writer settings."""
    cfg = settings()
    if actor not in cfg.get('operators', {}):
        raise ContractError('operator is not authorized for ontology review')
    ports = _ports(actor)
    probe = ports.get('runtime_probe')
    if probe is None:
        return {'status':'UNVERIFIED', 'message':'관리 저장소 설정됨 · 현재 RAG 읽기 연결은 확인 전입니다.'}
    result = probe()
    if not isinstance(result, dict) or result.get('status') not in ('OFF','NO_SCOPE','EMPTY','READY'):
        raise ContractError('runtime readiness result invalid')
    messages = {'OFF':'현재 RAG의 온톨로지 사용이 꺼져 있습니다.',
        'NO_SCOPE':'현재 RAG에 이 작업공간의 읽기 범위가 등록되지 않았습니다.',
        'EMPTY':'현재 RAG 읽기 범위에 사용할 수 있는 게시본이 없습니다.',
        'READY':'현재 RAG의 게시본 읽기·원문 대조를 확인했습니다.'}
    return {'status':result['status'], 'message':messages[result['status']]}


def workflow(*,actor):
    bound = _ports(actor)
    if bound:
        return bound['workflow']
''')
edit(cfg,"    from ..full_glossary import Glossary",'''    bound = _AUTHORING.get()
    if bound:
        checked = _ports(bound['actor'])
        if config != checked['config']:
            raise ContractError('glossary authoring configuration mismatch')
        port = checked['glossary_factory']()
        if port.snapshot != config['domain_profile']['source_snapshot']:
            port.reader.close()
            raise ContractError('glossary authoring snapshot mismatch')
        return port
    from ..full_glossary import Glossary''')
front='03_FRONTEND/APPS/legal-knowledge-streamlit/'
edit(front+'ontology_app.py','from ontology_dashboard import main','from ontology_console import main')
edit(front+'ontology_private_app.py','from ontology_dashboard import render','from ontology_console import render')
edit(front+'app.py',"from ontology_dashboard import render\n        return render(embedded=True, initial_page='검토 대시보드')",'from ontology_console import render\n        return render(embedded=True)')
edit(front+'app.py','from semantic_runtime.ontology_work.ui import render\n        return render(simulation=True)',"from ontology_console import render\n        return render(embedded=True, initial_panel='시나리오 검증')")
edit(front+'ontology_dashboard.py',"    st.set_page_config(page_title='기록에서 승인까지', page_icon='✓', layout='wide', initial_sidebar_state='collapsed')\n    render()",'    from ontology_console import main as console_main\n    console_main()')
calc='02_BACKEND/semantic_runtime/legal_agent/scenario_computation.py'
edit(calc,"            if 'computed_gap_ref' not in row:\n                continue",'''            if 'computed_gap_ref' not in row:
                if any(ref in row.get('reason', '') for ref in options):
                    raise output.OutputContractError(
                        '미확인 입력 ID는 이유문에 쓰지 말고 computed_gap_ref와 issue_id 필드로 선택하세요. 원래 설명은 원제안에 보존됩니다.',
                        [output.issue('COMPUTED_GAP_IN_REASON', '/gaps/'+str(index)+'/reason')],
                        category='SCENARIO_REVIEW_INVALID')
                continue''')
rev='02_BACKEND/semantic_runtime/legal_agent/review_explanation.py'
edit(rev,"            reason += ' 조사 당시 확인 목적(이력): ' + declaration", "            if not assessment.get('scenario_calculation'):\n                reason += ' 조사 당시 확인 목적(이력): ' + declaration")
edit(rev,"'claim_refs': deepcopy(final.get('claim_refs', []))})", "'claim_refs': deepcopy(final.get('claim_refs', [])),\n            **({'historical_declaration': declaration} if assessment.get('scenario_calculation') and declaration else {})})")
edit(rev,"        'SCENARIO_REVIEW_SHAPE':", "        'COMPUTED_GAP_IN_REASON':'미확인 입력이 설명문에만 적혀 있어 구조화된 입력 연결을 완료하지 못했습니다.',\n        'SCENARIO_REVIEW_SHAPE':")
render='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
p=S/render;s=p.read_text();pos=s.index("    return",s.index('def _review_explanation_text'))
print('render function must be inspected before changing',s[s.index('def _review_explanation_text'):s.index('def _review_explanation_text')+2400])
print('core edits written')
