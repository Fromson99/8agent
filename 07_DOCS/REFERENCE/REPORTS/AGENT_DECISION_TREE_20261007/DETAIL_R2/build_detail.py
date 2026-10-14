"""Build only report assets; never execute or mutate the RAG pipeline."""
from pathlib import Path
import csv
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE = HERE.parent

PHASES = [
    ('A', '입력·권한·실행 경로', '허용된 동일 요청을 정확한 실행 구성에 연결',
     '입력·인증·사건 소유권·코드/데이터/모델 binding 검증 후 B로 이동',
     '원 입력·요청 ID·사건 revision·권한 범위·binding',
     '두 진입 방식과 오류 분류는 기존 구현에 있다. 상세 실패 정보의 공통 전달은 후속 수정 목표다.'),
    ('B', '질문 분해·기존 사건·정정', '원 요청의 주체·행위·시점·범위를 쟁점 ID에 연결',
     '일반 규칙/사건 적용과 새 질문/정정/재개를 구분한 뒤 C 또는 사용자 확인',
     '원 요청·요구사항 ID·사건 관계·기존 근거·정정 이력',
     '기존 사건·revision과 INTENT가 있다. 경쟁 맥락 오판은 전달 실패와 모델 오류를 나누어 확인한다.'),
    ('C', '검색·후보 탐색·0건·실패', '허용 범위의 후보와 유효한 원문 읽기 경로를 확보',
     '후보 발견은 D로 이동; 0건·실패는 별도 관측으로 남기고 대안/복귀/중단을 선택',
     '검색식·문서/판본/권한 범위·결과 상태·후보·페이지·이전 성공 근거',
     '현재 반복 검색 제안은 거절될 수 있다. 그 뒤 원 화면 복구와 상세 중단 전달은 모든 분기에서 보장됐다고 할 수 없다.'),
    ('D', '원문 읽기·부분 전달·재열람', '정확한 원문·판본·확보 범위·실제 전달 범위를 확보',
     '실제 전달된 범위만 E/G의 근거로 사용; 미열람·실패 범위는 그대로 남김',
     '원문 ID·hash·좌표·확보/전달/채택 범위·읽기 영수증·성공/실패 대상',
     '읽기·전달 영수증과 저장 원문 재열람이 있다. 대형 입력의 상세 복구·모든 부분 실패는 추가 검증 대상이다.'),
    ('E', '채택·보류·제외·과거 화면 복귀', '자료와 쟁점의 선택 이유를 기록하고 유효 선택지를 유지',
     '읽기와 채택을 분리; RETURN_TO는 화면을 복원하며 이후 성공 자료·판단·예산은 유지',
     '자료별 결정·issue 연결·선택 이유·origin frame·이후 확보 자료·현재 판단',
     'ADOPT/DEFER/EXCLUDE/RETURN_TO가 있다. 복귀를 전체 상태 롤백으로 해석하지 않는다.'),
    ('F', '명시 참조·정의·예외·시행령', '질문에 필요한 연결은 확인하고 나머지는 이유와 함께 처리',
     '링크 존재만으로 필수화하지 않음; 필수 미해결은 G로 전달',
     '출발 span·참조 target·FOLLOW/SKIP/DEFER 이유·잔여 큐·원 메뉴·한도',
     '참조 메뉴·보류·한도 정보가 있다. 미해결의 영구 ID 장부와 모든 실패 복구는 후속 목표다.'),
    ('G', '쟁점별 판단·부족분·조사 종료', '해결/미해결과 전체/부분/답변 없음의 범위를 결정',
     'SELECT는 확보 자료·중단 이유를 보고; 답변 coverage는 ASSESS가 판단하고 게시 검증으로 이동',
     'issue/gap ID·중요도·근거·해결 이벤트·유효한 이전 claims·거절 출력·종료 이유',
     '현재 FINISH는 assessment_gaps를 제거한다. ASSESS의 제한 수정 실패도 재조사·부분 분기보다 먼저 예외로 끝난다.'),
    ('H', '모델·행동·도구 실패와 복구', '실패 제안과 실제 실행을 구분하고 기존 성과를 유지',
     '유효한 수정·대안이면 원단계 복귀; 한도·보호 경계면 명시적 중단',
     '원 단계·원 화면·허용 메뉴·실패 출력·시도 ID·수락 여부·기존 성공분',
     '현행 형식/행동 수정은 제한되어 있다. 현재 ASSESS는 최초 출력과 한 번 수정 후 실패하면 미완료 예외를 발생시킨다.'),
    ('I', '진전·예산·시간·중단·재개', '정확한 checkpoint와 누적 예산에서 중복 없이 계속 또는 중단',
     '권한·binding·revision·영수증·원 deadline·남은 예산이 모두 유효한 경우에만 재개',
     '최초 deadline·사용 예산·physical attempt·checkpoint·성공/실패/UNKNOWN·revision',
     'completion_budget.restore는 입력/binding·기한·물리 시도를 복원한다. 모든 미완료 예외에 재개가 자동 허용되는 것은 아니다.'),
    ('J', '게시·저장·사용자 표시·두 소비자', '검증한 결과와 조사 상태를 두 경로에 같은 의미로 전달',
     '원문·인용·권한·세대·revision·claims 일치 및 저장 상태 검증 후 사용자 결과 확정',
     '공통 결과 ID·본문 hash·인용·coverage·미해결·중단 사유·게시/저장/전달 영수증',
     'app.py는 LegalAgentError diagnostics를 다섯 필드로 축소한다. workflow.render는 오류 분기에서 일반 미완료 문구를 먼저 반환한다.'),
]

CURRENT = {
    'C07': '코드의 반복 검색 거절과 기존 REG-cm-039 관측을 연결했다. 원래 화면에서 재선택하도록 하는 일관된 복구는 수정 목표다.',
    'D07': 'completion 모드의 VIEW_SAVED_SOURCE는 delivery_requested를 켜고 delivery를 초기화하지만 보류/제외를 자동 채택하지 않는다.',
    'E04': 'RETURN_TO/restore는 화면 복귀 기능이다. 상세 트리도 이후 확보 자료·판단을 지우는 롤백을 제안하지 않는다.',
    'G05': 'completion_execution.py는 모순을 검사하고 한 번 수정한다. 수정도 실패하면 이후 actionable gap 분기에 도달하기 전 InvestigationPending을 발생시킨다.',
    'G06': '현재 수정 실패 예외는 resume_available=false다. 이 상세 트리의 이전 검증 성과·미해결·복구 정보 반환은 새 목표다.',
    'G07': "law_navigation.py의 FINISH 분기에 self.p.pop('assessment_gaps', None)이 있다. 영구 gap ID와 해결 이벤트 보존은 아직 목표다.",
    'G08': '기존 REG-IC24에서는 맥락이 전달됐는데 다른 맥락의 조항을 선택한 모델 판단 문제가 보고됐다. 이 문서에서 그 사례를 재실행하지 않았다.',
    'J03': '확보한 원문이 있어도 ASSESS 예외와 API 투영에서 사용자에게 조사 성과가 충분히 이어지지 않는 문제가 기존 검토에 기록되어 있다.',
    'J08': '현재 API 투영은 schema_version/stage/cause_codes/resume_available/stop_reason만 남긴다. 확보 자료·미해결·다음 행동의 공통 전달은 미구현 목표다.',
    'J09': '현재 두 소비자가 완료/부분/미완료/모델 장애를 분류한다. 상세 장부와 모든 실패 분기의 동일 표시는 추가 수정·검증이 필요하다.',
    'J10': '앞단 Socket.IO는 별도 담당 작업이다. 현재 Codex 세션은 GENOS에 접근하지 않으며 현장 검증 완료를 주장하지 않는다.',
}

COMMON = [
    {'id': 'issues', 'title': '미해결 장부 · 조사 종료는 해결 이벤트가 아님', 'fields': [
        ['OPEN', '아직 해결하지 못한 쟁점. 단계 이동·FINISH·복귀·재개에도 ID를 유지.'],
        ['RESOLVED', '관련 원문·사용자 사실 또는 정당한 재판단과 해결 이벤트를 연결. 의미상 정답은 별도 검토.'],
        ['DEFERRED', '나중에 판단할 쟁점. 보류 이유와 출발 화면 보존.'],
        ['NOT_REQUIRED', '현재 요청에 불필요하다는 모델 판단·이유·관련 범위를 보존. 질문 요구사항을 무단 삭제하지 않음.'],
        ['BLOCKED', '권한·도구·모델·예산 등으로 더 진행 불가. 실패 원인과 다음 조건 보존.'],
        ['중요도와 자료 상태', 'REQUIRED/OPTIONAL/UNDETERMINED와 미확보/확보/부분전달/전달완료를 별도로 기록.'],
        ['회귀 금지', '전체 링크를 강제 필수화하지 않음. 새 원문 없이도 합당한 범위 재판단은 허용하되 이유를 기록.']
    ]},
    {'id': 'recovery', 'title': '실패 복구 · 다음 행동을 결정하는 순서', 'fields': [
        ['1. 성공분 저장', '성공 원문·전달 영수증·채택·검증된 기존 판단을 실패 시도와 분리.'],
        ['2. 수락 여부 확인', '실행 전 거절 / 실제 실패 / 실제 성공 / UNKNOWN으로 구분. UNKNOWN을 미실행으로 추정하지 않음.'],
        ['3. 대안 확인', '원 화면·현재 유효 메뉴·대체 검색·다른 범위 읽기를 제시. 자동 채택하지 않음.'],
        ['4. 한도 확인', '선택된 수정/재시도 정책·누적 예산·최초 deadline·무진전 여부를 검사. 횟수·시간을 새로 부여하지 않음.'],
        ['5. 진행 또는 중단', '허용된 대안은 원단계로; 대안 없음/한도/보호 경계는 J의 공통 결과로.'],
        ['재개 표시', '체크포인트가 있다는 이유만으로 재개 가능을 표시하지 않음. 실제 사전조건·유효 handle이 확인된 경우만 available.']
    ]},
    {'id': 'result', 'title': '종료 결과 · 작업 상태와 답변 범위는 별도', 'fields': [
        ['완료 답변', '요청 범위의 필수 쟁점 해결 + 검증 통과. 답변 범위 COVERED.'],
        ['부분 답변', '검증된 일부 claims + 남은 쟁점. 답변 범위 PARTIAL이며 조사 중단/모델 장애도 함께 표시 가능.'],
        ['추가 입력 필요', '사용자 사실이 필요한 쟁점만 WAITING_USER. 원문 부족은 시스템 조사로 분류.'],
        ['범위 내 못 찾음', '정상 실행한 범위에서 NO_MATCH. 문서 부존재·법률상 근거 부존재로 단정하지 않음.'],
        ['조사·판단 미완료', '원문 확보가 있어도 확정 claims가 없으면 NONE. 조사 성과와 미해결을 표시.'],
        ['모델·도구 일시 장애', 'FAILED/UNKNOWN의 실제 상태를 보존. 이미 검증된 답변 범위는 별도 검사.'],
        ['게시 안전 중단', '권한·원문·해시·revision·인용 검증 실패는 게시 차단. 조사 상태는 공개 가능한 범위로 별도 반환.'],
        ['저장과 전달', '게시 정본 저장 완료 / 내보내기 실패 / 전달 실패를 나누며 검증된 정본을 중복 생성하지 않음.']
    ]},
    {'id': 'display', 'title': '두 경로의 공통 사용자 결과 · 무엇을 반드시 보여줄까', 'fields': [
        ['확정된 답변 범위', '어느 쟁점을 답했는지, 조건·판본·인용 근거.'],
        ['확보 자료', '허용된 원문 제목·좌표·읽은 범위의 요약. 후보 제목만 본 경우는 미열람으로 구분.'],
        ['미해결 쟁점', '같은 issue/gap ID·중요도·부족한 원문/사실·답변에 미치는 영향.'],
        ['중단 이유', '못 찾음·도구 실패·모델 오류·무진전·예산·시간·권한·게시 충돌 구분.'],
        ['다음 행동', '원 화면 재선택·저장 원문 재열람·추가 사실·재검증·운영 복구·새 요청 중 실제 가능한 행동.'],
        ['공개 범위', '두 방식 모두 같은 권한 필터를 적용. 내부 경로·인증키·다른 사용자 자료는 표시하지 않음.']
    ]},
    {'id': 'quantity', 'title': '정보량·저장량 · 확보와 실제 전달을 분리', 'fields': [
        ['원문', '전체 범위 / 확보 범위 / 현재 제시 범위 / 채택 span / 잔여 범위 구분.'],
        ['후보·참조·이력', '전체 건수 / 제시 건수 / 생략 건수 / 다음 페이지·조회 경로 기록.'],
        ['입력 한도', '필수 원문·미해결 ID가 빠졌는지 확인. 추가 조회도 불가하면 그 한계를 답변에 표시.'],
        ['저장 정책', '동일 원문·캐시는 hash로 공유. 원시 실패 기록은 무손실 압축·hash·복원 방법을 보존.'],
        ['비용·지연 목표', '이번에는 모델 호출 0. 상세 장부의 토큰·저장량·지연 변화는 미측정이며 구현 후 동일 실행 기준으로 측정.']
    ]},
    {'id': 'adoption', 'title': '도입·검증 경계 · 문서와 실행 완료를 구분', 'fields': [
        ['지금 수행한 일', '기존 72개 시나리오를 상세 목표 분기로 확장하고 실제 코드의 주요 차이를 다시 확인. 제품 코드 변경·외부 호출 없음.'],
        ['후속 구현', '기존 공통 엔진에 ID 장부·실패 결과·두 소비자 표시를 통합. 원문/용어집 재구축 필요 여부는 실제 의존성으로 다시 확인.'],
        ['동일 코드 검증', '영수증·장부·DB·출력·중복/권한/binding/기한을 상태 전이 fixture와 두 소비자에서 대조. 이번 상세 가지는 미실행.'],
        ['MAIN 반영', '해당 실험 규정에 따른 격리·기준 동결·검증·승격과 선택 포인터·실제 로컬 service binding을 확인.'],
        ['GENOS', '코드 반입·편집기 반영·generation·push·리비전 배포·워크플로우 테스트의 현장 로그를 별도 확인.'],
        ['롤백', '이전 코드/결과 계약·선택 릴리스·스키마 판독 경로를 보존. legacy 상태를 근거 없이 RESOLVED로 보정하지 않음.']
    ]},
]

ROUTES = {key: f'{key}. {title}' for key, title, *_ in PHASES}
ROUTES.update({
    'END': '사용자 결과 확정 — 완료/부분/미완료/거절은 해당 분기 설명에 따름',
    'WAIT': '사용자 입력 대기 — 기존 사건·근거 보존 후 답을 받으면 B에서 연결',
    'OPS': '운영·무결성 복구 대기 — J의 공개 상태 반환, 복구 후 A부터 재검증',
    'RETURN': '원단계 복귀 — 저장된 origin frame의 현재 유효 메뉴에서 재선택',
})

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    with (BASE / 'SCENARIOS.csv').open(encoding='utf-8-sig', newline='') as handle:
        cases = list(csv.DictReader(handle))
    assert len(cases) == 72
    by_id = {row['id']: row for row in cases}
    branches = {}
    current = None
    for line in (HERE / 'BRANCHES_UTF8.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        if line.startswith('@'):
            current = line[1:].strip()
            assert current in by_id and current not in branches, current
            branches[current] = []
            continue
        values = line.split('|')
        assert len(values) == 5 and current is not None, line
        when, action, target, visible, saved = values
        assert target in ROUTES, (current, target)
        branches[current].append(dict(when=when, action=action, next=target, visible=visible, saved=saved))
    assert set(branches) == set(by_id)
    phase_data = []
    flat = []
    for key, title, goal, exit_rule, preserve, note in PHASES:
        phase_cases = []
        for old in cases:
            if not old['id'].startswith(key):
                continue
            new = {**old, 'current_note': CURRENT.get(old['id'], '')}
            new['branches'] = []
            assert len(branches[old['id']]) >= 2
            for i, branch in enumerate(branches[old['id']], 1):
                value = {**branch, 'id': f"{old['id']}-{i:02d}",
                    'preserve': preserve + '；' + branch['saved']}
                value['check'] = ('해당 분기 입력·실행 영수증·장부·다음 메뉴·두 경로의 표시를 대조. '
                    '실패를 0건/성공/전체 완료로 바꾸지 않고, 미해결·권한·누적 예산·최초 기한을 유지.')
                new['branches'].append(value)
                flat.append({'branch_id': value['id'], 'scenario_id': old['id'], 'phase': key,
                    'condition': old['condition'], 'branch_condition': value['when'],
                    'desired_result': value['action'], 'preserve': value['preserve'],
                    'next': ROUTES[value['next']], 'user_display': value['visible'],
                    'baseline_evidence': old['evidence'], 'verification_status': '목표 분기 / 실행 검증 전'})
            phase_cases.append(new)
        phase_data.append(dict(id=key, title=title, goal=goal, exit=exit_rule,
                               preserve=preserve, current_note=note, cases=phase_cases))
    active_path = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    pointer = json.loads(active_path.read_text())
    manifest_path = ROOT / pointer['manifest_path']
    release = json.loads(manifest_path.read_text())
    assert sha(manifest_path) == pointer['release_manifest_sha256']
    checked_files = [
        '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py',
        '02_BACKEND/semantic_runtime/legal_agent/completion_execution.py',
        '02_BACKEND/semantic_runtime/legal_agent/completion_budget.py',
        '02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py',
        '02_BACKEND/semantic_runtime/app.py',
        '02_BACKEND/semantic_runtime/chat_adapter.py',
        '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',
        'service.py',
    ]
    code_evidence = []
    for rel in checked_files:
        work = ROOT / rel
        selected = ROOT / release['code_root'] / rel
        expected = release['files'].get(rel)
        code_evidence.append(dict(path=rel, working_sha256=sha(work),
            selected_sha256=sha(selected) if selected.is_file() else None,
            manifest_sha256=expected,
            selected_matches_manifest=selected.is_file() and sha(selected) == expected,
            working_equals_selected=selected.is_file() and sha(work) == sha(selected)))
    payload = dict(revision='agent-decision-tree-detail-20261007-r2',
        phases=phase_data, routes=ROUTES, common=COMMON,
        counts=dict(phases=len(phase_data), scenarios=len(cases), branches=len(flat)),
        status='design_only_not_executed', active_release=pointer['release_id'],
        active_generation=pointer['generation'])
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    fragment_path = HERE / 'decision-tree-detail.html'
    template_path = HERE / 'decision-tree-detail.template.html'
    if not template_path.exists():
        template_path.write_text(fragment_path.read_text())
    template = template_path.read_text()
    assert template.count('__TREE_DATA__') == 1
    fragment_path.write_text(template.replace('__TREE_DATA__',encoded.replace('</','<\\/')))
    with (HERE / 'DETAIL_BRANCHES.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer = csv.DictWriter(handle,fieldnames=list(flat[0]))
        writer.writeheader();writer.writerows(flat)
    lines = [
        '에이전트 상세 의사결정 트리 — 2026-10-07 R2',
        f"구조: {len(phase_data)}개 구간 / 기존 {len(cases)}개 상황 / 상세 {len(flat)}개 목표 분기",
        '상태: 설계 상세화. 후속 제품 코드 구현·외부 모델 호출·상세 분기 실행·MAIN 승격 없음.',
        f"선택 포인터: {pointer['release_id']} / generation {pointer['generation']}. manifest 해시 확인.",
        '기존 36개 계약 검사 + HTTP 오류 전달 2개는 이전 검토 기록이다. 이번에 재실행하지 않았다.',
        '이 상세 가지들의 상태는 모두 실행 검증 전이다. 수는 법률 사례 수나 테스트 통과 수가 아니다.',
        'GENOS 현장 미검증. 앞단 Socket.IO는 별도 담당 작업. 두 실행 방식을 유지한다.',
        '원문·모델 입출력은 복제하지 않고 기존 기록과 코드의 경로·해시만 연결한다.',
        '',
        '전체 연결: 통합 /chat ─┐',
        '                      ├─ 공통 에이전트 엔진',
        '별도 워크플로우 ─────┘',
        'A 입력 → B 질문/사건 → C 검색 → D 원문 → E 선택/복귀 → F 참조 → G 판단 → J 게시/표시',
        'H 오류 복구와 I 한도/재개는 모든 단계에 연결된다.',
        '모든 전이: 실행 전 상태 → 시도 ID → 실제 영수증 → 저장 → 다음 메뉴.',
        '',
    ]
    for phase in phase_data:
        lines.extend([f"{phase['id']}. {phase['title']}",
            f"  원하는 결과: {phase['goal']}", f"  다음 단계 조건: {phase['exit']}",
            f"  현재 구현 주의점: {phase['current_note']}"])
        for position, row in enumerate(phase['cases']):
            last = position == len(phase['cases'])-1
            lead = '└─' if last else '├─'
            prefix = '   ' if last else '│  '
            lines.extend([f"  {lead} {row['id']} {row['condition']}",
                f"  {prefix}  공통 목표: {row['expected']}",
                f"  {prefix}  기존 기록 근거: {row['evidence']} / {row['source']}",
                f"  {prefix}  현재 차이: {row['current_note'] or phase['current_note']}"])
            for j, branch in enumerate(row['branches']):
                marker = '└─' if j == len(row['branches'])-1 else '├─'
                tail = '   ' if j == len(row['branches'])-1 else '│  '
                lines.extend([
                    f"  {prefix}  {marker} [{branch['id']}] {branch['when']}",
                    f"  {prefix}  {tail} ├─ 목표 처리: {branch['action']}",
                    f"  {prefix}  {tail} ├─ 보존: {branch['preserve']}",
                    f"  {prefix}  {tail} ├─ 다음: {ROUTES[branch['next']]}",
                    f"  {prefix}  {tail} └─ 사용자 표시: {branch['visible']}",
                ])
        lines.append('')
    lines.append('전 단계 공통 규칙')
    for item in COMMON:
        lines.append('  ├─ '+item['title'])
        for title,text in item['fields']:
            lines.append(f'  │  ├─ {title}: {text}')
    lines.extend(['','주요 기존→목표 비교',
        '1. FINISH에서 assessment_gaps 제거 + REG-NG13 기존 관측 → ID별 상태·해결/범위 재판단 이벤트 유지 → 해결 기록 없는 필수 쟁점이 사라지지 않는지 검사.',
        '2. ASSESS 최초+1회 수정 실패 시 예외 + H05/H10 기존 관측 → 이전 검증 claims·조사 성과 보존, 새 실패 초안은 미게시 → 근거 없는 주장 없이 성과가 표시되는지 검사.',
        '3. SELECT와 ASSESS의 충분성 판단 충돌 + REG-NG13 기존 관측 → SELECT는 확보/중단 보고, ASSESS는 답변 coverage → 동일 gap의 상태 변화·무진전 중단 검사.',
        '4. API diagnostics 5필드 축약 + 일반 미완료 전달 → 권한 필터가 적용된 공통 조사/실패 결과 → 통합 JSON/SSE·별도 workflow의 정보 의미 대조.',
        '5. 반복 행동 거절 뒤 bounded stop + REG-cm-039 기존 관측 → 원 화면·유효 메뉴·이후 성과 유지 → 다른 행동 선택과 한도 종료를 함께 검사.',
        '6. 경쟁 맥락 정보 전달 후 오판 + REG-IC24 기존 관측 → 선택 이유·입력·근거 보존과 쟁점 정정 → 시스템 전달 문제와 의미 오판을 구분.',
        '7. 이력/연결 카드 한도 코드 존재, 직접 실패 원인 여부는 미확인 → 확보/제시/생략량·추가 조회 경로 → 큰 입력에서 미해결·근거가 무음 유실되지 않는지 검사.',
        '', '검증·도입 방법(아직 수행하지 않은 목표)',
        '같은 분기 입력에서 실제 메뉴·모델 제안·실행 영수증·DB·공통 결과·두 소비자 표시를 대조한다.',
        '실패의 성공 처리, 미해결 무설명 유실, 권한/인용/해시 위반, 두 소비자의 의미 차이를 막는다.',
        '후속 실제 비교 실험은 저장소 실험 규정에 따라 ADR 예약·동결·격리 후 수행한다.',
        '통합 코드 → 동일 코드 검증 → MAIN 배선/승격 → 포인터 → 실제 로컬 service binding → 별도 GENOS 반입/배포/현장 확인.',
        '상태 스키마는 새 버전으로 이행한다. legacy 미확정 상태를 추측해 해결 처리하지 않으며 이전 판독·롤백 경로를 보존한다.',
        '성능·비용·저장량·일정 개선 수치는 미산정. 구현 후 입력 토큰·조회·호출·지연·DB 증가량을 계측한다.',
        '', '근거 해시 및 현재 작업 코드/선택 릴리스 비교'])
    for evidence in code_evidence:
        lines.append(json.dumps(evidence,ensure_ascii=False))
    (HERE / 'AGENT_DECISION_TREE_DETAIL_UTF8.txt').write_text('\n'.join(lines)+'\n')
    evidence = dict(schema_version='agent-tree-detail-evidence-v1',
        active_pointer={'path':str(active_path.relative_to(ROOT)), 'sha256':sha(active_path),
                        'release_id':pointer['release_id'],'generation':pointer['generation']},
        manifest={'path':pointer['manifest_path'],'sha256':sha(manifest_path),'hash_verified':True},
        source_scenarios={'path':str((BASE/'SCENARIOS.csv').relative_to(ROOT)), 'sha256':sha(BASE/'SCENARIOS.csv')},
        baseline_report={'path':str((BASE/'AGENT_DECISION_TREE_UTF8.txt').relative_to(ROOT)),
                         'sha256':sha(BASE/'AGENT_DECISION_TREE_UTF8.txt')},
        code_evidence=code_evidence,counts=payload['counts'],
        verification={'document_integrity':'built_and_structurally_checked',
                      'branch_execution':'not_executed','external_model_calls':0,
                      'genos_execution':'not_accessed','main_change':False})
    (HERE/'EVIDENCE.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'counts':payload['counts'],'fragment_bytes':fragment_path.stat().st_size,
        'code_matches':[(e['path'],e['working_equals_selected'],e['selected_matches_manifest']) for e in code_evidence]},ensure_ascii=False))

if __name__ == '__main__':
    main()
