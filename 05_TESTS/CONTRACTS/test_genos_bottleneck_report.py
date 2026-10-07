"""End-to-end checks for the read-only, TXT-only bottleneck handoff."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '08_DEPLOYMENT/GENOS/diagnostics/06_bottleneck_report.py'
TXT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/bottleneck_20260928_r1/GENOS_BOTTLENECK_20260928_R1.txt'


def event(name, at, **fields):
    return dict(event=name, ts=f'2026-09-28T00:00:{at}Z', **fields)


def report(path, ident='request-a'):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {'schema_version': 'genos-request-report-v1', 'request_id': ident,
            'request': {'question': 'PRIVATE_QUESTION', 'authorization': 'PRIVATE_KEY'},
            'result': {'answer': 'PRIVATE_ANSWER'}, 'journal': {'prompt': 'PRIVATE_PROMPT'},
            'service_events': [
                event('request.started', '00.000', worker_id='worker-a'),
                event('step.finished', '00.800', step='resources.index', duration_ms=800,
                      work_ms=700, thread_cpu_ms=20, start_log_ms=100),
                event('tools.cache.hit', '00.801'),
                event('session.resources.ready', '00.900'),
                event('model.attempt.started', '01.000'),
                event('step.finished', '02.000', step='index.open', duration_ms=99000),
                event('fulltext.sql.timings', '03.000', search_id='a'*32, sql_status='completed',
                      sql_execute_ms=877.028, sql_first_row_ms=5.603, sql_fetch_ms=82920.937,
                      sql_fetch_cpu_ms=112.3, fetched_count=7676, selected_count=2191,
                      scope_rejected_count=5485, active_searches_peak=2,
                      query='PRIVATE_QUERY', source_ids=['PRIVATE_SOURCE'],
                      slowest_batches=[{'batch': 3, 'wall_ms': 20000, 'cpu_ms': 1,
                                        'text': 'PRIVATE_BATCH_TEXT'}]),
                event('step.finished', '03.001', step='fulltext_tool.rank', work_ms=84166,
                      duration_ms=84167, thread_cpu_ms=150),
                event('fulltext.location.timings', '04.000', work_ms=21216.404,
                      source_sql_execute_ms=500, source_sql_fetch_ms=20000,
                      source_json_decode_ms=100, source_json_cpu_ms=99,
                      source_cache_hits=1, source_sql_count=2190),
                event('step.finished', '04.001', step='fulltext_tool.page_preview', work_ms=689),
                event('request.returning', '05.000', duration_ms=120000)]}
    path.write_text(json.dumps(data), encoding='utf-8')
    return data


def run(tmp_path, *args, script=SCRIPT):
    command = [sys.executable, str(script)] if script.suffix == '.py' else ['bash', str(script)]
    result = subprocess.run([*command, '--output', str(tmp_path/'out'), *map(str, args)],
                            cwd=ROOT, capture_output=True, text=True,
                            env={**os.environ, 'GENOS_BOTTLENECK_RUN_LOG_DIR': str(tmp_path/'execution')})
    folders = sorted((tmp_path/'out').iterdir())
    return result, folders[-1]


def texts(folder):
    return '\n'.join(p.read_text() for p in folder.rglob('*.txt'))


def test_completed_report_splits_stages_and_preserves_original(tmp_path):
    path = tmp_path/'logs/2026-09-28/risk_team/one.json'
    report(path)
    original = path.read_bytes()
    result, folder = run(tmp_path, '--root', tmp_path/'logs', '--team', 'risk_team')
    assert result.returncode == 0, result.stderr
    loading = next(folder.rglob('로딩.txt')).read_text()
    fts = next(folder.rglob('FULLTEXT.txt')).read_text()
    assert '900.000 ms' in loading
    assert '작업 700.000 ms' in loading and 'CPU 20.000 ms' in loading
    rank_section = loading.split('초반 구간별 시간 순위')[1].split('캐시/검증 상태')[0]
    assert 'index.open' not in rank_section
    assert '첫 모델 시작 이후' in loading
    assert '82,920.937 ms' in fts and 'source_sql_fetch_ms=20000' in fts
    assert 'active_searches_peak=2' in fts
    assert '중첩' in fts and '합산 금지' in fts
    combined = texts(folder)
    for private in ('PRIVATE_QUESTION', 'PRIVATE_KEY', 'PRIVATE_ANSWER', 'PRIVATE_PROMPT',
                    'PRIVATE_QUERY', 'PRIVATE_SOURCE', 'PRIVATE_BATCH_TEXT'):
        assert private not in combined
    assert hashlib.sha256(original).hexdigest() in loading
    assert path.read_bytes() == original


def test_old_log_without_internal_metrics_reports_unknown(tmp_path):
    path = tmp_path/'old.log'
    path.write_text('2026-09-28T00:00:00+00:00 INFO request.started request_id=request-old worker_id=w1\n'
                    '2026-09-28T00:00:01+00:00 DEBUG step.finished step=fulltext_tool.rank duration_ms=1000 request_id=request-old\n')
    result, folder = run(tmp_path, '--input', path)
    assert result.returncode == 0
    fts = next(folder.rglob('FULLTEXT.txt')).read_text()
    assert '미확인: fulltext.sql.timings 없음' in fts
    assert '미확인: fulltext.location.timings 없음' in fts
    assert 'fulltext_tool.rank: 1,000.000 ms' in fts
    assert '로딩 준비=미확인' in texts(folder)


def test_container_requests_and_unbound_warmup_remain_separate(tmp_path):
    path = tmp_path/'container.jsonl'
    rows = [event('step.finished', '00.000', step='warmup.resources', duration_ms=4000,
                  process_id=10, thread_id=11),
            event('request.started', '01.000', request_id='a', worker_id='w1'),
            event('request.started', '01.000', request_id='b', worker_id='w2'),
            event('fulltext.sql.timings', '02.000', request_id='a', sql_fetch_ms=8000),
            event('fulltext.sql.timings', '02.000', request_id='b', sql_fetch_ms=20)]
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    result, folder = run(tmp_path, '--input', path)
    assert result.returncode == 0
    assert len(list(folder.rglob('FULLTEXT.txt'))) == 3
    a = next(folder.glob('*-a/FULLTEXT.txt')).read_text()
    b = next(folder.glob('*-b/FULLTEXT.txt')).read_text()
    assert '8,000.000 ms' in a and '8,000.000 ms' not in b
    assert '20.000 ms' in b
    assert 'NO_REQUEST_ID:10:11' in texts(folder)


def test_json_companion_is_used_once_and_team_is_selected(tmp_path):
    path = tmp_path/'logs/2026-09-28/risk_team/one.json'
    report(path)
    path.with_suffix('.log').write_text('PRIVATE_LOG')
    report(tmp_path/'logs/2026-09-28/finance_team/two.json', 'request-finance')
    result, folder = run(tmp_path, '--root', tmp_path/'logs', '--team', 'risk_team')
    assert result.returncode == 0
    assert len(list(folder.rglob('FULLTEXT.txt'))) == 1
    assert 'request-finance' not in texts(folder)


def test_malformed_report_is_recorded_without_hiding_valid_input(tmp_path):
    path = tmp_path/'good.json'
    report(path)
    bad = tmp_path/'bad.json'
    bad.write_text('{unfinished')
    result, folder = run(tmp_path, '--input', bad, '--input', path)
    assert result.returncode == 0
    assert '읽기 실패 JSONDecodeError' in texts(folder)
    assert bad.read_text() == '{unfinished'


def test_no_matching_request_leaves_failure_txt_and_nonzero_status(tmp_path):
    path = tmp_path/'good.json'
    report(path)
    result, folder = run(tmp_path, '--input', path, '--request-id', 'missing')
    assert result.returncode == 2
    assert '실패: 조건에 맞는 계측 없음' in texts(folder)
    assert not list(folder.rglob('FULLTEXT.txt'))


def test_readable_txt_and_nonfinite_or_content_counters(tmp_path):
    path = tmp_path/'readable.txt'
    path.write_text('질문: PRIVATE_QUESTION\n'
                    '2026-09-28T00:00:01+00:00 [service/DEBUG] step.finished step=resources.index duration_ms=200\n'
                    '2026-09-28T00:00:02+00:00 [service/INFO] fulltext.sql.timings sql_fetch_ms=NaN sql_execute_ms=PRIVATE_KEY\n')
    result, folder = run(tmp_path, '--input', path)
    assert result.returncode == 0
    combined = texts(folder)
    assert 'PRIVATE_' not in combined
    assert 'execute: 미확인' in combined and '이후 fetch: 미확인' in combined


def test_exec_txt_is_self_contained_and_creates_persistent_log(tmp_path):
    path = tmp_path/'good.json'
    report(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result, folder = run(tmp_path, '--input', path, script=TXT)
    assert result.returncode == 0, result.stderr
    assert len(list(folder.rglob('로딩.txt'))) == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert 'PRIVATE_' not in result.stdout
    assert list((tmp_path/'execution').glob('*.txt'))


def test_missing_root_returns_failure_in_execution_log(tmp_path):
    result, folder = run(tmp_path, '--root', tmp_path/'missing', script=TXT)
    assert result.returncode == 2
    assert '실패' in texts(folder)
    assert 'exit_status=2' in result.stdout


def test_stalled_partial_live_log_shows_unfinished_stage_without_claiming_done(tmp_path):
    path = tmp_path/'partial.log'
    path.write_text('2026-09-28T00:00:00Z INFO request.started request_id=partial\n'
                    '2026-09-28T00:00:01Z DEBUG step.started step=fulltext_tool.rank request_id=partial\n'
                    '2026-09-28T00:00:02Z INFO fulltext.sql.started search_id=' + 'a'*32 + ' request_id=partial\n'
                    '2026-09-28T00:00:31Z INFO request.heartbeat elapsed_ms=31000 request_id=partial\n')
    result, folder = run(tmp_path, '--input', path)
    assert result.returncode == 0
    fts = next(folder.rglob('FULLTEXT.txt')).read_text()
    assert '시작→마지막 기록 30,000.000 ms' in fts
    assert '진행 중 또는 완료 로그 누락' in fts
    assert '시작 있음 / 완료 계측 없음' in fts
    assert '미확인: fulltext.sql.timings 없음' in fts


def test_embedded_source_matches_canonical_and_bash_syntax():
    delivery = TXT.read_text()
    embedded = delivery.split("<<'GENOS_BOTTLENECK_PYTHON'\n", 1)[1].rsplit('\nGENOS_BOTTLENECK_PYTHON\n', 1)[0]
    assert embedded == SCRIPT.read_text()
    assert subprocess.run(['bash', '-n', str(TXT)], capture_output=True).returncode == 0


def test_context_only_report_cannot_claim_measurements_exist(tmp_path):
    path = tmp_path/'context.json'
    data = report(path)
    data['service_events'] = [event('request.started', '00.000'), event('request.returning', '01.000', duration_ms=1000)]
    path.write_text(json.dumps(data))
    result, folder = run(tmp_path, '--input', path)
    assert result.returncode == 2
    assert '요청 공통 이벤트만 있음' in texts(folder)
    assert not list(folder.rglob('FULLTEXT.txt'))
