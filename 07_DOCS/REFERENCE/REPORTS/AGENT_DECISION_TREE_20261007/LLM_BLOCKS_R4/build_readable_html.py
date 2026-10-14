"""Standalone searchable documentation, with no network or engine execution."""
import html
import json
import re


def build_html(out, rows, profile_rows, checked_files):
    original = (out.parent / 'LLM_BLOCKS_R3/AGENT_LLM_INPUT_BLOCKS_UTF8.txt').read_text()
    original = original.replace(
        '    수정도 실패하면 현재는 예외로 종료될 수 있다.\n',
        '    수정 실패는 MODEL_DECISION_UNRESOLVED로 정리한다.\n'
        '    채택 근거가 있으면 FINISH, 없으면 PENDING 결과로 이어진다.\n'
        '    도구·참조 예외처럼 다른 종료 경로는 구분해야 한다.\n')
    headings = list(re.finditer(r'(?m)^(\d+)\. (.+)$', original))
    sections = {}
    for i, m in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(original)
        sections[int(m[1])] = original[m.end():end].strip()
    groups = [
        ('common', '공통 — 모든 호출을 감싸는 예산·입력·출력', ['공통'], None),
        ('b1', 'LLM 1 — 조사 에이전트를 실행할 요청인가?', ['LLM 1 분류'], 3),
        ('b2', 'LLM 2 — 새 질문·정정·재개 중 어떤 명령인가?', ['LLM 2 명령'], 4),
        ('b3', 'LLM 3 — 정한 명령이 사용자 요청과 맞는가?', ['LLM 3 명령 확인'], 5),
        ('b4', 'LLM 4 — 답해야 할 쟁점은 무엇인가?', ['LLM 4 쟁점 분리'], 6),
        ('search', '검색 준비 코드 — 검색 표현과 검색에 쓸 단어', ['검색 준비'], None),
        ('b5', 'LLM 5 — 현재 법령·조항·원문 화면에서 다음 행동', ['LLM 5 탐색'], 7),
        ('read', '원문 읽기 코드 — 확보량과 모델 전달량', ['원문 읽기'], None),
        ('b6', 'LLM 6 — 참조한 다른 자료를 따라갈 것인가?', ['LLM 6 참조'], 8),
        ('b7', 'LLM 7 — 쟁점별로 답변·부분 답변·추가 조사', ['LLM 7 판단'], 9),
        ('repair', '수정·전송 공통 — 실패 시 다음 호출에 전달되는 것', ['수정 공통', '전송 공통'], None),
        ('result', '답변 구성·사용자 응답·저장 조회', ['결과·조회'], 10),
        ('conditional', '조건부·구형 경로 — 설정 존재와 실제 적용 구분', ['조건부·비활성'], None),
    ]
    cards = []
    for key, title, blocks, section in groups:
        entries = [r for r in rows if r['block'] in blocks]
        info = sections.get(section, '')
        data = json.dumps({'title': title, 'info': info, 'entries': entries}, ensure_ascii=False)
        limits = []
        for r in entries:
            current = r['status'] == '현행'
            limits.append(f'''<details class="limit" data-status="{'current' if current else 'conditional'}">
<summary><span class="identifier">{r['id']}</span><span class="limit-name">{html.escape(r['name'])}</span>
<span class="value">{html.escape(r['value'])}</span><span class="tag">{html.escape(r['kind'])}</span></summary>
<div class="limit-body"><p class="status">적용 상태: {html.escape(r['status'])}</p>
<p><b>실제로 하는 일</b> {html.escape(r['behavior'])}</p>
<p><b>한도 초과·이후 확인</b> {html.escape(r['continuation'])}</p>
<p class="source">{html.escape(r['path'])}:{r['line']}</p><code>{html.escape(r['expression'])}</code></div></details>''')
        info_html = f'<div class="explanation"><b>LLM 입력 블록 · 판단 · 성공/실패 분기</b><pre>{html.escape(info)}</pre></div>' if info else ''
        cards.append(f'''<details class="stage" id="{key}" {'open' if key == 'common' else ''}>
<summary>{html.escape(title)}<span class="count">{len(entries)}항목</span></summary>
{info_html}<div class="limits">{''.join(limits)}</div>
<script type="application/json" class="card-data">{data.replace('<', chr(92)+'u003c')}</script></details>''')
    profile_html = ''.join(f'<tr><td><code>{html.escape(r["setting"])}</code></td><td>{html.escape(r["selected_value"])}</td><td>{html.escape(r["usage"])}</td></tr>' for r in profile_rows)
    page = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>우리 agent: LLM 입력·판단·슬라이스·상한</title><style>
:root{--ink:#16243a;--muted:#526077;--line:#d6e0ec;--blue:#1d4ed8;--paper:#fff;--wash:#f3f6fb}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.7 system-ui,'Malgun Gothic',sans-serif}
main{max-width:1120px;margin:auto;padding:30px 22px 70px}h1{font-size:30px;line-height:1.4;margin:8px 0}p{margin:12px 0}a{color:var(--blue)}
.meta,.source{color:var(--muted);font-size:13px;overflow-wrap:anywhere}.intro,.flow,.stage,.profile{background:var(--paper);border:1px solid var(--line);border-radius:12px;margin:16px 0;padding:18px}
.highlights{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.highlight{background:#eef4ff;border-radius:8px;padding:12px}.highlight b{display:block;font-size:18px}
.legend{display:flex;gap:8px;flex-wrap:wrap}.legend span,.tag{background:#edf2f7;border-radius:5px;padding:3px 8px;font-size:12px}.flow pre,pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 ui-monospace,'Malgun Gothic',monospace}
.toolbar{position:sticky;top:0;z-index:2;background:#f3f6fbf5;padding:12px 0;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;align-items:center;gap:9px}
input,select,button{font:inherit;border:1px solid #b8c7dc;border-radius:7px;padding:8px 10px;background:#fff;color:var(--ink)}input{flex:1;min-width:230px}button{cursor:pointer;font-size:14px}
.stage>summary,.profile>summary{font-weight:700;cursor:pointer;font-size:19px}.count{font-size:12px;color:var(--muted);margin-left:10px}.explanation{margin:16px 0;padding:14px 18px;border-left:4px solid #7ea4ea;background:#f4f7fd}
.limit{border-top:1px solid var(--line);padding:10px 0}.limit>summary{cursor:pointer;display:flex;align-items:center;gap:9px;flex-wrap:wrap;list-style:none}.limit>summary:before{content:'＋';color:var(--blue)}.limit[open]>summary:before{content:'−'}
.identifier{font-size:12px;color:var(--muted)}.limit-name{font-weight:600}.value{color:#1748a0;font-weight:650}.limit-body{padding:8px 16px;margin:8px 0 0;background:#f8fafd;border-radius:8px}.limit-body b{display:block;color:#304561;font-size:13px}.limit-body code{font-size:12px;display:block;white-space:pre-wrap;overflow-wrap:anywhere}.status{font-size:13px;color:#5a4b34}
.jump{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px}.jump a{font-size:14px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);text-align:left;padding:8px;vertical-align:top}td:first-child{overflow-wrap:anywhere;width:36%}footer{margin-top:26px;font-size:14px;color:var(--muted)}[hidden]{display:none!important}
@media(max-width:750px){main{padding:18px 12px}h1{font-size:25px}.highlights{grid-template-columns:1fr}.stage>summary{font-size:17px}.tag{display:block}td:first-child{width:42%}}
@media print{body{background:white}.toolbar,.jump,button{display:none}.stage,.profile{break-inside:auto}main{max-width:none;padding:0}.stage>summary{font-size:15px}}
</style></head><body><main>
<p class="meta">로컬 선택 MAIN generation 44 · investigation-completion-v6-20261007-r1 · 2026-10-07</p>
<h1>우리 agent를 LLM 입력·판단 단위로 보기</h1>
<p>각 판단에서 모델에게 무엇이 들어가는지, 어디서 목록·본문을 줄이는지, 한도를 넘으면 어떻게 되는지를 함께 보여줍니다.</p>
<div class="intro"><div class="highlights">
<div class="highlight"><b>5개 제한은 현재 근거 상한이 아님</b>구형 max_core_sources 기본5와 현행 법령 탐색의 실제 배선을 구분했습니다.</div>
<div class="highlight"><b>100000자 설정은 공통 자동 컷이 아님</b>참조 입력 검사와 모든 탐색·판단 입력의 전체 크기는 별개입니다.</div>
<div class="highlight"><b>저장 원문과 모델이 본 범위는 다름</b>240/360/600자 미리보기, 원문 페이지, 마지막 판단의 전체 근거 입력을 따로 봅니다.</div>
</div><p>분류 기준을 확인하면 숫자가 무엇을 뜻하는지 구분할 수 있습니다.</p><div class="legend">
<span>페이지: total·cursor로 이어보기</span><span>슬라이스: 앞/최근 일부만 모델에 전달</span><span>출력 계약: 초과 출력 거절</span>
<span>무손실 분할: 전체를 나누어 처리</span><span>실행 중단: 못 한 상태 유지 필요</span><span>조건부·비활성: 현재 적용 여부 별도</span></div></div>
<div class="flow"><b>호출 순서와 되돌아가는 위치</b><pre>사용자 입력 → 코드: 권한·요청·기존 사건 확인
 ├─ LLM 1: 조사 요청인가? → DIRECT이면 안내 답변
 └─ CASE
     ├─ LLM 2: 새 질문/정정/재개 명령 선택
     ├─ LLM 3: 명령 확인 → 틀리면 LLM 2 수정 한 번
     ├─ LLM 4: 원래 요구를 쟁점으로 정리
     ├─ 코드: 검색 표현 생성 → 검색 → 후보·원문 준비
     ├─ LLM 5: 이번 화면에서 다음 행동 선택 ↔ 코드: 검색·읽기·복귀
     │    └─ 참조를 따라갈 때 LLM 6 ↔ 코드: 참조 대상 읽기
     └─ LLM 7: 쟁점별 답변 가능 범위 판단
          ├─ 추가 원문 필요 → LLM 5로 복귀 최대2회
          ├─ 출력 계약 오류 → 판단 수정 한 번
          └─ 답변/부분 답변 → 코드: 구성·검증 → 사용자 응답

7개는 호출 종류입니다. 실제 호출 횟수는 반복·수정·재시도에 따라 달라집니다.
어느 제한에 걸렸든 ‘못 찾음/못 읽음/못 판단함’을 ‘규정이 없음’으로 바꾸면 안 됩니다.
상태 보존·풍부한 실패 전달에는 아직 수정이 필요한 경로가 있으며 본문에서 구분합니다.</pre>
<nav class="jump">__JUMPS__</nav></div>
<div class="toolbar"><input id="query" type="search" aria-label="설정과 처리 설명 검색" placeholder="예: 5개, 48, max_context, 12000, 판단 수정">
<select id="status" aria-label="적용 상태 필터"><option value="all">전체 적용 상태</option><option value="current">현행</option><option value="conditional">조건부·구형·비활성</option></select>
<button id="expand">전부 펼치기</button><button id="collapse">전부 접기</button><span id="result" aria-live="polite"></span></div>
__CARDS__
<details class="profile"><summary>선택 프로필 전체 __PROFILE_COUNT__필드</summary><p>파일 값과 서비스 팩토리의 적용 지점을 구분했습니다. 위 표의 현행 여부를 함께 확인하세요.</p>
<table><thead><tr><th>설정</th><th>선택 값</th><th>적용 설명</th></tr></thead><tbody>__PROFILE_ROWS__</tbody></table></details>
<footer><p>__ENTRY_COUNT__개 수동 설명 항목과 관련 __CHECKED_FILES__개 파일의 작업 코드·선택 코드·manifest 해시 일치를 확인했습니다. 실행 중 프로세스의 설정 재조회, 모델 호출, 72시나리오 실행, GENOS 현장 검증은 이번 작업에 포함하지 않았습니다.</p>
<p><a href="AGENT_LLM_INPUT_BLOCKS_WITH_LIMITS_UTF8.txt">전체 입력·판단 설명 TXT</a> · <a href="LIMITS_BY_LLM_BLOCK.csv">모든 항목·코드 위치 CSV</a> · <a href="SELECTED_PROFILE_ALL_FIELDS.csv">전체 선택 설정 CSV</a> · <a href="SOURCE_BOUND_CANDIDATES.csv">미분류 기계 검색 후보 CSV</a> · <a href="EVIDENCE.json">확인 근거 JSON</a></p>
<p>보고서와 설정 설명만 추가했습니다. 런타임 코드·제한값·MAIN 포인터는 변경하지 않았습니다. 기존 보고서는 보존했습니다.</p></footer>
</main><script>
const cards = [...document.querySelectorAll('.stage')];
for (const card of cards) {card.info = JSON.parse(card.querySelector('.card-data').textContent); const els=[...card.querySelectorAll('.limit')];els.forEach((el,i)=>el.search=JSON.stringify(card.info.entries[i]).toLocaleLowerCase());}
const query=document.querySelector('#query'), status=document.querySelector('#status'), result=document.querySelector('#result');
function filter(){let visible=0;const q=query.value.trim().toLocaleLowerCase();for(const card of cards){let n=0;for(const el of card.querySelectorAll('.limit')){const yes=(!q||el.search.includes(q))&&(status.value==='all'||el.dataset.status===status.value);el.hidden=!yes;if(yes){n++;visible++;if(q)el.open=true;}}const infoHit=q&&status.value==='all'&&(card.info.title+' '+card.info.info).toLocaleLowerCase().includes(q);card.hidden=!(n||infoHit);if(q&&!card.hidden)card.open=true;card.querySelector('.count').textContent=n+'항목';}const profile=document.querySelector('.profile');let pn=0;for(const tr of profile.querySelectorAll('tbody tr')){const yes=!q||tr.textContent.toLocaleLowerCase().includes(q);tr.hidden=!yes;if(yes)pn++;}profile.hidden=!!q&&!pn;if(q&&pn)profile.open=true;result.textContent=visible+' / __ENTRY_COUNT__ 항목'+(q?' · 프로필 '+pn+'필드':'');}
query.addEventListener('input',filter);status.addEventListener('change',filter);
document.querySelector('#expand').addEventListener('click',()=>{document.querySelectorAll('details').forEach(el=>{if(!el.hidden)el.open=true;});});
document.querySelector('#collapse').addEventListener('click',()=>{document.querySelectorAll('details').forEach(el=>el.open=false);});
for(const link of document.querySelectorAll('.jump a'))link.addEventListener('click',()=>{const card=document.querySelector(link.getAttribute('href'));card.hidden=false;card.open=true;});filter();
</script></body></html>'''
    replacements = {
        '__JUMPS__': ''.join(f'<a href="#b{i}">LLM {i}</a>' for i in range(1, 8)),
        '__CARDS__': ''.join(cards), '__PROFILE_COUNT__': str(len(profile_rows)),
        '__PROFILE_ROWS__': profile_html, '__ENTRY_COUNT__': str(len(rows)),
        '__CHECKED_FILES__': str(checked_files),
    }
    for key, value in replacements.items():
        page = page.replace(key, value)
    (out / 'AGENT_LLM_INPUT_BLOCKS_WITH_LIMITS.html').write_text(page, encoding='utf-8')
