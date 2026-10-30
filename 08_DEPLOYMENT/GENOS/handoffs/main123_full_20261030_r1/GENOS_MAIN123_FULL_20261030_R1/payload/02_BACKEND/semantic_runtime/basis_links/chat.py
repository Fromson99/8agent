"""Explicit basis-link AD actions; approval is never inferred by an LLM."""
import re
from .contracts import require,digest


def handle(service,who,body,*,active):
    if not active:return None
    text=body.get('question',body.get('q','')).strip()
    session=body.get('ad_session_id') or body.get('session_id')
    require(isinstance(session,str) and session,'BASIS_SESSION','승인 화면을 연결할 세션이 필요합니다.')
    key=digest(['basis-chat',who['team_id'],who['user_id'],session])
    # Current view is session state, stored as immutable sequence receipts;
    # selection never resolves a row against a different user's last screen.
    if text in ('근거 관계 목록','근거 연결 목록','basis_link 목록'):
        request_key=service._receipt_key(who,'chat-list',body.get('request_id'));ih=digest([session,text])
        with service.repo.transaction():
            prior=service.repo.receipt(request_key,ih)
            if prior:
                # A repeated display gets current authority but does not replace
                # a newer row selection context.
                pass
        view=service.view(who)
        if prior is None:
            with service.repo.transaction():
                if service.repo.receipt(request_key,ih) is None:
                    service.repo.save_receipt(request_key,ih,{'view_id':view['view_id']})
                    service.repo.set_view_head(key,{'view_id':view['view_id']})
        lines=['근거 관계 목록','', '| 번호 | 내규 | 외규 | 승인 | 위치 |','|---|---|---|---|---|']
        from html import escape
        def cell(x):return escape(str(x)).replace('|','\\|').replace('\n',' ')
        for n,row in enumerate(view['items'],1):
            ends=row['binding'] or row['link']
            lines.append('| '+' | '.join(cell(x) for x in [n, '; '.join(e['document_name']+' '+e['title'] for e in ends['internal']),'; '.join(e['document_name']+' '+e['title'] for e in ends['external']),row['link']['status'],row['current_status']])+' |')
        lines+=['','행 번호로 승인·반려·취소할 수 있습니다. 예: 1번 승인. 원문·이력 및 관계 수정은 /basis/ 화면에서 확인합니다.']
        return {'response_schema':'ad-mode-v1','ad_mode':True,'answer_status':'administration','text':'\n'.join(lines),'basis_links':view}
    current=service.repo.view_head(key)
    if current is None or not current.get('view_id'):return None
    if not re.fullmatch(r'\s*\d+(?:\s*[,、]\s*\d+)*\s*번?\s*(승인|반려|취소)\s*',text) and text not in ('이 연결 맞아','이 연결 승인'):
        # Another AD command changes the active object. Never apply its later
        # row number to a lingering basis table.
        with service.repo.transaction():service.repo.set_view_head(key,{'view_id':None})
        return None
    result=service.review_view(who,{'request_id':body.get('request_id'),'view_id':current['view_id'],'text':text})
    return {'response_schema':'ad-mode-v1','ad_mode':True,'answer_status':'administration','text':'근거 관계 처리 결과: '+result['status'],'basis_review':result}


def active_context(path,workspace,channel,chat):
    from ..ad_store import fingerprint
    from ..state_sqlite import readonly
    if not path.exists():return False
    db=readonly(path)
    try:
        if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ad_session'").fetchone():return False
        row=db.execute('SELECT enabled,pending_action FROM ad_session WHERE id=?',(fingerprint([workspace,channel,chat]),)).fetchone()
        return bool(row and row[0] and row[1]=='basis_link')
    finally:db.close()
