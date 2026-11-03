"""Analyze a saved R3 report. No Oracle, SQLite, INSERT or model calls."""
import csv
from datetime import datetime
import html
import json
from pathlib import Path
import math
import uuid


def good_number(value):
    return isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0


def analyze(report):
    items=report.get('items',[])
    kinds={item['kind']:item for item in items}
    if len(kinds)!=len(items):raise ValueError('DUPLICATE_PLAN_KIND')
    for item in items:
        if type(item.get('rows')) is not int or item['rows']<0:raise ValueError('INVALID_PLAN_COUNT')
    groups={}
    for probe in report.get('oracle',{}).get('insert_probes',[]):
        if probe.get('table')!='SRCH_ROW' or probe.get('status')!='ROLLED_BACK_VERIFIED':continue
        kind=probe.get('kind')
        if kind not in kinds or not good_number(probe.get('rows')) or not good_number(probe.get('request_seconds')):continue
        rank=probe.get('requested_rows',0)
        if kind not in groups or rank>groups[kind].get('requested_rows',0):groups[kind]=probe
    rows=[]
    for kind,item in kinds.items():
        p=groups.get(kind,{})
        seconds_per_row=p['request_seconds']/p['rows'] if p else None
        def share(field):
            value=p.get(field)
            return 100*value/p['request_seconds'] if p and isinstance(value,(int,float)) and math.isfinite(value) and value>=0 else None
        rows.append({'kind':kind,'planned_rows':item['rows'],'trial_rows':p.get('rows'),
            'request_seconds':p.get('request_seconds'),'seconds_per_row':seconds_per_row,
            'plan_scaled_request_hours':item['rows']*seconds_per_row/3600 if p else None,
            'insert_percent':share('insert_db_seconds'),'verify_percent':share('verify_db_seconds'),
            'unseparated_request_percent':share('request_outside_measured_db_seconds'),
            'payload_bytes':p.get('payload_bytes'),'sql_bytes':p.get('sql_bytes'),
            'prepare_seconds':p.get('prepare_seconds'),'render_seconds':p.get('render_seconds'),
            'candidate_only_not_excluded':bool(item.get('candidate'))})
    rows.sort(key=lambda r:-r['planned_rows'])
    total=sum(r['planned_rows'] for r in rows)
    covered=sum(r['planned_rows'] for r in rows if r['seconds_per_row'] is not None)
    measured=[r for r in rows if r['seconds_per_row'] is not None and r['planned_rows']>0]
    hours=sum(r['plan_scaled_request_hours'] for r in measured) if measured else None
    rates=[r['seconds_per_row'] for r in measured]
    return {'planned_rows':total,'trial_covered_plan_rows':covered,'unmeasured_plan_rows':total-covered,
        'covered_request_hours_reference':hours,
        'all_plan_if_missing_at_fastest_trial_hours':hours+(total-covered)*min(rates)/3600 if rates else None,
        'all_plan_if_missing_at_slowest_trial_hours':hours+(total-covered)*max(rates)/3600 if rates else None,
        'actual_remaining_eta_hours':None,'full_completion_eta_hours':None,
        'scope':'Historical rollback/diagnostic-exception request rates; assumptions, not ETA bounds. No COMMIT/source generation/final verification/vector forecast.',
        'loader_status':report.get('loader_status'),'binding':report.get('binding',{}),'rows':rows}


def run(observer=None,report_path=''):
    if report_path:
        path=Path(report_path).expanduser().resolve(strict=True)
        if path.stat().st_size>16*1024**2:raise ValueError('REPORT_SIZE_LIMIT')
        report=json.loads(path.read_text(encoding='utf-8'));origin=str(path)
    elif observer is not None and isinstance(getattr(observer,'REPORT',None),dict):
        report=observer.REPORT;origin=str(observer.OUTPUT)
    else:raise ValueError('같은 R3 노트북에서 실행하거나 TIME_REPORT_PATH에 기존 REPORT.json 경로를 지정하세요. 새 시험은 실행하지 않습니다.')
    result=analyze(report);result['report_origin']=origin
    output=Path.cwd()/'gold-time-analysis'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    (output/'TIME_ANALYSIS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if result['rows']:
        with (output/'KIND_TIMES.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(result['rows'][0]));writer.writeheader();writer.writerows(result['rows'])
    fmt=lambda n:'미측정' if n is None else f'{n:,.2f}'
    summary=[['검색 계획 / 시험이 있는 종류의 계획행',f"{result['planned_rows']:,} / {result['trial_covered_plan_rows']:,}"],
        ['시험이 있는 종류의 요청시간 단순환산',fmt(result['covered_request_hours_reference'])+'시간'],
        ['미측정 종류를 가장 빠른 관측률로 가정',fmt(result['all_plan_if_missing_at_fastest_trial_hours'])+'시간'],
        ['미측정 종류를 가장 느린 관측률로 가정',fmt(result['all_plan_if_missing_at_slowest_trial_hours'])+'시간'],
        ['실제 전체 완료/잔여시간','미확정 — 원본 준비/COMMIT/전수검증/임베딩 별도'],
        ['원래 적재 상태',result.get('loader_status') or '미확인']]
    detail=[['종류(큰순서12)','계획행','시험행','요청초','INSERT%','검증%','기타요청%']]
    detail += [[r['kind'],f"{r['planned_rows']:,}",r['trial_rows'],fmt(r['request_seconds']),fmt(r['insert_percent']),
                fmt(r['verify_percent']),fmt(r['unseparated_request_percent'])] for r in result['rows'][:12]]
    esc=lambda v:html.escape('미측정' if v is None else str(v))
    table=lambda rows:'<table style="width:100%;border-collapse:collapse">'+''.join('<tr>'+''.join('<td style="padding:6px;border-bottom:1px solid #ddd">'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</table>'
    value='<div style="max-width:1100px;background:white;color:#243a50;padding:15px;font:14px Arial"><b>저장된 R3 시간 분석</b>'+table(summary)+'<br>'+table(detail)
    value+='<p>두 가정은 최소/최대 보장범위가 아닙니다. 롤백·진단용 오류 응답을 포함한 과거 시험이며 실제 적재 배치와 다릅니다. 기타요청은 순수 네트워크가 아닙니다. 제외 후보도 계획에 포함하며 현재 완료분을 빼지 않았습니다.</p><p>SQL/INSERT 실행 없음. 전체 결과: '+esc(output)+'/TIME_ANALYSIS.json</p></div>'
    from IPython.display import HTML,display
    display(HTML(value))
    return result,output
