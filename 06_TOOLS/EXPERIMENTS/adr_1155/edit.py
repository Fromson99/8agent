from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_1155/focused-r1/snapshot';B=S/'02_BACKEND/semantic_runtime/legal_agent'
def replace(name,a,b):
 p=B/name;s=p.read_text();assert a in s,(name,a);p.write_text(s.replace(a,b,1))
(B/'investigation_focus.py').write_text('''"""Request-bound search continuity. No semantic selection or new model call."""
from copy import deepcopy
from ..contracts import digest


def retain_search_candidates(inv, data, actions, offer, search_window):
    binding = digest([inv.p['binding'], data['query_fingerprint'],
                      data.get('direct_search_scope'), sorted(inv.s.scope)])
    saved = inv.p.get('search_candidate_memory')
    if not saved or saved['binding'] != binding:
        saved = {'binding': binding, 'candidates': {}}
        inv.p['search_candidate_memory'] = saved
    if search_window:
        for law in data['laws']:
            for row in law.get('article_matches', []):
                action = actions.get(row.get('read_action'))
                if action:
                    key = digest(action['identity'])
                    saved['candidates'][key] = {'law': {k: law[k] for k in ('id', 'document_id', 'name')},
                        'row': deepcopy(row), 'action': deepcopy(action)}
        return
    selected = {r['source_id'] for r in inv.p.get('selected', {}).values()}
    laws = {law['document_id']: law for law in data['laws']}
    for item in saved['candidates'].values():
        identity = item['action']['identity']; did = identity['document_id']
        if did not in inv.s.scope or identity['source_id'] in selected:
            continue
        # Re-offer through the current scope and availability owner; never reuse
        # a historical executable handle or broaden a current document filter.
        target = offer('READ_ARTICLES', deepcopy(identity), item['action']['label'])
        if not target:
            continue
        if did not in laws:
            laws[did] = deepcopy(item['law']); data['laws'].append(laws[did])
        rows = laws[did].setdefault('article_matches', [])
        if any(r.get('read_action') == target for r in rows):
            continue
        row = deepcopy(item['row']); row.update(read_action=target, origin='PREVIOUS_SEARCH_UNREAD')
        rows.append(row)


def matched_excerpts(hits, terms, limit=3, width=160):
    """Exact substrings, with offsets, from all bounded search hits."""
    out = []
    for hit in hits[:limit]:
        text = hit.get('text', '')
        if not text:
            continue
        positions = [text.casefold().find(str(t).casefold()) for t in terms if str(t)]
        positions = [p for p in positions if p >= 0]
        start = max(0, (min(positions) if positions else 0) - width // 4)
        end = min(len(text), start + width)
        out.append({'unit_id': hit.get('unit_id'), 'start_cp': start, 'end_cp': end,
                    'text': text[start:end], 'full_unit_shown': start == 0 and end == len(text)})
    return out
''')
replace('law_navigation.py',"        data['presentation_id'] = lc.token(self.s, 'P', digest(data))\n        return data, actions", "        if self.policy.get('minimal_input'):\n            from .investigation_focus import retain_search_candidates\n            retain_search_candidates(self, data, actions, offer, search_window)\n            data['actions'] = [{k: a[k] for k in ('id', 'action', 'label')} for a in actions.values()]\n        data['presentation_id'] = lc.token(self.s, 'P', digest(data))\n        return data, actions")
replace('law_navigation.py',"key=digest([self.p['binding'],descriptor,query])", "key=digest([self.p['binding'],descriptor,query,'matching-excerpts-v1'])")
replace('law_navigation.py',"                    body=next((h for h in hits if str(h['unit_id'])!=str(h['article_unit_id'])),hits[0] if hits else None)\n                    self.s.store.check_unchanged(); self.idx.check_unchanged()\n                    cache[key]=body['text'][:240] if body else ''", "                    from .investigation_focus import matched_excerpts\n                    self.s.store.check_unchanged(); self.idx.check_unchanged()\n                    cache[key]=matched_excerpts(hits,query['terms'])")
replace('law_navigation.py',"                row['preview']=cache[key]\n", "                row['matching_excerpts']=deepcopy(cache[key])\n                row['preview']='\\n'.join(x['text'] for x in cache[key])\n                row['preview_scope']='검색 적중 일부; 조 전체나 질문 해결 여부를 뜻하지 않음'\n")
replace('decision_projection.py',"hint_fields = ('article', 'heading', 'preview', 'coordinate', 'title', 'surface', 'path')", "hint_fields = ('article', 'heading', 'preview', 'coordinate', 'title', 'surface', 'path', 'matching_excerpts', 'preview_scope', 'origin')")
# Existing semantic review machinery; observe without forced correction/handoff.
replace('answer_progress.py',"return bool(getattr(inv, 'policy', {}).get('answer_progress_control', False))", "return bool(getattr(inv, 'policy', {}).get('answer_progress_control', False) or\n                getattr(inv, 'policy', {}).get('answer_progress_observe', False))")
replace('answer_progress.py',"            'handoff_after_unchanged_steps': NO_CHANGE_LIMIT}", "            'handoff_after_unchanged_steps': (None if inv.policy.get('answer_progress_observe') else NO_CHANGE_LIMIT),\n            'mode': 'OBSERVE' if inv.policy.get('answer_progress_observe') else 'CONTROL',\n            'original_acquisition_is_answer_progress': False}")
replace('answer_progress.py',"        target['properties'].pop('missing_need', None)\n        target['required'] = [k for k in target['required'] if k != 'missing_need']", "        if not inv.policy.get('answer_progress_observe'):\n            target['properties'].pop('missing_need', None)\n            target['required'] = [k for k in target['required'] if k != 'missing_need']")
replace('answer_progress.py',"    if not check_action:\n        return", "    if not check_action or (inv is not None and inv.policy.get('answer_progress_observe')\n                            and value['choice'] not in ('FINISH', 'PENDING')):\n        return")
replace('answer_progress.py',"    current = {s['id']: s for s in data.get('sources', []) if s.get('text')}\n    validate_review", "    if inv.policy.get('answer_progress_observe'):\n        return value, None\n    current = {s['id']: s for s in data.get('sources', []) if s.get('text')}\n    validate_review")
replace('answer_progress.py',"    value = deepcopy(value)\n    goals =", "    value = deepcopy(value)\n    if inv is not None and inv.policy.get('answer_progress_observe'):\n        return value\n    goals =")
replace('answer_progress.py',"    handoff = bool(originals and selected and all(counts[r['issue_id']] >= NO_CHANGE_LIMIT for r in selected))", "    handoff = bool(not inv.policy.get('answer_progress_observe') and originals and selected\n                   and all(counts[r['issue_id']] >= NO_CHANGE_LIMIT for r in selected))")
p=S/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=json.loads(p.read_text());v['candidate_navigation']['answer_progress_observe']=True;p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
replace('compact_model_input.py',"필요한 읽기 후보가 있으면 먼저 읽는다.", "origin=PREVIOUS_SEARCH_UNREAD는 앞선 검색에서 아직 읽지 않은 후보이며 현재 연결과 별개로 선택할 수 있다. matching_excerpts는 검색 적중 일부이지 전체 조항 내용이 아니다.\n필요한 읽기 후보가 있으면 먼저 읽는다.")
replace('compact_model_input.py',"실제 실행 결과와 남은 확인 사항을 보고 같은 실패·원문 조회를 반복하지 않는다.", "실제 실행 결과와 남은 확인 사항을 보고 같은 실패·원문 조회를 반복하지 않는다. answer_progress의 answer_so_far·material_need·previous_effect를 새 원문과 대조해 갱신한다. 이미 확보한 항을 다시 확보한다고 쓰지 말고 범위를 넓혀 새로 확인할 조건을 특정한다. NO_CHANGE가 이어지면 이전 검색 후보·다른 검색어·구조조회·확인 범위 종료 중 방향을 다시 판단한다. 새 원문 수와 도구 성공만으로 답변이 진전됐다고 하지 않는다.")
print('Edited isolated candidate')
