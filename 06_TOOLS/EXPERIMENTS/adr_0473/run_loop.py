"""ADR-0473 runner: legal_agent 탐색 루프 rev-004(C1~C5) on CM 51 (공개 출처 문서만), ADR-0462 채점 계약.

모델을 부르거나 부를 설정을 정하는 단계만 여기 둔다. 집계·질문 파일·단계 원장은 report.py·build_ledger.py.

    .venv/bin/python <this> selftest     # S0-a 가짜 모델로 C1·C2·C3·C4 경로 → s0-selftest.json
    .venv/bin/python <this> trajectory   # S0-b ADR-0472 기록 결정을 rev-004 루프(C4 끔)로 재생 → s0-trajectory-replay.json
    .venv/bin/python <this> audit        # S0-c 동결 C4 규칙을 ADR-0472 채택에 적용·사전 탐침 값 대조·S1 표본 → s0-c4-audit.json
    .venv/bin/python <this> freeze       # frozen-inputs.json (S0 세 검사 통과가 조건)
    .venv/bin/python <this> replay       # S1 run-001: s1-{flash,qwen}-{control,pairs}
    .venv/bin/python <this> judge s1     # S1 답 채점
    .venv/bin/python <this> gate         # S1-G 판정 → s1-gate.json
    .venv/bin/python <this> run          # S2 run-002·run-003 (S1-G 결과로 loop4-flash의 C4를 정한다)
    .venv/bin/python <this> judge s2     # S2 답 + 참고 arm 3개(같은 배치)

S0 세 명령은 후보 동결 전 점검용으로 --dev --out <scratch 디렉터리>를 받아 수정 중인 snapshot을 쓸 수 있다(산출물은 artifacts에 쓰지 않는다).
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
sys.dont_write_bytecode = True
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0473-legal-agent-loop-rev4'
ART = ADR / 'artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0473/legal-loop-v4'
REVISION = 'rev-001'
FROZEN = CAND / 'revisions' / REVISION / 'snapshot/02_BACKEND'
DEV = '--dev' in sys.argv
sys.path.insert(0, str(ROOT / '02_BACKEND'))
sys.path.insert(0, str(CAND / 'snapshot/02_BACKEND') if DEV else str(FROZEN))

GEN = ROOT / '01_DATA/SEMANTIC/GENERATIONS/navigation-source-20260918-body-v1'
PROJECTION = ROOT / '01_DATA/PROJECTIONS/document-origins/term-source-adca5fbe3650f90fb372.json'
LAW_ROOT = ROOT / '01_DATA/RAW/law'
ADR72 = ROOT / '04_EXPERIMENTS/ADR/ADR-0472-legal-agent-loop-rev3/artifacts'
ADR69 = ROOT / '04_EXPERIMENTS/ADR/ADR-0469-legal-agent-loop-rev2/artifacts'
ADR62 = ROOT / '04_EXPERIMENTS/ADR/ADR-0462-cm-golden-answer-correctness-regrade/artifacts'
STRONG = {'quoted', 'declared_alias', 'declared_alias_decree', 'corpus_name', 'already_resolved', 'cue_override',
          'same_document'}
SOURCE_ARMS = {'loop3-flash': 'flash-lite-exp', 'loop3-qwen': 'genos-qwen-proxy'}      # ADR-0472 arm → 프로파일
S1_ARMS = {'s1-flash': 'loop3-flash', 's1-qwen': 'loop3-qwen'}
S2_RUNS = ['run-002', 'run-003']
REFERENCE = {'ref-loop3-flash': (ADR72, 'loop3-flash'), 'ref-loop3-qwen': (ADR72, 'loop3-qwen'),
             'ref-loop2c-qwen': (ADR69, 'loop2c-qwen')}
TARGETS = ['cm-003', 'cm-008', 'cm-014']
EXPECTED_C4 = {'loop3-flash': {'pairs': 23, 'cases': 20, 'decisive': 6},
               'loop3-qwen': {'pairs': 25, 'cases': 22, 'decisive': 1}}       # 사전 탐침(설계 동결 값)
ORDER_SEED = 4730
WORKERS = 4
LOCK = threading.Lock()


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read(path: Path):
    return json.loads(Path(path).read_text())


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + '\n')
    tmp.replace(path)


def out_dir() -> Path:
    """S0 산출물 위치. --dev면 --out 디렉터리(artifacts 금지)."""
    if not DEV:
        return ART
    out = Path(sys.argv[sys.argv.index('--out') + 1]).resolve()
    if out.is_relative_to(ADR.resolve()):
        raise SystemExit('--dev output must not be inside the ADR directory')
    return out


def check_candidate() -> dict:
    """legal_agent가 동결 revision에서 왔고 파일이 동결 hash와 같은지 확인한다(fail closed)."""
    import legal_agent
    here = Path(legal_agent.__file__).resolve()
    manifest = read(CAND / 'candidate.json')
    revision = next((r for r in manifest['revisions'] if r['revision_id'] == REVISION), None)
    if DEV:
        return {'dev_snapshot': str(here.parent.relative_to(ROOT)), 'revision_id': None}
    if revision is None or not here.is_relative_to(FROZEN.resolve()):
        raise SystemExit(f'legal_agent must come from frozen {REVISION}: {here}')
    for row in revision['files']:
        if sha(ROOT / row['frozen_path']) != row['snapshot_sha256']:
            raise SystemExit(f"frozen file drifted: {row['frozen_path']}")
    return {'revision_id': REVISION, 'revision_sha256': revision['revision_sha256'],
            'candidate_json_sha256': sha(CAND / 'candidate.json')}


def check_client_pin() -> dict:
    frozen = (CAND / 'snapshot/02_BACKEND' if DEV else FROZEN) / 'lawrag/research/experiment_client.py'
    live = ROOT / '02_BACKEND/lawrag/research/experiment_client.py'
    if sha(frozen) != sha(live):
        raise SystemExit('experiment_client drifted from the frozen revision; refuse to run')
    return {'frozen': str(frozen.relative_to(ROOT)), 'sha256': sha(frozen)}


def shared(with_locator: bool):
    from legal_agent.harness import PUBLIC_ORIGINS
    from legal_agent.index import LegalIndex
    from legal_agent.locator import Locator, official_abbreviations
    from legal_agent.references import ReferenceResolver
    from legal_agent.replay import origin_prefixes
    index = LegalIndex(GEN / 'store.sqlite')
    resolver = ReferenceResolver(index, GEN / 'navigation/navigation.sqlite')
    edges = resolver.edges([r for r in resolver.resolve_all() if r.via in STRONG])
    reverse: dict[str, set[str]] = {}
    for source, targets in edges.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    origins = origin_prefixes(PROJECTION)
    allowed = {d for d in index.documents if origins.get(d) in PUBLIC_ORIGINS}
    locator = Locator(index, official_abbreviations(LAW_ROOT), allowed) if with_locator else None
    return index, edges, reverse, origins, allowed, locator


def visible_in(index, allowed):
    def visible(sid: str) -> bool:
        article = index.article(sid)
        return article is not None and article.document_id in allowed
    return visible


def label(index, sid: str) -> str:
    article = index.article(sid)
    return f'{article.document_name} {article.label}'.strip() if article else sid


def interleave(evidence: list[str], pairs: list[dict]) -> list[str]:
    """루프와 같은 순서: 채택 조문 바로 뒤에 그 짝."""
    out: list[str] = []
    for sid in evidence:
        out.append(sid)
        out += [p['child'] for p in pairs if p['parent'] == sid]
    return out


def units_for(index, origins, sids: list[str], chars: int = 6000):
    from legal_agent.contracts import EvidenceUnit
    units = []
    for i, sid in enumerate(sids, start=1):
        article = index.article(sid)
        units.append(EvidenceUnit(handle=f'E{i}', source_id=sid, document_id=article.document_id,
                                  document_name=article.document_name, heading=article.heading,
                                  text=article.text()[:chars], origin=origins.get(article.document_id, 'unknown')))
    return units


class Scripted:
    """가짜 모델: step(system, data, schema, phase) → 결정. 호출 원문을 모두 남긴다."""

    def __init__(self, step):
        self.step, self.calls, self.log = step, 0, []

    def generate(self, system, data, schema, phase):
        self.calls += 1
        out = self.step(system, data, schema, phase)
        self.log.append({'phase': phase, 'data': data, 'output': out})
        return out


def empty(**kw) -> dict:
    return {'adopt': [], 'drop': [], 'expand': [], 'open': [], 'search': [], 'done': True, **kw}


# ── S0-a 가짜 모델 단위 검사 ─────────────────────────────────────────────
def selftest() -> None:
    from legal_agent.loop import Loop
    from legal_agent.profiles import PROFILES, loop_config
    from legal_agent.search import Search
    cand = check_candidate()
    index, edges, reverse, origins, allowed, locator = shared(True)
    search = Search(GEN, allowed, index)
    questions = {c['case_id']: c['question'] for c in read(ADR72 / 'frozen-inputs.json')['cases']}
    flash, qwen = PROFILES['flash-lite-exp'], PROFILES['genos-qwen-proxy']
    tests = []

    def loop_for(model, **override):
        return Loop(index, search, edges, origins, allowed, model, loop_config(flash, **override),
                    reverse_edges=reverse, locator=locator)

    def check(name, condition, detail):
        tests.append({'test': name, 'passed': bool(condition), 'detail': detail})

    # T1 C1: 목록 핸들 채택 = 열고 채택, 목록 핸들 drop = 다음 라운드부터 목록에서 빠짐
    state = {}

    def t1(system, data, schema, phase):
        if phase.endswith('-compose'):
            return {'answer': '테스트 [E1]'}
        if phase.endswith('-r1'):
            state['adopt'], state['drop'] = data['listing'][0]['handle'], data['listing'][1]['handle']
            return empty(adopt=[state['adopt']], drop=[state['drop']], done=False)
        state.setdefault('later', []).append([x['handle'] for x in data['listing']])
        return empty()
    model = Scripted(t1)
    out = loop_for(model, delegation_pairs=False).run(questions['cm-048'], phase='t1')
    r1 = next(t for t in out['trace'] if t.get('round') == 1)
    card = next((c for c in out['cards'] if c['via'] == '목록 채택'), None)
    check('T1 목록 채택 카드 생성·채택', card is not None and card['adopted'] and r1['listing_adopted'] == [card['handle']],
          {'card': card and {k: card[k] for k in ('handle', 'label', 'via', 'adopted')}, 'round1': {k: r1[k] for k in (
              'listing_adopted', 'listing_dropped', 'unknown_handles', 'added_cards')}})
    check('T1 목록 채택 카드는 새 카드(done 보류 사유)로 세지 않음', card is not None and card['handle'] not in r1['added_cards'],
          r1['added_cards'])
    check('T1 목록 핸들 drop은 목록에서 빠지고 모르는 핸들이 아님',
          r1['listing_dropped'] == [state['drop']] and not r1['unknown_handles']
          and all(state['drop'] not in later and state['adopt'] not in later for later in state.get('later', [])),
          {'dropped': state['drop'], 'later_listing_heads': [x[:5] for x in state.get('later', [])]})
    check('T1 근거에 목록 채택 조문', card is not None and card['source_id'] in out['evidence_source_ids'] and not out['fallback'],
          out['evidence_source_ids'])

    # T2 C1: 같은 목록 핸들을 open과 adopt에 함께 → 한 번만 꺼냄
    def t2(system, data, schema, phase):
        if phase.endswith('-compose'):
            return {'answer': '테스트 [E1]'}
        if phase.endswith('-r1'):
            h = data['listing'][0]['handle']
            return empty(adopt=[h], open=[h], done=False)
        return empty()
    out = loop_for(Scripted(t2), delegation_pairs=False).run(questions['cm-023'], phase='t2')
    r1 = next(t for t in out['trace'] if t.get('round') == 1)
    listed = [c for c in out['cards'] if c['via'] in ('목록 채택', '목록 열기')]
    check('T2 open+adopt 같은 핸들 → 카드 1장(목록 채택)·꺼냄 1',
          len(listed) == 1 and listed[0]['via'] == '목록 채택' and listed[0]['adopted'] and r1['listing_taken_total'] == 1
          and not r1['unknown_handles'], {'cards': [(c['handle'], c['via']) for c in listed], 'round1': r1['listing_taken_total']})

    # T3 C3: 라운드당 4, 총량 8에서 목록 닫힘, 닫힌 뒤 목록 핸들은 모르는 핸들
    seen = {}

    def t3(system, data, schema, phase):
        if phase.endswith('-compose'):
            return {'answer': '테스트 [E1]'}
        if phase.endswith('-final'):
            return {'adopt': []}
        r = int(phase.rsplit('-r', 1)[1])
        seen[r] = [x['handle'] for x in data['listing']]
        if r == 1:
            return empty(open=seen[r][:6], done=False)
        if r == 2:
            return empty(open=seen[r][:4], done=False)
        return empty(open=['L30'], done=True)
    out = loop_for(Scripted(t3), delegation_pairs=False).run(questions['cm-019'], phase='t3')
    tr = {t['round']: t for t in out['trace'] if t.get('step') == 'round'}
    check('T3 라운드당 꺼내기 4(초과 2개 거절)', len(tr[1]['listing_opened']) == 4 and len(tr[1]['listing_refused']) == 2,
          {k: tr[1][k] for k in ('listing_opened', 'listing_refused', 'listing_taken_total')})
    check('T3 총량 8에서 목록 닫힘', tr[2]['listing_taken_total'] == 8 and tr[2]['listing_closed'] and seen.get(3) == [],
          {'taken': tr[2]['listing_taken_total'], 'closed': tr[2]['listing_closed'], 'round3_listing': seen.get(3)})
    check('T3 닫힌 뒤 목록 핸들은 모르는 핸들', 3 in tr and tr[3]['unknown_handles'] == ['L30'], tr.get(3, {}).get('unknown_handles'))

    # T4 C2: 채택 0 → 마지막 고르기(버린 카드 포함 전부) → 고른 카드가 근거
    final_seen = {}

    def t4(system, data, schema, phase):
        if phase.endswith('-compose'):
            return {'answer': '테스트 [E1]'}
        if phase.endswith('-final'):
            final_seen['handles'] = [c['handle'] for c in data['cards']]
            return {'adopt': [data['cards'][2]['handle'], 'L3', 'C999']}
        return empty(drop=[c['handle'] for c in data['cards']])
    model = Scripted(t4)
    out = loop_for(model, delegation_pairs=False).run(questions['cm-019'], phase='t4')
    final = next((t for t in out['trace'] if t.get('step') == 'final_pick'), {})
    third = out['cards'][2]
    check('T4 마지막 고르기: 버린 카드 포함 전부 표시',
          out['final_pick'] and final_seen.get('handles') == [c['handle'] for c in out['cards']]
          and final.get('dropped_shown') == len(out['cards']),
          {'shown': len(final_seen.get('handles', [])), 'cards': len(out['cards']), 'dropped_shown': final.get('dropped_shown')})
    check('T4 고른 카드가 근거·대체 아님·모르는 핸들 기록',
          out['evidence_source_ids'] == [third['source_id']] and not out['fallback']
          and final.get('unknown_handles') == ['L3', 'C999'] and third['adopted'],
          {'evidence': out['evidence_source_ids'], 'final': {k: final.get(k) for k in ('adopted', 'unknown_handles')}})

    # T5 C2: 마지막 고르기도 비면 기존 대체(질문 지목·FTS 상위 2)
    def t5(system, data, schema, phase):
        if phase.endswith('-compose'):
            return {'answer': '테스트 [E1]'}
        if phase.endswith('-final'):
            return {'adopt': []}
        return empty(drop=[c['handle'] for c in data['cards']])
    out = loop_for(Scripted(t5), delegation_pairs=False).run(questions['cm-019'], phase='t5')
    expected = [c['source_id'] for c in out['cards'] if c['via'].startswith(('질문 지목', 'FTS'))][:2]
    check('T5 빈 마지막 고르기 → 기존 대체', out['fallback'] and out['final_pick'] and out['evidence_source_ids'] == expected,
          {'fallback': out['fallback'], 'evidence': out['evidence_source_ids']})

    # T6 C4: 코스닥시장 상장규정 제13조 채택 → 시행세칙 제15조가 바로 뒤 근거(채택 아님), 끄면 없음
    target = '코스닥시장 상장규정 제13조'

    def t6_factory(log):
        def t6(system, data, schema, phase):
            if phase.endswith('-compose'):
                log['evidence'] = [e['label'] for e in data['evidence']]
                return {'answer': '테스트 [E1]'}
            for c in data['cards']:
                if c['label'] == target:
                    return empty(adopt=[c['handle']])
            for x in data['listing']:
                if x['label'] == target:
                    return empty(adopt=[x['handle']])
            return empty(search=[target], done=False)
        return t6
    log_on, log_off = {}, {}
    on = loop_for(Scripted(t6_factory(log_on)), delegation_pairs=True).run(questions['cm-008'], phase='t6')
    off = loop_for(Scripted(t6_factory(log_off)), delegation_pairs=False).run(questions['cm-008'], phase='t6off')
    child = '코스닥시장 상장규정 시행세칙 제15조'
    pair_labels = [(label(index, p['parent']), label(index, p['child']), p['rank']) for p in on['paired']]
    first = pair_labels[0] if pair_labels else None
    check('T6 위임 짝: 제13조 → 시행세칙 제15조, 부모 바로 뒤, 채택 목록 밖',
          first is not None and first[:2] == (target, child) and first[2] <= 40
          and log_on.get('evidence', [])[:2] == [target, child]
          and on['paired_source_ids'][0] not in on['adopted_source_ids'],
          {'pairs': pair_labels, 'compose_evidence': log_on.get('evidence'), 'adopted': [label(index, s) for s in on['adopted_source_ids']]})
    check('T6 위임 짝 끔 → 짝 없음', off['paired'] == [] and child not in log_off.get('evidence', []),
          {'compose_evidence': log_off.get('evidence')})

    # T7 C5: 프로파일 값
    cf, cq = loop_config(flash), loop_config(qwen)
    try:
        loop_config(flash, no_such_setting=1)
        rejected = False
    except ValueError:
        rejected = True
    check('T7 프로파일 → LoopConfig', (cf.composer_rules, cf.delegation_pairs, cf.listing_take_limit, cf.final_pick) == ('v2', True, 8, True)
          and (cq.composer_rules, cq.delegation_pairs, cq.listing_take_limit) == ('v3', False, 8) and rejected,
          {'flash': [cf.composer_rules, cf.delegation_pairs, cf.listing_take_limit], 'qwen': [cq.composer_rules, cq.delegation_pairs, cq.listing_take_limit]})

    result = {'schema_version': 'adr0473-s0-selftest-v1', 'candidate': cand, 'passed': all(t['passed'] for t in tests),
              'tests': tests, 'model_calls': 0}
    write(out_dir() / 's0-selftest.json', result)
    for t in tests:
        print(('PASS ' if t['passed'] else 'FAIL ') + t['test'])
    print('selftest', 'passed' if result['passed'] else 'FAILED')


# ── S0-b ADR-0472 기록 결정 재생 ─────────────────────────────────────────
def trajectory() -> None:
    """기록된 모델 결정을 그대로 rev-004 루프(C1~C3 켬, C4 끔)에 넣는다. C1~C3가 건드리지 않은 문항은 카드·채택·근거가 같아야 한다."""
    from legal_agent.loop import Loop
    from legal_agent.profiles import PROFILES, loop_config
    from legal_agent.search import Search
    cand = check_candidate()
    index, edges, reverse, origins, allowed, locator = shared(True)
    search = Search(GEN, allowed, index)
    frozen72 = read(ADR72 / 'frozen-inputs.json')
    loops72 = read(ADR72 / 'loop-results.json')['results']
    rows = {}
    for arm, profile_name in SOURCE_ARMS.items():
        for case in frozen72['cases']:
            cid = case['case_id']
            rec = loops72[f'{cid}::{arm}::run-001']
            decisions = [t['decision'] for t in rec['trace'] if t.get('step') == 'round']

            def step(system, data, schema, phase, decisions=decisions):
                if phase.endswith('-compose'):
                    return {'answer': '재생'}
                if phase.endswith('-final'):
                    return {'adopt': []}
                r = int(phase.rsplit('-r', 1)[1])
                return decisions[r - 1] if r <= len(decisions) else empty()
            out = Loop(index, search, edges, origins, allowed, Scripted(step),
                       loop_config(PROFILES[profile_name], delegation_pairs=False),
                       reverse_edges=reverse, locator=locator).run(case['question'], phase=f'traj-{cid}')
            old_rounds = [t for t in rec['trace'] if t.get('step') == 'round']
            new_rounds = [t for t in out['trace'] if t.get('step') == 'round']
            old_unknown_open = {(t['round'], h) for t in old_rounds for h in t['decision'].get('open') or []
                                if h in t['unknown_handles']}
            triggers = []
            if any(t['listing_adopted'] for t in new_rounds):
                triggers.append('C1_listing_adopt')
            if any(t['listing_refused'] for t in new_rounds) or any(t['listing_closed'] for t in new_rounds):
                triggers.append('C3_cap')
            if out['final_pick']:
                triggers.append('C2_final_pick')
            if any((t['round'], h) not in old_unknown_open for t in new_rounds for h in t['unknown_handles']
                   if h in (t['decision'].get('open') or []) or h in t['decision']['adopt']):
                triggers.append('C1_listing_drop_reused')
            if any(len(t['decision'].get('open') or []) > 4 for t in new_rounds):
                triggers.append('open_over_round_limit')
            old_cards = [(c['handle'], c['source_id'], c['via'], c['adopted'], c['dropped']) for c in rec['cards']]
            new_cards = [(c['handle'], c['source_id'], c['via'], c['adopted'], c['dropped']) for c in out['cards']]
            same = (old_cards == new_cards and rec['evidence_source_ids'] == out['evidence_source_ids']
                    and bool(rec['fallback']) == out['fallback'] and rec['rounds'] == out['rounds']
                    and (rec.get('deferrals') or 0) == out['deferrals'])
            rows[f'{cid}::{arm}'] = {
                'case_id': cid, 'arm': arm, 'same': same, 'triggers': triggers,
                'explained': same or bool(triggers),
                'old': {'cards': len(old_cards), 'evidence': [label(index, s) for s in rec['evidence_source_ids']],
                        'fallback': bool(rec['fallback']), 'rounds': rec['rounds']},
                'new': {'cards': len(new_cards), 'evidence': [label(index, s) for s in out['evidence_source_ids']],
                        'fallback': out['fallback'], 'rounds': out['rounds'], 'final_pick': out['final_pick'],
                        'listing_adopted': [c for t in new_rounds for c in t['listing_adopted']],
                        'listing_taken_total': out['listing_taken_total'], 'listing_closed': out['listing_closed']},
                'first_card_diff': next(({'old': o, 'new': n} for o, n in zip(old_cards, new_cards) if o != n), None)}
    changed = sorted(k for k, v in rows.items() if not v['same'])
    unexplained = sorted(k for k, v in rows.items() if not v['explained'])
    result = {'schema_version': 'adr0473-s0-trajectory-v1', 'candidate': cand, 'model_calls': 0,
              'config': 'rev-004 loop, C1~C3 on, C4 off; recorded ADR-0472 run-001 decisions replayed; final pick returns []',
              'passed': not unexplained, 'identical': sum(v['same'] for v in rows.values()), 'total': len(rows),
              'changed': changed, 'unexplained': unexplained, 'rows': rows}
    write(out_dir() / 's0-trajectory-replay.json', result)
    print(f"trajectory identical {result['identical']}/{result['total']}, changed {len(changed)}, unexplained {unexplained}")
    for k in changed:
        v = rows[k]
        print(' ', k, v['triggers'], 'old ev', v['old']['evidence'], '→ new ev', v['new']['evidence'])


# ── S0-c 위임 짝 감사·S1 표본 ─────────────────────────────────────────────
def audit() -> None:
    from legal_agent.delegation import pairs as delegation_pairs
    from legal_agent.search import Search
    cand = check_candidate()
    index, edges, reverse, origins, allowed, _ = shared(False)
    search = Search(GEN, allowed, index)
    visible = visible_in(index, allowed)
    frozen72 = read(ADR72 / 'frozen-inputs.json')
    loops72 = read(ADR72 / 'loop-results.json')['results']
    sample, counts, detail = {}, {}, {}
    for arm in SOURCE_ARMS:
        sample[arm], detail[arm] = {}, []
        for case in frozen72['cases']:
            cid = case['case_id']
            rec = loops72[f'{cid}::{arm}::run-001']
            if rec['fallback']:
                continue
            adopted = [c['source_id'] for c in rec['cards'] if c['adopted']]
            if adopted != rec['evidence_source_ids']:
                raise SystemExit(f'{cid} {arm}: adopted cards differ from recorded evidence')
            found = delegation_pairs(index, reverse, adopted, search.articles(case['question'], limit=40), visible)
            if not found:
                continue
            sample[arm][cid] = {'evidence': adopted, 'pairs': [p.__dict__ for p in found]}
            decisive = set(case['decisive_source_ids'])          # 정답은 선택이 끝난 뒤 채점용으로만 결합
            for p in found:
                detail[arm].append({'case_id': cid, 'parent': label(index, p.parent), 'child': label(index, p.child),
                                    'rank': p.rank, 'decisive': p.child in decisive})
        counts[arm] = {'pairs': len(detail[arm]), 'cases': len(sample[arm]),
                       'decisive': sum(1 for d in detail[arm] if d['decisive'])}
    result = {'schema_version': 'adr0473-s0-c4-audit-v1', 'candidate': cand, 'model_calls': 0,
              'expected': EXPECTED_C4, 'counts': counts, 'passed': counts == EXPECTED_C4,
              'gold_visible_to_product': False, 'detail': detail, 'sample': sample}
    write(out_dir() / 's0-c4-audit.json', result)
    print('c4 audit', json.dumps(counts, ensure_ascii=False), 'passed' if result['passed'] else 'MISMATCH')
    for arm in detail:
        print(' ', arm, [(d['case_id'], d['child'], d['rank']) for d in detail[arm] if d['decisive']])


# ── 입력 동결 ────────────────────────────────────────────────────────────
def freeze() -> None:
    cand = check_candidate()
    checks = {name: read(ART / f'{name}.json') for name in ('s0-selftest', 's0-trajectory-replay', 's0-c4-audit')}
    for name, value in checks.items():
        if not value.get('passed') or value.get('candidate') != cand:
            raise SystemExit(f'{name} must pass on the frozen revision before freeze')
    frozen72 = read(ADR72 / 'frozen-inputs.json')
    loops72 = read(ADR72 / 'loop-results.json')['results']
    loops69 = read(ADR69 / 'loop-results.json')['results']
    judge = read(ADR62 / 'frozen-inputs.json')
    cases = []
    for case in frozen72['cases']:
        cid = case['case_id']
        texts = {'ref-loop3-flash': loops72[f'{cid}::loop3-flash::run-001']['text'],
                 'ref-loop3-qwen': loops72[f'{cid}::loop3-qwen::run-001']['text'],
                 'ref-loop2c-qwen': loops69[f'{cid}::loop2c-qwen::run-001']['text']}
        if texts['ref-loop2c-qwen'] != case['reference_texts']['loop2c-qwen']:
            raise SystemExit(f'{cid}: ADR-0469 loop2c-qwen text differs from ADR-0472 frozen reference')
        cases.append({'case_id': cid, 'question': case['question'], 'reference_answer': case['reference_answer'],
                      'decisive_source_ids': case['decisive_source_ids'], 'reference_texts': texts})
    frozen = {'schema_version': 'adr0473-frozen-inputs-v1',
              'adr0472_frozen_sha256': sha(ADR72 / 'frozen-inputs.json'),
              'adr0472_loop_results_sha256': sha(ADR72 / 'loop-results.json'),
              'adr0469_loop_results_sha256': sha(ADR69 / 'loop-results.json'),
              'store_sha256': sha(GEN / 'store.sqlite'), 'navigation_sha256': sha(GEN / 'navigation/navigation.sqlite'),
              'fulltext_sha256': sha(GEN / 'fulltext/fulltext.sqlite'), 'projection_sha256': sha(PROJECTION),
              'candidate': cand, 'client_pin': check_client_pin(), 'locator_enabled': True,
              's0_sha256': {name: sha(ART / f'{name}.json') for name in checks},
              'judge_system': judge['judge_system'], 'judge_system_sha256': judge['judge_system_sha256'],
              'judge_schema': judge['judge_schema'], 'order_seed': ORDER_SEED,
              's1_sample': checks['s0-c4-audit']['sample'], 'targets': TARGETS,
              'reference_arms': {k: f'{v[0].parent.name} {v[1]} run-001' for k, v in REFERENCE.items()},
              'cases': cases}
    write(ART / 'frozen-inputs.json', frozen)
    print(f"frozen {len(cases)} cases, S1 sample flash {len(frozen['s1_sample']['loop3-flash'])} "
          f"qwen {len(frozen['s1_sample']['loop3-qwen'])}")


# ── S1 조립 재생 ─────────────────────────────────────────────────────────
def replay() -> None:
    from legal_agent.harness import PUBLIC_ORIGINS
    from legal_agent.index import LegalIndex
    from legal_agent.models import experiment_model
    from legal_agent.pipeline import answer_from_evidence
    from legal_agent.profiles import PROFILES
    from legal_agent.replay import origin_prefixes
    cand = check_candidate()
    check_client_pin()
    frozen = read(ART / 'frozen-inputs.json')
    if frozen['candidate'] != cand:
        raise SystemExit('frozen inputs were made with another candidate revision')
    cases = {c['case_id']: c for c in frozen['cases']}
    index = LegalIndex(GEN / 'store.sqlite')
    origins = origin_prefixes(PROJECTION)
    out_path = ART / 'replay-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0473-replay-v1', 'run': 'run-001', 'results': {}}
    for base, source_arm in S1_ARMS.items():
        profile = PROFILES[SOURCE_ARMS[source_arm]]
        items = frozen['s1_sample'][source_arm]
        for variant in ('control', 'pairs'):
            arm = f'{base}-{variant}'
            todo = [cid for cid in items if f'{cid}::{arm}::run-001' not in out['results']
                    or out['results'][f'{cid}::{arm}::run-001']['error']]
            buckets = [todo[i::WORKERS] for i in range(WORKERS)]

            def worker(no: int, cids: list[str], arm=arm, variant=variant, items=items, profile=profile) -> None:
                model = experiment_model(profile, ROOT, ART / 'calls' / 'run-001' / arm / f'worker-{no}',
                                         max_calls=2 * len(cids) + 2)
                for cid in cids:
                    item = items[cid]
                    sids = item['evidence'] if variant == 'control' else interleave(item['evidence'], item['pairs'])
                    units = units_for(index, origins, sids)
                    if any(u.origin not in PUBLIC_ORIGINS for u in units):
                        raise SystemExit(f'{cid}: non-public evidence in replay')
                    before = model.calls
                    try:
                        answer = answer_from_evidence(model, cases[cid]['question'], units, mode='plain',
                                                      phase=f'replay-{cid}-{variant}', rules=profile.composer_rules)
                        row = {'text': answer.text, 'answer': answer.to_json(), 'error': None}
                    except Exception as exc:
                        row = {'text': '(답변 생성 실패)', 'answer': None, 'error': f'{type(exc).__name__}: {exc}'[:500]}
                    row.update(arm=arm, run='run-001', case_id=cid, source_arm=source_arm, profile=profile.name,
                               composer_rules=profile.composer_rules, evidence_source_ids=sids,
                               paired=item['pairs'] if variant == 'pairs' else [],
                               calls=model.calls - before, usage=[u for u in model.usage if u['call'] > before])
                    with LOCK:
                        out['results'][f'{cid}::{arm}::run-001'] = row
                        write(out_path, out)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for future in [pool.submit(worker, i, b) for i, b in enumerate(buckets) if b]:
                    future.result()
            done = [v for k, v in out['results'].items() if k.split('::')[1] == arm]
            print(f"run-001 {arm}: {len(done)}/{len(items)}, errors {sum(1 for v in done if v['error'])}", flush=True)


# ── 채점 ─────────────────────────────────────────────────────────────────
def judge(stage: str) -> None:
    from lawrag.research.experiment_client import GeminiExperimentClient
    frozen = read(ART / 'frozen-inputs.json')
    cases = {c['case_id']: c for c in frozen['cases']}
    items = {}
    if stage == 's1':
        for key, row in read(ART / 'replay-results.json')['results'].items():
            items[key] = (cases[row['case_id']], row['arm'], row['run'], row['text'])
    elif stage == 's2':
        for key, row in read(ART / 'loop-results.json')['results'].items():
            items[key] = (cases[row['case_id']], row['arm'], row['run'], row['text'])
        for cid, case in cases.items():
            for ref in REFERENCE:
                items[f'{cid}::{ref}::run-002'] = (case, ref, 'run-002', case['reference_texts'][ref])
    else:
        raise SystemExit('judge stage must be s1 or s2')
    out_path = ART / 'judged-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0473-judged-v1', 'results': {}}
    order = sorted(items)
    random.Random(f'{ORDER_SEED}-{stage}').shuffle(order)
    todo = [k for k in order if k not in out['results'] or out['results'][k]['output'] is None]
    buckets = [todo[i::WORKERS] for i in range(WORKERS)]

    def worker(no: int, keys: list[str]) -> None:
        client = GeminiExperimentClient(ROOT, ART / 'judge-calls' / stage / f'worker-{no}', max_calls=2 * len(keys) + 2)
        for key in keys:
            case, arm, run_id, text = items[key]
            user = (f"[질문]\n{case['question']}\n\n[기준답변]\n{case['reference_answer']}\n\n[시스템 답변]\n{text}\n\n"
                    "reason은 3문장 이내, missing_points는 최대 5개의 짧은 항목으로 쓴다.")
            attempts, parsed = [], None
            for _ in range(2):
                try:
                    parsed = client.generate(frozen['judge_system'], user, frozen['judge_schema'],
                                             phase=f"judge-{case['case_id']}-{arm}-{run_id}")
                    attempts.append({'call': client.calls, 'error': None})
                    break
                except Exception as exc:
                    attempts.append({'call': client.calls, 'error': f'{type(exc).__name__}: {exc}'[:500]})
            row = {'key': key, 'stage': stage, 'arm': arm, 'run': run_id, 'case_id': case['case_id'],
                   'text_sha256': sha_text(text), 'user_sha256': sha_text(user), 'attempts': attempts, 'output': parsed,
                   'usage': [u for u in client.usage if u['call'] in {a['call'] for a in attempts}]}
            with LOCK:
                out['results'][key] = row
                write(out_path, out)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for future in [pool.submit(worker, i, b) for i, b in enumerate(buckets) if b]:
            future.result()
    mine = [r for k, r in out['results'].items() if k in items]
    print(f"judged {stage} {len(mine)}/{len(items)}, errors {sum(1 for r in mine if r['output'] is None)}")


# ── S1 관문 ──────────────────────────────────────────────────────────────
def gate() -> None:
    frozen = read(ART / 'frozen-inputs.json')
    replayed = read(ART / 'replay-results.json')['results']
    judged = read(ART / 'judged-results.json')['results']
    judged72 = read(ADR72 / 'judged-results.json')['results']
    loops72 = read(ADR72 / 'loop-results.json')['results']

    def verdict(cid, arm):
        row = judged.get(f'{cid}::{arm}::run-001')
        if row is None or row['output'] is None:
            raise SystemExit(f'missing S1 judgement: {cid} {arm}')
        return bool(row['output']['correct'])

    report = {}
    for base, source_arm in S1_ARMS.items():
        cids = sorted(frozen['s1_sample'][source_arm])
        control = {c: verdict(c, f'{base}-control') for c in cids}
        paired = {c: verdict(c, f'{base}-pairs') for c in cids}
        original = {c: bool((judged72[f'{c}::{source_arm}::run-001']['output'] or {}).get('correct')) for c in cids}
        report[base] = {
            'cases': len(cids), 'control_correct': sum(control.values()), 'pairs_correct': sum(paired.values()),
            'recovered': [c for c in cids if paired[c] and not control[c]],
            'regressed': [c for c in cids if control[c] and not paired[c]],
            'both_correct': [c for c in cids if control[c] and paired[c]],
            'both_wrong': [c for c in cids if not control[c] and not paired[c]],
            'control_vs_adr0472_verdict_flips': [c for c in cids if control[c] != original[c]],
            'control_text_identical_to_adr0472': sum(
                replayed[f'{c}::{base}-control::run-001']['text'] == loops72[f'{c}::{source_arm}::run-001']['text'] for c in cids),
            'errors': [k for k, v in replayed.items() if v['arm'].startswith(base) and v['error']]}
    flash = report['s1-flash']
    recovered_targets = [c for c in TARGETS if c in flash['recovered']]
    passed = len(recovered_targets) >= 2 and len(flash['regressed']) <= 1 and not flash['errors']
    result = {'schema_version': 'adr0473-s1-gate-v1', 'rule': 'S1-G: 목표 3문항 중 대조군 오답·짝 정답 ≥ 2이고 대상 전체 회귀 ≤ 1',
              'targets': TARGETS, 'recovered_targets': recovered_targets, 'passed': passed,
              'c4_on_for_loop4_flash': passed, 'run_loop4_flash_nopair': passed, 'report': report,
              'qwen_note': 'S1 Qwen 재생은 보고용이며 S2 loop4-qwen의 C4(끔)를 바꾸지 않는다',
              'judged_results_sha256': sha(ART / 'judged-results.json'),
              'replay_results_sha256': sha(ART / 'replay-results.json')}
    write(ART / 's1-gate.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'report'}, ensure_ascii=False))
    for base, value in report.items():
        print(base, json.dumps(value, ensure_ascii=False))


# ── S2 E2E ───────────────────────────────────────────────────────────────
def run() -> None:
    from dataclasses import asdict
    from legal_agent.loop import Loop
    from legal_agent.models import experiment_model
    from legal_agent.profiles import PROFILES, loop_config
    from legal_agent.search import Search
    cand = check_candidate()
    check_client_pin()
    frozen = read(ART / 'frozen-inputs.json')
    gate_result = read(ART / 's1-gate.json')
    if frozen['candidate'] != cand:
        raise SystemExit('frozen inputs were made with another candidate revision')
    arms = {'loop4-flash': ('flash-lite-exp', {'delegation_pairs': bool(gate_result['c4_on_for_loop4_flash'])})}
    if gate_result['run_loop4_flash_nopair']:
        arms['loop4-flash-nopair'] = ('flash-lite-exp', {'delegation_pairs': False})
    arms['loop4-qwen'] = ('genos-qwen-proxy', {})
    index, edges, reverse, origins, allowed, locator = shared(frozen['locator_enabled'])
    out_path = ART / 'loop-results.json'
    out = read(out_path) if out_path.exists() else {'schema_version': 'adr0473-loop-v1', 'results': {}, 'configs': {}}
    for arm, (profile_name, override) in arms.items():
        out['configs'][arm] = {'profile': profile_name, 'override': override,
                               'loop_config': asdict(loop_config(PROFILES[profile_name], **override))}
    for run_id in S2_RUNS:
        for arm, (profile_name, override) in arms.items():
            profile = PROFILES[profile_name]
            config = loop_config(profile, **override)
            # 기록이 없거나 제공자 오류(503 등)로 끝난 문항만 다시 돈다. 실패한 시도의 호출 원문은 calls/에 남는다.
            todo = [c for c in frozen['cases'] if f"{c['case_id']}::{arm}::{run_id}" not in out['results']
                    or out['results'][f"{c['case_id']}::{arm}::{run_id}"]['error']]
            buckets = [todo[i::WORKERS] for i in range(WORKERS)]

            def worker(no: int, cases: list[dict], arm=arm, run_id=run_id, profile=profile, config=config) -> None:
                search = Search(GEN, allowed, index)
                model = experiment_model(profile, ROOT, ART / 'calls' / run_id / arm / f'worker-{no}',
                                         max_calls=10 * len(cases) + 4)
                for case in cases:
                    before = model.calls
                    try:
                        result = Loop(index, search, edges, origins, allowed, model, config,
                                      reverse_edges=reverse, locator=locator).run(
                            case['question'], phase=f"loop-{case['case_id']}")
                        answer = result.pop('answer')
                        row = {'text': answer.text, 'answer': answer.to_json(), 'error': None, **result}
                    except Exception as exc:
                        row = {'text': '(답변 생성 실패)', 'answer': None, 'error': f'{type(exc).__name__}: {exc}'[:500],
                               'shown_source_ids': [], 'adopted_source_ids': [], 'evidence_source_ids': [],
                               'listing_source_ids': [], 'paired': [], 'paired_source_ids': []}
                    row.update(arm=arm, run=run_id, case_id=case['case_id'], calls=model.calls - before,
                               usage=[u for u in model.usage if u['call'] > before])
                    with LOCK:
                        out['results'][f"{case['case_id']}::{arm}::{run_id}"] = row
                        write(out_path, out)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for future in [pool.submit(worker, i, b) for i, b in enumerate(buckets) if b]:
                    future.result()
            done = [v for k, v in out['results'].items() if k.endswith(f'::{arm}::{run_id}')]
            print(f"{run_id} {arm}: {len(done)}/51, errors {sum(1 for v in done if v['error'])}", flush=True)


if __name__ == '__main__':
    command = sys.argv[1]
    if DEV and command not in ('selftest', 'trajectory', 'audit'):
        raise SystemExit('--dev is only for S0 commands')
    if command == 'judge':
        judge(sys.argv[2])
    else:
        {'selftest': selftest, 'trajectory': trajectory, 'audit': audit, 'freeze': freeze, 'replay': replay,
         'gate': gate, 'run': run}[command]()
