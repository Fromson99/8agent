"""Read-only, one-display monitor. Does not launch, retry or cancel a scenario."""
from html import escape
import json
import time
from progress_panel import _DefaultSink, duration
from zip_config import STAGES
from dev_guard import PROJECT
from zip_runtime import read_folder


def snapshot(cfg):
    import dataiku
    if dataiku.api_client().get_default_project().project_key != PROJECT or cfg['project'] != PROJECT:
        raise ValueError('TEST_PROJECT_REQUIRED')
    rows = []
    for stage, code, label, _ in STAGES:
        folder = dataiku.Folder(cfg['folders'][stage], ignore_flow=True)
        try:
            value = read_folder(folder, 'latest.json')
            rows.append({'stage':stage, 'title':code[:2]+' '+label, 'value':value})
        except Exception as exc:
            rows.append({'stage':stage, 'title':code[:2]+' '+label,
                         'value':None, 'observation_error':type(exc).__name__+': '+str(exc)})
    # Do not combine a prior final report with a newer running/failed stage.
    values = [r['value'] for r in rows]
    complete = all(v and v.get('status')=='SUCCESS' for v in values)
    if complete:
        complete = values[-1].get('ended_at',0) >= max(v.get('started_at',0) for v in values)
    report = None
    if complete:
        report = read_folder(dataiku.Folder(cfg['folders']['report'], ignore_flow=True), 'report.json')
        complete = bool(report and report.get('status')=='GOLD_LOADED' and
                        report.get('row_counts_and_publications_verified'))
    return {'rows':rows,'complete':complete,'report':report}


def render(state, elapsed):
    labels = {'SUCCESS':'완료','FAILED':'실패','RUNNING':'실행 중으로 기록됨'}
    title = '예시 2조각 Gold 시험 · 최근 단계별 결과'
    plain = [title, '관찰 경과 '+duration(elapsed)]
    html = '<div style="max-width:1100px;border:1px solid #cbd5e1;border-radius:8px;padding:16px"><b>'+title+'</b>'
    html += '<p>관찰 경과 '+duration(elapsed)+' · 단계별 최근 기록입니다. 실행 여부는 Scenarios에서도 확인하세요.</p>'
    html += '<table style="width:100%;border-collapse:collapse"><tr><th align="left">단계</th><th align="left">상태</th><th align="left">실행 시간 / 확인 내용</th></tr>'
    for row in state['rows']:
        value = row['value'] or {}
        status = labels.get(value.get('status'), '미실행')
        note = ''
        if row.get('observation_error'):
            status='조회 실패'; note=row['observation_error']
        elif value:
            ended = value.get('ended_at')
            note = duration(ended-value['started_at']) if ended else '아직 종료 기록 없음'
            if value.get('error'): note += ' · '+value['error']
            result = value.get('result',{})
            if 'query_rows' in result: note += ' · 검색자료 '+str(result['query_rows'])+'행 준비'
            if row['stage']=='vector' and value.get('status')=='SUCCESS': note += ' · 벡터 '+str(result.get('rows','?'))+'개'
        plain.append(row['title']+' | '+status+' | '+note)
        html += '<tr>'+''.join('<td style="border-top:1px solid #e2e8f0;padding:9px">'+escape(x)+'</td>' for x in (row['title'],status,note))+'</tr>'
    html += '</table>'
    note = '전체 성공 여부: 최신 결과 저장·행수·게시 기록 확인 완료' if state['complete'] else '전체 성공 여부: 아직 확인되지 않음'
    if state['complete']:
        note += '\n확인한 행수: '+json.dumps(state['report']['counts'],ensure_ascii=False)
    note += '\n전체 로그: 각 단계 RESULT 폴더의 runs/ · 결과: 07_REPORT_RESULT/report.json'
    note += '\n단계별 작업량이 달라 전체 진행률·처리속도·ETA는 계산하지 않습니다.'
    plain.append(note)
    html += '<pre style="white-space:pre-wrap">'+escape(note)+'</pre></div>'
    return html, '\n'.join(plain)


def watch(cfg, seconds=600, interval=3, sink=None):
    if seconds<=0 or interval<1: raise ValueError('POSITIVE_OBSERVATION_WINDOW_REQUIRED')
    sink = sink or _DefaultSink()
    started = time.monotonic()
    try:
        while True:
            state = snapshot(cfg)
            elapsed = time.monotonic()-started
            terminal = state['complete'] or elapsed>=seconds
            html, plain = render(state, elapsed)
            sink(html, plain, terminal)
            if terminal: return state
            time.sleep(interval)
    except KeyboardInterrupt:
        sink('<p>관찰만 종료했습니다. 실제 작업 상태는 Scenarios에서 확인하세요.</p>',
             '관찰만 종료했습니다. 실제 작업 상태는 Scenarios에서 확인하세요.', True)
