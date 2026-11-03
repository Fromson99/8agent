"""One authenticated entry to the existing review and authoring workflows."""
import hashlib
import json
import os
from pathlib import Path
import sys

import streamlit as st

PANELS = ['검토 대시보드', '자유 작업공간', '도메인 프로필·판단 축적', '시나리오 검증']


def load_backend():
    root = Path(os.environ.get('GENOS_ONTOLOGY_CODE_ROOT', Path(__file__).resolve().parents[3])).resolve()
    pointer = root / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    if not os.environ.get('GENOS_ONTOLOGY_CODE_ROOT') and pointer.is_file():
        active = json.loads(pointer.read_text())
        manifest_path = root / active['manifest_path']
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != active['release_manifest_sha256']:
            raise RuntimeError('Selected MAIN manifest changed')
        manifest = json.loads(manifest_path.read_text())
        code = root / manifest['code_root']
        for name, expected in manifest['files'].items():
            if hashlib.sha256((code/name).read_bytes()).hexdigest() != expected:
                raise RuntimeError('Selected MAIN code changed')
        root = code.resolve()
    loaded = sys.modules.get('semantic_runtime')
    if loaded and Path(loaded.__file__).resolve() != root/'02_BACKEND/semantic_runtime/__init__.py':
        raise RuntimeError('Console and backend code roots differ; restart the application')
    sys.path.insert(0, str(root/'02_BACKEND'))
    return root


def reset_identity(identity):
    previous = st.session_state.get('oc_identity')
    if previous != identity:
        # A change of user, grant or environment invalidates every pending edit
        # and publication receipt. Preserve only the separate login gate.
        if previous is not None:
            for key in list(st.session_state):
                if not key.startswith('private_review_'):
                    del st.session_state[key]
        st.session_state['oc_identity'] = identity


def render(*, embedded=False, initial_panel=None):
    factory = os.environ.get('GENOS_ONTOLOGY_HOST_FACTORY', '').strip()
    if factory:
        try:
            import importlib
            module, name = factory.split(':')
            host = getattr(importlib.import_module(module), name)
            with host():
                return _render(embedded=embedded, initial_panel=initial_panel)
        except Exception:
            from ontology_dashboard import failure
            failure('인증된 관리 연결 준비')
            return
    return _render(embedded=embedded, initial_panel=initial_panel)


def _render(*, embedded=False, initial_panel=None):
    try:
        root = load_backend()
        if os.environ.get('ONTOLOGY_DASHBOARD_DEMO') == '1':
            if os.environ.get('GENOS_RAG_ONTOLOGY_CONFIG'):
                raise RuntimeError('Demo and production settings must not be enabled together')
            reset_identity('demo:'+str(root))
            from ontology_dashboard import render as dashboard
            return dashboard(embedded=embedded)
        from semantic_runtime.ontology_work.configuration import settings, connection_status
        from semantic_runtime.ontology_work.ui import actor
        cfg = settings(); operator = actor()
        if operator not in cfg.get('operators', {}):
            raise PermissionError('Operator not authorized')
        identity = hashlib.sha256(json.dumps([str(root), operator, cfg], sort_keys=True).encode()).hexdigest()
        reset_identity(identity)
        status = connection_status(actor=operator)
    except Exception:
        from ontology_dashboard import failure
        failure('관리 화면 연결 확인')
        return
    st.caption(status['message'])
    key = 'oc_panel_simulation' if initial_panel == '시나리오 검증' else 'oc_panel'
    if key not in st.session_state:
        st.session_state[key] = initial_panel or PANELS[0]
    selected = st.radio('관리 작업', PANELS, horizontal=True, key=key)
    # Do not construct unused writers, dictionaries, models or tab contents.
    if selected == PANELS[0]:
        from ontology_dashboard import render as dashboard
        dashboard(embedded=embedded)
    elif selected == PANELS[1]:
        from semantic_runtime.ontology_work.wiki_ui import render as workspace
        workspace()
    elif selected == PANELS[2]:
        from semantic_runtime.ontology_work.domain_ui import render as domain
        domain()
    else:
        from semantic_runtime.ontology_work.ui import render as simulation
        simulation(simulation=True)


def main():
    st.set_page_config(page_title='온톨로지 관리', page_icon='✓', layout='wide')
    render()


if __name__ == '__main__':
    main()
