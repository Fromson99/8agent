from pathlib import Path
import subprocess
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0772/provider-display';S=C/'snapshot'
p=R/'05_TESTS/CONTRACTS/test_workflow_source_cards.py';s=p.read_text().replace('workflow_source_cards_20261013_r1','workflow_source_provider_20261013_r2').replace('GENOS_WORKFLOW_SOURCE_CARDS_20261013_R1','GENOS_WORKFLOW_SOURCE_PROVIDER_20261013_R2')
s=s.replace('asyncio.run(d.progress(e))','async def run():\n        await d.progress(e)\n        await d._flush_source_reads()\n    asyncio.run(run())',1)
s=s.replace("assert text.count('\\n\\n- ') == 2", "assert '외부법률 / 법제처\\n\\n1. 모의법' in text\n    assert '외부법률 / 한국거래소\\n\\n1. 모의 시행세칙' in text")
s=s.replace("assert 'financial\\\\_team &gt; law &gt; 모의법' in text", "assert 'external' not in text and 'financial' not in text")
s=s.replace("assert 'financial_team &gt; law &gt; 모의법' in html", "assert html.count('<ol>') == 2")
s=s.replace("text.count('\\n\\n- ') == 21", "MarkdownIt().render(text).count('<li>') == 21")
s=s.replace('assert all(view._ChatProgress._plain(row) in text for row in rows)', 'assert all(view._ChatProgress._plain(row.rsplit(" > ", 1)[-1]) in text for row in rows)')
s=s.replace("asyncio.run(d.progress(event('candidate', 'LAW_FULLTEXT_DIRECTORY', [row])))", "async def run():\n        await d.progress(event('candidate', 'LAW_FULLTEXT_DIRECTORY', [row]))\n        await d._flush_source_reads()\n    asyncio.run(run())")
s=s.replace('genos_source_cards_handoff.py','genos_source_provider_handoff.py').replace('text, _ = module.build()',"text, _ = module.build(ROOT / '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py')")
s+='''\n\n@pytest.mark.parametrize('key', ['LAW_DECISION_REJECTED', 'MODEL_OUTPUT_INVALID', 'COMPLETION_ASSESSMENT_REJECTED', 'OBS_EVENT'])
def test_private_errors_do_not_flush_groups_or_reach_public_flow(view, key):
    d, sent = recorder(view)
    raw = event('decision', key, ['PRIVATE_TRACEBACK duplicate branch or missing reason'], label='실행 오류')
    raw['basis']['detail_mode'] = 'full_error'
    async def run():
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['external/krx/규정A']))
        await d.progress(raw)
        assert not sent and not d.blocks
        await d.progress(event('reading', 'UNIT_READ_STARTED', ['external/krx/규정B']))
        await d.finish('완료')
    asyncio.run(run())
    assert 'PRIVATE_TRACEBACK' not in json.dumps([sent,d.blocks,d.flow_events])
    assert len(d.blocks) == 1 and '2곳' in content(d.blocks[0])
    assert raw['details'][0].startswith('PRIVATE_TRACEBACK')  # diagnostic input retained
    assert '조회 번호: r-1' in view.render_error({'request_id':'r-1','traceback':raw['details'][0]})


def test_candidate_chunks_and_request_boundaries(view):
    d, _ = recorder(view)
    async def run():
        for i in range(19):
            e = event('candidate', 'LAW_FULLTEXT_DIRECTORY', [f'external > financial_team > krx > 규정{i}'])
            e['basis']['journal_seq'] = 3
            await d.progress(e)
        e = event('candidate', 'LAW_FULLTEXT_DIRECTORY', ['external/kofia/협회규정'])
        e['basis']['journal_seq'] = 4
        await d.progress(e)
        await d.finish('완료')
    asyncio.run(run())
    assert len(d.blocks) == 2
    assert content(d.blocks[0]).count('외부법률 / 한국거래소') == 1
    assert MarkdownIt().render(content(d.blocks[0])).count('<li>') == 19
    assert '19. 규정18' in content(d.blocks[0])
    assert '외부법률 / 한국금융투자협회' in content(d.blocks[1])


def test_unknown_provider_internal_and_duplicate_titles_are_not_mislabelled(view):
    d,_=recorder(view)
    rows=['external/team/unknown/규정A','internal/team/사규B',
          'external/law/동일명','external/krx/동일명','external/kofia/<img src=x> **위험**']
    text=d._card_rationale('검색',rows)
    assert '외부법률 / 기타 출처' in text and '내부규정' in text
    assert text.count('1. 동일명') == 2
    assert all(x not in text for x in ['external','internal','unknown','<img'])
    html=MarkdownIt().render(text)
    assert '<img' not in html and '<strong>' not in html


def test_committed_judgment_survives_privacy_filter(view):
    d,_=recorder(view)
    e=event('decision','CASE_JUDGMENT_ACCEPTED',['현재 판단: 확인한 원문에 근거한 판단'])
    e['basis'].update(detail_mode='judgment',state='COMPLETED')
    asyncio.run(d.progress(e))
    assert d.blocks and any('확인한 원문' in str(x) for x in d.flow_events)
'''
(S/'05_TESTS/CONTRACTS').mkdir(parents=True,exist_ok=True)
(S/'05_TESTS/CONTRACTS/test_workflow_source_cards.py').write_text(s)
s=(R/'05_TESTS/CONTRACTS/test_main_workflow_display.py').read_text().replace('rag-source-cards-20261013-r1','rag-source-provider-20261013-r2');(S/'05_TESTS/CONTRACTS/test_main_workflow_display.py').write_text(s)
for name in ['test_main_source_cards.py']:(S/'05_TESTS/CONTRACTS'/name).write_bytes((R/'05_TESTS/CONTRACTS'/name).read_bytes())
for name in ['test_workflow_source_cards.py','test_main_workflow_display.py','test_main_source_cards.py']:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target','05_TESTS/CONTRACTS/'+name,'--upstream-state','present'],check=True,stdout=subprocess.DEVNULL)
p=R/'06_TOOLS/EXPERIMENTS/adr_0772/run_tests.py';s=(R/'06_TOOLS/EXPERIMENTS/adr_0771/run_tests.py').read_text().replace("'test_genos_answer_stream')", "'test_genos_answer_stream','test_workflow_source_cards')");p.write_text(s)
s=(R/'06_TOOLS/EXPERIMENTS/adr_0771/freeze_code.py').read_text().replace('0771','0772').replace('source-cards-main-wiring','source-provider-display').replace('source-cards','provider-display')
# No backend engine or pipeline edits: preserve exact selected MAIN57 bytes.
beg=s.index('for p in (S/');end=s.index('subprocess.run',beg);s=s[:beg]+s[end:]
(R/'06_TOOLS/EXPERIMENTS/adr_0772/freeze_code.py').write_text(s)
