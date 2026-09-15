"""Synthetic functionality only. No real model, deployment or corpus mutation."""
import copy
import io
import json
from pathlib import Path

import pytest

from .test_genos_build import Fake, setup, XML
from .test_genos_staged import StagedFake
from lawrag.pipeline import genos_build as build, genos_stages as stages
from lawrag.pipeline.genos_progress import Progress, reason
from lawrag.pipeline.genos_raw_move import move, rebase


class PhaseFake(StagedFake):
    def prepare_kind(self, kind):
        self.kind = kind
        self.models = {kind: self.models[kind]}
        self.targets = {kind: self.targets[kind]}
        return self.prepare()


def invoke(args, raw, data, stage, run='one'):
    args.extraction_mode = 'staged'
    progress = Progress(data / 'LOGS' / run, io.StringIO())
    try:
        return stages.execute(build.inventory(raw, 'internal'), args, data, run, stage,
                              provider_factory=PhaseFake, progress=progress, dependencies={'test': 'v1'})
    finally:
        progress.close()


def test_phase_major_then_reuse_new_run(setup, monkeypatch):
    args, raw, out = setup
    (raw / 'two.xml').write_text(XML.replace('가상규정', '두번째규정'))
    data = out.parent / 'canonical'
    calls = []
    original = build.ingest_files
    def ingest(*a, **kw):
        assert not Fake.instances  # BOTH documents parse before any model connection.
        calls.append('parse')
        return original(*a, **kw)
    monkeypatch.setattr(build, 'ingest_files', ingest)
    result = invoke(args, raw, data, 'all')
    assert result['ok'], result
    assert len(calls) == 2 and result['passed'] == 2
    assert [x.kind for x in Fake.instances] == ['llm', 'llm', 'embed', 'embed']
    assert all(not p.batches for p in Fake.instances if p.kind == 'llm')
    assert all(not p.calls for p in Fake.instances if p.kind == 'embed')
    assert len(list((data / 'VECTOR').rglob('generation/manifest.json'))) == 2
    assert not list((data / 'LLM').rglob('structure/result.json'))
    args.max_tokens += 10  # A new model run may change tokens without re-parsing.
    assert invoke(args, raw, data, 'all', run='two')['ok']
    assert len(calls) == 2


def test_separate_phases_and_resume(setup, monkeypatch):
    args, raw, out = setup
    data = out.parent / 'canonical'
    assert invoke(args, raw, data, 'structure')['ok']
    assert not Fake.instances
    monkeypatch.setattr(build, 'ingest_files', lambda *a, **kw: pytest.fail('unexpected reparse'))
    assert invoke(args, raw, data, 'llm')['ok']
    assert [p.kind for p in Fake.instances] == ['llm']
    assert invoke(args, raw, data, 'vector')['ok']
    assert Fake.instances[-1].kind == 'embed' and not Fake.instances[-1].calls
    assert invoke(args, raw, data, 'llm')['ok']
    assert not Fake.instances[-1].calls  # Completed queue reused.
    assert invoke(args, raw, data, 'vector')['ok']
    assert not Fake.instances[-1].batches


def test_no_implicit_extract_and_cache_tamper(setup):
    args, raw, out = setup
    data = out.parent / 'canonical'
    assert not invoke(args, raw, data, 'llm')['ok']
    assert not Fake.instances
    assert invoke(args, raw, data, 'structure')['ok']
    source = next((data / 'STRUCTURE').glob('*/authoring-source.sqlite'))
    with source.open('ab') as f:
        f.write(b'tampered')
    assert not invoke(args, raw, data, 'llm')['ok']
    assert not Fake.instances


def test_cache_key_invalidation(setup):
    args, raw, out = setup
    plan = build.inventory(raw, 'internal')
    row = plan['files'][0]
    key = stages.structure_key(row, plan, {'version': 1})
    assert key != stages.structure_key(row, plan, {'version': 2})
    assert key != stages.structure_key({**row, 'sha256': 'changed'}, plan, {'version': 1})
    assert key != stages.structure_key({**row, 'engine': 'docxstyle'}, plan, {'version': 1})


class Terminal(io.StringIO):
    def isatty(self):
        return True


def test_live_line_and_private_detail(tmp_path, monkeypatch):
    monkeypatch.setenv('GENOS_QWEN_KEY', 'top-secret')
    terminal = Terminal()
    progress = Progress(tmp_path, terminal)
    progress.document(2, 3290, '외규/아주긴문서명.xml', 'LLM 추출')
    progress.emit('[TASK] ' + json.dumps({'number': 4, 'total': 18, 'stage': 'extract', 'label': '원문 누락 검사'}))
    progress.emit('irrelevant english traceback top-secret')
    assert '\x1b[2K' in terminal.getvalue() and '누적 현황' in terminal.getvalue()
    assert '[2/3290]' in terminal.getvalue() and '아주긴문서명.xml' in terminal.getvalue()
    progress.document(3, 3290, '다음.xml', '추출')
    assert '\x1b[3A' in terminal.getvalue()
    progress.close()
    assert 'top-secret' not in (tmp_path / 'detail.log').read_text()
    assert 'irrelevant' not in terminal.getvalue()
    assert '\x1b' not in (tmp_path / 'progress.log').read_text()


def test_specific_reason_and_empty_stage(tmp_path):
    assert '필수 필드 없음' in reason("schema path graph/clauses/0: 'id' is a required property")
    assert 'ID 연결' in reason('invalid_resolved:target')
    term = io.StringIO()
    progress = Progress(tmp_path, term)
    progress.document(1, 1, 'sample.xml', 'LLM 추출')
    progress.emit('[QUEUE] ' + json.dumps({'passed': 0, 'total': 3, 'stage': '규칙', 'attempt': 1,
        'state': 'READY', 'empty_collections': ['provisos', 'relations'], 'error': None}))
    progress.close()
    assert '해당 내용 없음' in (tmp_path/'progress.log').read_text()
    assert '해당 내용 없음' not in term.getvalue()
    assert '\r' not in term.getvalue()


def test_accumulated_results_survive_phase_changes_and_failures(tmp_path):
    terminal = Terminal(); progress = Progress(tmp_path, terminal)
    try:
        progress.document(1, 2, 'one.pdf', '구조화')
        progress.finish('구조화 완료')
        progress.document(2, 2, 'two.pdf', '구조화')
        progress.error(ValueError('synthetic failure'))
        progress.document(1, 2, 'one.pdf', 'LLM 추출')
        board = '\n'.join(progress._board())
        assert '구조화 완료 1 / 실패 1' in board
        assert '구조화 완료 → LLM 추출 진행 중' in board
        progress.finish('의미 추출 완료')
        summary = json.loads((tmp_path/'progress-summary.json').read_text())
        assert summary['documents']['one.pdf']['stages'] == {'구조화':'COMPLETED', 'LLM 추출':'COMPLETED'}
        assert summary['documents']['two.pdf']['stages']['구조화'] == 'FAILED'
        assert len(progress.recent) == 2
    finally: progress.close()


def test_non_tty_only_emits_boundaries_but_retains_live_state(tmp_path):
    terminal = io.StringIO(); progress = Progress(tmp_path, terminal)
    try:
        progress.document(1, 1, 'one.pdf', '구조화')
        started = terminal.getvalue()
        for n in range(50):
            progress.emit(f'[STRUCTURE STEP] step {n}')
        assert terminal.getvalue() == started
        assert json.loads((tmp_path/'current.json').read_text())['detail'] == 'step 49'
        progress.finish('구조화 완료')
        assert '구조화 완료 1 / 실패 0' in terminal.getvalue()
        assert '\x1b' not in terminal.getvalue()
        assert 'step 0' in (tmp_path/'progress.log').read_text()
    finally: progress.close()


def test_review_board_updates_slots_and_invalidates_old_approval(tmp_path, monkeypatch):
    from lawrag.pipeline import genos_progress
    import os
    monkeypatch.setattr(genos_progress.shutil, 'get_terminal_size', lambda *a: os.terminal_size((55, 10)))
    terminal = Terminal(); progress = Progress(tmp_path, terminal)
    def event(name, **fields):
        progress.emit('[STRUCTURE VLM] '+json.dumps({'event':name, 'run_id':'test', **fields}))
    try:
        progress.document(1, 1, '한글문서.pdf', '구조화')
        for n in range(20):
            event('recipe.review.start', window_number=n+1, window_count=20, pages=[n+1], corrections=0)
        assert len(progress.state['milestones']) == 1
        event('recipe.review.result', window_number=20, window_count=20, verdict='approve', issue_count=0)
        event('recipe.correction', corrections=1)
        assert '이전 승인 사용 안 함' in progress.state['milestones']['검수']
        assert progress.drawn_lines <= 8
        assert '\x1b[3A' in terminal.getvalue()
    finally: progress.close()


def raw_fixture(tmp_path):
    src = tmp_path / 'old/data/corpus'
    (src / 'law').mkdir(parents=True)
    (src / 'internal/부서/팀').mkdir(parents=True)
    (src / 'law/body.xml').write_text(XML)
    (src / 'internal/부서/팀/original.docx').write_bytes(b'protected raw bytes')
    build.atomic(src / 'law/manifest.json', {'items': [{'body_file': str(src / 'law/body.xml'),
                                                      'name': 'raw title'}]})
    return src, tmp_path / '01_DATA'


def test_move_preview_apply_portable_and_idempotent(tmp_path):
    src, data = raw_fixture(tmp_path)
    before = (src / 'law/manifest.json').read_bytes()
    assert move(src, data)['status'] == 'PREVIEW_ONLY'
    assert src.exists() and not data.exists()
    assert move(src, data, apply=True)['status'] == 'MOVED'
    assert not src.exists()
    assert (data / 'RAW/internal/부서/팀/original.docx').read_bytes() == b'protected raw bytes'
    assert json.loads((data / 'RAW/law/manifest.json').read_text())['items'][0]['body_file'] == 'law/body.xml'
    from lawrag.pipeline.genos_corpus import raw_path
    assert raw_path(data / 'RAW', 'law', 'law/body.xml').is_file()
    assert (data / 'LOGS/raw-migration/original-manifests/law/manifest.json').read_bytes() == before
    assert move(src, data, apply=True)['status'] == 'ALREADY_MOVED'


def test_move_conflict_symlink_and_escape(tmp_path):
    src, data = raw_fixture(tmp_path)
    (data / 'RAW').mkdir(parents=True)
    with pytest.raises(FileExistsError):
        move(src, data, apply=True)
    (data / 'RAW').rmdir()  # Empty test-created directory only.
    (src / 'link').symlink_to(src / 'law/body.xml')
    with pytest.raises(ValueError, match='링크'):
        move(src, data)
    with pytest.raises(ValueError, match='밖'):
        rebase({'body_file': '/outside/file.xml'}, src)


def test_interrupted_move_recover(tmp_path, monkeypatch):
    from lawrag.pipeline import genos_raw_move as mover
    src, data = raw_fixture(tmp_path)
    original = mover.atomic
    def fail(path, value):
        if Path(path) == data / 'RAW/law/manifest.json':
            raise OSError('synthetic interruption')
        return original(path, value)
    monkeypatch.setattr(mover, 'atomic', fail)
    with pytest.raises(OSError):
        move(src, data, apply=True)
    assert not src.exists() and (data / 'RAW').exists()
    monkeypatch.setattr(mover, 'atomic', original)
    assert move(src, data, apply=True)['status'] == 'MOVED'
