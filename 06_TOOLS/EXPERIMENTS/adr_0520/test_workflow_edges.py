"""Ensure server tasks continue linked reverse/forward references beyond the root."""
from conftest import term_glossary
from test_document_release import source
from test_legal_agent_v5 import session
from test_tool_exploration_v3 import read
from lawrag.pipeline.term_generation import build_generation

def test_system_tasks_continue_forward_and_reverse_at_linked_sources(tmp_path,term_glossary):
    raw=source(tmp_path/'raw.sqlite',[('d','모의승인규정',[
        '제2조를 준용한다.', '제3조를 준용한다.', '승인 조건을 따른다.',
        '제2조에 따라 위임한다.', '제4조에 따라 승인한다.'])])
    build_generation(raw,term_glossary,tmp_path/'built',serving=True)
    with session(tmp_path,tmp_path/'built/generation') as s:
        r=read(s)
        assert r['status']=='OK'
        headings={s.sources.tools.sources[e['source_id']]['heading'] for e in s.work.evidence()}
        assert all(any(h.startswith(f'제{i}조') for h in headings) for i in range(1,6)),headings
        rows=s.work.db.execute('SELECT automatic_depth FROM evidence_origin').fetchall()
        assert max(r[0] for r in rows)>=3
        assert not [r for r in s.sources.action_summaries() if r['status']=='ERROR']
