"""Offline, script-free HTML review of committed batch relations."""
from html import escape


def esc(value):
    return escape(str(value if value is not None else ''), quote=True)


STATUS = {'PROPOSED': '미검토 후보', 'APPROVED': '승인', 'REJECTED': '기각', 'REVOKED': '철회'}


def endpoint(end):
    context = ' → '.join(p.get('title') or p.get('id', '') for p in end.get('context', []))
    spans = ''.join(
        '<div class="span"><small>블록 ' + esc(p['block_id']) + ' · 문자 ' +
        esc(p['start_cp']) + '–' + esc(p['end_cp']) + '</small><pre>' +
        esc(p['text']) + '</pre></div>' for p in end['spans'])
    return (
        '<section class="endpoint"><strong>' + esc(end['document_name']) + '</strong>'
        '<p class="clause">' + esc(end['title']) + '</p><p class="context">' + esc(context) +
        '</p>' + spans + '<details><summary>판본·원문 식별자</summary><dl>'
        '<dt>문서 ID / 판본</dt><dd>' + esc(end['document_id']) + '</dd>'
        '<dt>조항 ID</dt><dd>' + esc(end.get('unit_id', '')) + '</dd>'
        '<dt>원문 해시</dt><dd>' + esc(end['source_artifact_hash']) + '</dd>'
        '<dt>선택 범위 해시</dt><dd>' + esc(end['endpoint_hash']) + '</dd></dl></details></section>')


def render(value):
    """One relation per row; multiple endpoints stay grouped, never cross-multiplied."""
    items = value['items']
    mid = value['batch_status'] not in ('completed', 'partial')
    counts = {s: sum(x['link']['status'] == s for x in items) for s in STATUS}
    rows = []
    for index, item in enumerate(items, 1):
        link = item['link']
        ends = item['binding'] or link
        checked = item['source_check']
        verified = checked['status'] == 'verified'
        rows.append(
            '<tr><td class="number">' + str(index) + '</td><td>' +
            ''.join(endpoint(e) for e in ends['internal']) + '</td><td>' +
            ''.join(endpoint(e) for e in ends['external']) + '</td><td>'
            '<span class="badge">' + esc(STATUS.get(link['status'], link['status'])) + '</span>'
            '<p><b>' + esc(link['kind']) + '</b> · ' + esc(link.get('perspective')) + '</p>'
            '<pre>' + esc(link['reason']) + '</pre>'
            '<p class="' + ('ok' if verified else 'bad') + '">' +
            ('선택 원문·위치 일치 확인' if verified else '원문 확인 실패: ' + esc(checked.get('message'))) +
            '</p><p>' + (('SQLite 적용 후 대사 조회 가능' if value.get('storage') == 'json_candidates_not_published'
                         else '대사 우선 조회 가능') if item.get('retrievable') else '대사 우선 조회 대상 아님') +
            '</p><details><summary>연결·실행 이력</summary><dl><dt>연결 ID</dt><dd>' +
            esc(link['link_id']) + '</dd><dt>Revision</dt><dd>' + esc(link['revision']) +
            '</dd><dt>실행 ID</dt><dd>' + esc(link.get('provenance', {}).get('run_id')) +
            '</dd><dt>생성 시각</dt><dd>' + esc(link.get('created_at')) +
            '</dd><dt>원문 결속 상태</dt><dd>' +
            esc((item['binding'] or {}).get('status', '없음')) + '</dd></dl></details></td></tr>')
    empty = '<tr><td colspan="4" class="empty">현재 저장된 연결이 없습니다. 조사 중일 수 있으며 외규가 없다는 뜻은 아닙니다.</td></tr>'
    selected = ''.join(
        '<tr><td>' + esc(d['name']) + '</td><td>' + esc(value['document_states'].get(d['document_id'], {}).get('status', 'pending')) +
        '</td><td>' + str(sum(any(e['document_id'] == d['document_id'] for e in x['link']['internal']) for x in items)) +
        '</td></tr>' for d in value['documents'])
    return '''<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>내규 · 외규 연결 검토표</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#18283b;font:15px/1.65 system-ui,"Malgun Gothic",sans-serif}
main{max-width:1800px;margin:auto;padding:36px}h1{font-size:30px;margin:8px 0}h2{font-size:19px}
.eyebrow{font-size:12px;letter-spacing:2px;color:#526880}.notice{padding:16px 20px;background:#fff3d8;border-left:4px solid #c88b14}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}.card{background:white;border:1px solid #dbe2ea;padding:14px 24px;min-width:130px}
.card b{display:block;font-size:28px}.card span{font-size:13px;color:#526880}
table{border-collapse:collapse;width:100%;background:white;table-layout:fixed}th{background:#193751;color:white;text-align:left}
th,td{padding:16px;border:1px solid #dbe2ea;vertical-align:top;overflow-wrap:anywhere}thead th{position:sticky;top:0;z-index:1}
th:nth-child(1){width:4%}th:nth-child(2),th:nth-child(3){width:34%}th:nth-child(4){width:28%}
pre{font:inherit;white-space:pre-wrap;margin:8px 0;color:#172b3f}.span{border-top:1px solid #edf0f3;margin-top:12px;padding-top:8px}
small,.context{color:#65778b;font-size:12px}.clause{font-weight:650;color:#174f72;margin:8px 0}
.endpoint+.endpoint{border-top:3px solid #c2d1de;margin-top:20px;padding-top:20px}details{font-size:12px;margin-top:16px}
summary{cursor:pointer;color:#32627e}dl{margin:8px 0}dt{font-weight:600}dd{margin:0 0 8px;overflow-wrap:anywhere}
.badge{padding:4px 9px;background:#e7edf3;border-radius:4px;font-size:12px}.ok{color:#12623c}.bad{color:#a43120}
.number{color:#607287}.empty{text-align:center;padding:50px}.doclist{max-width:850px;margin:24px 0}.doclist th{position:static;width:auto}
footer{font-size:12px;color:#607287;margin:25px 0}@media print{main{padding:0}thead{display:table-header-group}thead th{position:static}details{display:block}body{background:white}}
</style></head><body><main><div class="eyebrow">INTERNAL / EXTERNAL REGULATION LINKS</div><h1>내규 · 외규 연결 검토표</h1>''' + (
        '<p>생성 시각: ' + esc(value['captured_at']) + ' · 배치: ' + esc(value['batch_id']) +
        ' · <b>' + ('중간 결과' if mid else '종료 배치의 저장 결과') + '</b> (' + esc(value['batch_status']) + ')</p>'
        '<div class="notice"><b>' +
        ('별도 JSON 후보이며 관계 SQLite에는 아직 적용하지 않았습니다.' if value.get('storage') == 'json_candidates_not_published'
         else '기존 R3가 관계 SQLite에 저장한 결과입니다. 이 보고서 자체는 관계를 추가·변경하지 않습니다.') +
        '</b><br>저장 완료된 연결의 읽기 전용 스냅샷입니다. 실행 중에는 새 연결이 계속 추가될 수 있으므로 명령을 다시 실행해 새 보고서를 만드세요. '
        '자동 새로고침은 하지 않습니다. 원문 일치 확인은 연결의 법적 타당성에 대한 승인과 다릅니다. '
        '미검토 후보는 검토가 필요하며, 목록에 없다고 대응 외규가 없는 것은 아닙니다. 내부 원문이 포함된 파일입니다.</div>'
        '<div class="cards"><div class="card"><b>' + str(len(items)) + '</b><span>저장된 연결</span></div>' +
        ''.join('<div class="card"><b>' + str(counts[s]) + '</b><span>' + esc(label) + '</span></div>' for s, label in STATUS.items()) +
        '</div><h2>내규별 진행 상태</h2><table class="doclist"><thead><tr><th>선택 내규</th><th>배치 상태</th><th>연결 수</th></tr></thead><tbody>' +
        selected + '</tbody></table><h2>조항별 연결과 실제 원문</h2>'
        '<p>브라우저의 찾기(Ctrl+F)로 문서명·조항·연결 ID를 찾을 수 있습니다. 여러 조항을 함께 묶은 연결은 같은 행에 표시합니다. '
        '이관 묶음에서는 검토 후 APPLY_RELATIONS.txt review --all 또는 review --ids 연결ID...로 적용 대상을 기록합니다.</p>'
        '<table><thead><tr><th>#</th><th>내규 출처 조항 · 선택 원문</th><th>대응 외규 출처 조항 · 선택 원문</th><th>연결 이유 · 검토 상태</th></tr></thead><tbody>' +
        (''.join(rows) or empty) + '</tbody></table><footer>세대: ' + esc(value['source']['generation_id']) +
        ' · 스냅샷: ' + esc(value['snapshot_sha256']) +
        '<br>확인 범위: 연결된 원문·구조·권한·선택 필터. 전체 데이터 파일의 재해시·재색인·모델 호출 없음. '
        '상태 JSON과 관계 DB의 읽기 시각은 서로 다를 수 있습니다.</footer></main></body></html>')
