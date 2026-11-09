"""Which internal document the user means, without a model call.

Only names registered in the selected catalogue are matched. A number answer
refers to the candidates this server showed earlier in the same session; the
record is bound to the principal, session and the candidate list it showed.
"""
import json
import re
from ..contracts import WorkflowError, digest

RECORD = 'document-compare-session-v1'
CONTINUE = re.compile(r'^\s*(계속|이어서|계속\s*진행|계속해\s*(줘|주세요)?|이어서\s*(해\s*줘|진행|해주세요)?)\s*[.!]?\s*$')
NUMBER = re.compile(r'^\s*(\d{1,3})\s*번?\s*[.!]?\s*$')
MAX_CANDIDATES = 50


def internal_documents(port):
    from semantic_runtime.comparison_research_bridge import document_names
    rows = []
    for did in port.all_scope:
        if port.categories[did] != 'internal':
            continue
        names = document_names(port.session, did)
        rows.append({'document_id': did, 'name': names[0] if names else did})
    return sorted(rows, key=lambda r: (r['name'], r['document_id']))


def named(port, text):
    """Registered internal document names occurring in the text (longer name wins)."""
    from semantic_runtime.comparison_research_bridge import preferred_documents
    return preferred_documents(port, text, 'internal')


def _path(ctx):
    key = digest([ctx.request['principal'], ctx.request['session_id'], RECORD])[:32]
    return ctx.rag.port.services.runtime / 'workflows' / 'document-sessions' / (key + '.json')


def load(ctx):
    path = _path(ctx)
    if not path.is_file():
        return {}
    saved = json.loads(path.read_text('utf-8'))
    value = saved.get('value') or {}
    if (saved.get('schema_version') != RECORD or digest(value) != saved.get('hash')
            or value.get('principal') != ctx.request['principal'] or value.get('session_id') != ctx.request['session_id']):
        raise WorkflowError('DOCUMENT_SESSION_INTEGRITY', '이 대화의 문서 대사 기록을 확인할 수 없습니다.', 409)
    return value


def save(ctx, **changes):
    value = {**load(ctx), **changes, 'principal': ctx.request['principal'], 'session_id': ctx.request['session_id']}
    path = _path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'schema_version': RECORD, 'value': value, 'hash': digest(value)},
                               ensure_ascii=False, sort_keys=True), 'utf-8')
    return value


def decide(ctx, question):
    """Return ('document', row) | ('continue', last_run) | ('ask', candidates, reason)."""
    port = ctx.rag.port
    allowed = {r['document_id']: r for r in internal_documents(port)}
    if not allowed:
        return ('ask', [], '이 팀에 허용된 내규 문서가 등록되어 있지 않습니다.')
    if CONTINUE.match(question):
        last = load(ctx).get('last_run')
        if not last:
            return ('ask', [], '이 대화에서 이어 갈 문서 대사가 없습니다. 대사할 내규 문서 이름으로 시작해 주세요.')
        if last['document_id'] not in allowed:
            raise WorkflowError('WORKFLOW_SCOPE_DENIED', '이어 갈 문서의 접근권한이 없습니다.', 403)
        return ('continue', last)
    number = NUMBER.match(question)
    if number:
        record = load(ctx)
        shown = record.get('candidates') or []
        index = int(number.group(1))
        if not shown:
            return ('ask', list(allowed.values())[:MAX_CANDIDATES], '번호로 고를 후보 목록이 없습니다. 아래에서 번호를 다시 골라 주세요.')
        if digest(shown) != record.get('candidates_hash'):
            raise WorkflowError('DOCUMENT_SESSION_INTEGRITY', '이전에 보여 드린 후보 목록을 확인할 수 없습니다.', 409)
        if not 1 <= index <= len(shown):
            return ('ask', shown, '%d번은 후보 목록에 없습니다. 1~%d 중에서 골라 주세요.' % (index, len(shown)))
        chosen = shown[index - 1]
        if chosen['document_id'] not in allowed:
            raise WorkflowError('WORKFLOW_SCOPE_DENIED', '고른 문서의 접근권한이 없습니다.', 403)
        return ('document', allowed[chosen['document_id']])
    found = named(port, question)
    if len(found) == 1:
        return ('document', allowed[found[0]])
    if found:
        return ('ask', [allowed[d] for d in found], '질문에 여러 내규 이름이 있습니다. 대사할 문서를 번호로 골라 주세요.')
    rows = list(allowed.values())
    return ('ask', rows[:MAX_CANDIDATES], '질문에서 등록된 내규 이름을 찾지 못했습니다. 대사할 문서를 번호로 골라 주세요.'
            + (' (후보가 많아 앞의 %d개만 보여 드립니다. 문서 이름으로 다시 물어도 됩니다.)' % MAX_CANDIDATES
               if len(rows) > MAX_CANDIDATES else ''))
