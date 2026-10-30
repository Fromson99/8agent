"""Password gate for the temporary private review preview; no model operations."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import time

import streamlit as st
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    st.set_page_config(page_title='온톨로지 검토', layout='wide')
    try:
        credentials = json.loads(Path(os.environ['ONTOLOGY_REVIEW_CREDENTIALS']).read_text())
        salt = bytes.fromhex(credentials['salt'])
        expected = credentials['password_hash']
    except (KeyError, OSError, ValueError):
        st.error('접속 설정을 확인해 주세요.')
        return
    if not hmac.compare_digest(st.session_state.get('private_review_access', ''), expected):
        st.title('온톨로지 검토')
        st.caption('전달받은 비밀번호로 실제 숏컷 검토 화면에 접속하세요.')
        with st.form('private_review_login'):
            password = st.text_input('비밀번호', type='password')
            submitted = st.form_submit_button('화면 열기', type='primary')
        if submitted:
            if time.monotonic() < st.session_state.get('private_review_retry_at', 0):
                st.warning('잠시 후 다시 입력해 주세요.')
                return
            actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 210000).hex()
            if not hmac.compare_digest(actual, expected):
                st.session_state.private_review_retry_at = time.monotonic() + 2
                st.error('비밀번호를 다시 확인해 주세요.')
                return
            st.session_state.private_review_access = expected
            st.rerun()
        return
    # Never create the backend or load source data before authentication.
    from ontology_dashboard import render
    render()


if __name__ == '__main__':
    main()
