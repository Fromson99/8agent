"""HTML overview from observed progress; no DB calls and no invented completion."""
from html import escape
import time
from flow_spec import STAGES

def duration(n):
    if n is None: return '계산 중'
    h, s=divmod(max(0,int(n)),3600); m,s=divmod(s,60)
    return f'{h}시간 {m}분 {s:02d}초'

def number(n): return '—' if n is None else format(n, ',')

def render(records, *, preview=False):
    esc=lambda v:escape(str(v),quote=True)
    cards=[]; pipelines=[]; tables=[]
    statuses={'WAITING':'대기','RUNNING':'진행 중','SUCCESS':'완료','FAILED':'오류 · 중단'}
    for index,(stage,code,label,zone,keys) in enumerate(STAGES):
        r=records.get(stage,{})
        status=r.get('status','WAITING'); done=r.get('rows'); total=r.get('total')
        pct=min(100,max(0,100*done/total)) if total and done is not None else 0
        detail=r.get('detail','아직 실행하지 않았습니다.')
        pipelines.append(f'<div class="node {esc(status)}"><span>{index+1:02d}</span><b>{esc(label)}</b><small>{statuses.get(status,esc(status))}</small></div>')
        meter=f'<div class="meter"><i style="width:{pct:.2f}%"></i></div>' if total else ''
        count=f'<strong>{number(done)} <em>/ {number(total)} {esc(r.get("unit","행"))}</em></strong>' if done is not None else '<strong>—</strong>'
        error=f'<pre>{esc(r["error"])}</pre>' if r.get('error') else ''
        stamp=time.strftime('%m-%d %H:%M:%S',time.localtime(r['updated_at'])) if r.get('updated_at') else '미수집'
        cards.append(f'<article class="{esc(status)}"><header><span>{esc(code)}</span><i>{statuses.get(status,esc(status))}</i></header><h2>{esc(label)}</h2>{count}{meter}<p>{esc(detail)}</p><dl><div><dt>경과</dt><dd>{duration(r.get("elapsed"))}</dd></div><div><dt>현재 단계 잔여</dt><dd>{"중단됨" if status=="FAILED" else duration(r.get("eta"))}</dd></div></dl>{error}<footer>갱신 {stamp} · {esc(r.get("basis","아직 측정 전"))}</footer></article>')
        for t in r.get('result',{}).get('tables',[]):
            tables.append(f'<tr><td>{esc(t["table"])}</td><td>{number(t["rows"])}</td><td><span class="ok">DB 조회 확인</span></td></tr>')
    complete=sum(r.get('status')=='SUCCESS' for r in records.values())
    failed=any(r.get('status')=='FAILED' for r in records.values())
    report=records.get('report',{}).get('result',{})
    actual=sum(t['rows'] for t in report.get('tables',[])) if report.get('tables') else None
    mode='미리보기 · 연결 전 · 실제 처리 수치 없음' if preview else ('오류 확인 필요' if failed else f'{complete} / 8 단계 완료')
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gold 데이터 적재 현황</title><style>
*{box-sizing:border-box}body{margin:0;background:#edf2f8;color:#15233b;font:14px/1.6 Arial,'Malgun Gothic',sans-serif}.wrap{max-width:1360px;margin:auto;padding:34px} .hero{background:#10213d;color:white;padding:32px 36px;border-radius:20px;position:relative}.eyebrow{letter-spacing:3px;font-size:11px;color:#7dd9d1}h1{font-size:32px;letter-spacing:-1px;margin:10px 0}h2{font-size:17px;margin:15px 0}.hero p{color:#bacbe1;margin:6px 0}.badge{display:inline-block;padding:7px 13px;border:1px solid #385679;border-radius:30px;color:#c7f5e9;margin-top:12px}.stats{display:flex;gap:16px;margin-top:24px}.stats div{background:#ffffff0d;padding:12px 18px;border-radius:10px;min-width:170px}.stats b{display:block;font-size:24px}.stats small{color:#b4c9e2}.pipeline{display:grid;grid-template-columns:repeat(8,1fr);gap:9px;margin:24px 0}.node{border:1px solid #d5dfeb;background:white;padding:13px 10px;border-radius:11px}.node span{display:block;color:#8c9db5;font-size:11px}.node b{font-size:12px;display:block;margin:5px 0}.node small{font-size:11px;color:#7b899c}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}article{background:white;border:1px solid #dce5ef;border-radius:15px;padding:20px;min-width:0}article header{display:flex;justify-content:space-between;color:#78869a;font-size:10px;gap:4px}article header i{font-style:normal;border-radius:15px;padding:2px 8px;background:#edf1f7}strong{font-size:23px;display:block;letter-spacing:-.7px}em{font-size:11px;font-style:normal;color:#8591a3;letter-spacing:0}.meter{height:7px;background:#edf2f7;border-radius:6px;margin-top:10px;overflow:hidden}.meter i{display:block;height:100%;background:#22ae9b}article p{color:#6a788c;font-size:12px;min-height:38px;overflow-wrap:anywhere}dl{display:flex;gap:14px;border-top:1px solid #edf1f6;padding-top:12px}dt{font-size:10px;color:#8b97a8}dd{margin:4px 0;font-size:12px}footer{color:#98a2b1;font-size:10px;margin-top:14px}.RUNNING{border-color:#3799df}.RUNNING header i{background:#e5f2ff;color:#1874bc}.SUCCESS header i,.ok{background:#e4f6ef;color:#167d62}.FAILED{border-color:#dc796e}.FAILED header i{background:#ffebe9;color:#b43e32}pre{font-size:11px;white-space:pre-wrap;word-break:break-word;background:#fff1f0;padding:10px;max-height:240px;overflow:auto}.result{margin-top:24px;border-radius:16px;background:white;padding:24px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:10px;border-bottom:1px solid #edf2f6}td:nth-child(2){text-align:right}.ok{padding:4px 9px;border-radius:20px}.note{font-size:12px;color:#697b93;margin:18px 0}.flow-line{font-size:15px;color:#dce9fa;letter-spacing:.3px}@media(max-width:1000px){.grid{grid-template-columns:repeat(2,1fr)}.pipeline{grid-template-columns:repeat(4,1fr)}}@media(max-width:600px){.grid{grid-template-columns:1fr}.wrap{padding:14px}.stats{flex-wrap:wrap}.hero{padding:22px}h1{font-size:25px}}
</style><div class="wrap"><section class="hero"><div class="eyebrow">LEGAL RAG / DATA PIPELINE</div><h1>데이터가 DB에 쌓이는 과정, 한눈에</h1><p class="flow-line">NFS 원본 → Dataiku 준비 → Oracle Gold _1 → 검증 → 벡터 저장</p><div class="badge">''' + esc(mode) + '''</div><div class="stats"><div><small>대상 DB 테이블</small><b>17</b></div><div><small>DB 실조회 합계 · 보고서 시점</small><b>''' + number(actual) + '''</b></div><div><small>서비스 조회 전환</small><b style="font-size:17px">별도 적용</b></div></div></section><section class="pipeline">''' + ''.join(pipelines) + '''</section><section class="grid">''' + ''.join(cards) + '''</section><p class="note">처리 행 수는 저장 완료 기록 기준입니다. DB 실조회는 마지막 결과 확인 단계에서 별도로 수행합니다. 잔여 시간은 현재 단계의 관측 속도 기준이며 다음 단계·벡터 시간을 포함하지 않습니다. 실행 중 약 15초마다 기록을 갱신합니다. 이 화면은 마지막 저장된 현황이며 새로고침하여 갱신 시각을 확인하세요.</p><section class="result"><h2>Oracle 저장 결과</h2>''' + ('<table><thead><tr><th>실제 테이블</th><th>현재 행 수</th><th>확인</th></tr></thead><tbody>'+''.join(tables)+'</tbody></table>' if tables else '<p class="note">최종 DB 확인 전입니다. 원문·검색·벡터 적재 후 실제 COUNT 결과가 표시됩니다. 온톨로지 승인 자료와 Agent 실행 기록은 별도 입력이므로 0행일 수 있습니다.</p>') + '</section></div></html>'
