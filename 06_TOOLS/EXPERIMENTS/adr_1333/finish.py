"""Finalize this fixed actual-model probe, including failures and skipped turns."""
from common import *
import re, statistics

# A POSIX rename between two names for the same inode is a no-op. Repeated
# identical summaries can therefore leave common.put's temporary hardlink.
# This post-run wrapper removes only a verified duplicate of the current file;
# it does not change the frozen live writer or any observed result bytes.
_put = put
def put(p, value):
    p = Path(p)
    temporary = p.with_name('.' + p.name + '.pointer')
    if temporary.exists():
        assert p.exists() and os.path.samefile(p, temporary)
        temporary.unlink()
    _put(p, value)
    if temporary.exists():
        assert p.exists() and os.path.samefile(p, temporary)
        temporary.unlink()

OUT = ROOT / '09_ARTIFACTS/AUDITS/20261104-repeat-scope-live'
OUT.mkdir(exist_ok=True)
base = ART / 'public-live/repeat-integrated'
turns = read(base / 'result.json')['turns']
calls = read(base / 'calls.json')
audit = read(ART / 'source-wire-audit.json')
semantic = read(ART / 'semantic-review.json')
inspection = read(ART / 'inspection-summary.json')
candidate = read(DES / 'candidate-integrated.json')
assert all(sha(ROOT / n) == h for n, h in candidate['selected_files'].items())
assert all(sha(ROOT / candidate['code_root'] / n) == h for n, h in candidate['selected_files'].items())
assert read(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == read(DES / 'baseline.json')['pointer']
assert read(ART / 'runtime-archives.json')['all_restore_hashes_verified']
summary = {
    'selected_main': 140, 'selected_main_unchanged': True,
    'candidate_revision': candidate['pin'], 'candidate_parent': 'ADR-1332-experiment-v1/integrated',
    'same_parent_candidate_working_files': 528, 'new_product_changes': 0,
    'planned_turns': 4, 'executed_turns': len(turns), 'skipped_turns': 4 - len(turns),
    'turns': turns, 'semantic': semantic,
    'physical_calls': len(calls),
    'http200': sum(c.get('http_status') == 200 for c in calls),
    'http429': sum(c.get('http_status') == 429 for c in calls),
    'unknown': sum(c.get('status') == 'unknown' for c in calls),
    'reported_cost_usd': sum((c.get('usage') or {}).get('cost', 0) for c in calls),
    'reported_prompt_tokens': sum((c.get('usage') or {}).get('prompt_tokens', 0) for c in calls),
    'reported_completion_tokens': sum((c.get('usage') or {}).get('completion_tokens', 0) for c in calls),
    'request_seconds': sum(t['request_seconds'] for t in turns),
    'model_seconds': sum(c.get('seconds', 0) for c in calls),
    'source_checks': sum(a['source_checks'] for a in audit['cells']),
    'delivered_checks': sum(a['delivered_checks'] for a in audit['cells']),
    'source_mismatches': sum(len(a['source_mismatches']) for a in audit['cells']),
    'acl_violations': sum(len(a['acl_violations']) for a in audit['cells']),
    'wire_mismatches': sum(len(a['wire_mismatches']) for a in audit['cells']),
    'budget_matches': all(a['budget_matches'] for a in audit['cells']),
    'duplicate_extra_model_calls': sum(t.get('duplicate', {}).get('extra_model_calls', 0) for t in turns),
    'direct_assessment_generations': len(inspection['assessment_generations']),
    'wire_legacy_link_properties': sum(len(x['wire_link_properties']) for x in inspection['assessment_generations']),
    'full60_live_passed': False, 'field_execution': False, 'email_sent': False, 'quality_certified': False,
}
put(RUN / 'result.json', summary)
put(OUT / '검증요약.json', summary)

sys.path.insert(0, str(ROOT / '02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import (
    StageLedgerRecorder, identity_canonicalizer, grade_capture, build_run_artifact,
    build_experiment_artifact, deterministic_sha256,
)
m = read(ADR / '실험/manifest.json')
inventory = {(x[0], int(x[1])) for x in read(ART / 'source-inventory.json')['article_roots']}
captures = []
for arm in ('integrated',):
    rec = StageLedgerRecorder('repeat', arm, identity_canonicalizer)
    if arm == 'integrated':
        a = audit['cells'][0]
        acquired = {(x[0], int(x[1])) for x in a['acquired_articles']}
        presented = {(x[0], int(x[1])) for x in a['presented_articles']}
        assert presented <= acquired <= inventory
        rec.record_stage('source', 'source', sorted(inventory))
        rec.record_stage('acquired', 'retrieve', sorted(acquired), parent_stage_ids=('source',), discard_reasons={x: 'Not acquired before termination; no legal absence inference' for x in inventory - acquired})
        rec.record_stage('present', 'present', sorted(presented), parent_stage_ids=('acquired',), discard_reasons={x: 'Original not seen in outgoing input' for x in acquired - presented})
    else:
        for sid, kind, parents in [('source', 'source', ()), ('acquired', 'retrieve', ('source',)), ('present', 'present', ('acquired',))]:
            rec.record_stage(sid, kind, [], parent_stage_ids=parents, executed=False, skip_reason='Completed parent reference only; no baseline live run')
    captures.append(grade_capture(rec.capture(), []))
ledger = build_experiment_artifact('ADR-1333', m['experiment_id'], [build_run_artifact('run-001', captures, {'integrated': ['source', 'acquired', 'present']})])
ledger['audit'] = {'meaning': 'Actual conversation aggregated under repeat; no approved answer-key recall and no paired baseline live run.'}
ledger['artifact_sha256'] = deterministic_sha256({k: v for k, v in ledger.items() if k != 'artifact_sha256'})
lp = ART / 'retrieval-stage-ledger-corrected.json.gz'
put(ART / 'retrieval-stage-ledger-ref.json', write_raw_json(lp, ledger))
def per(v):
    return {'baseline': None, 'integrated': v}
m['retrieval_accounting'] = {
    'changed': False, 'corpus_total': len(inventory), 'before_filter': per(len(inventory)),
    'after_filter': per(len(acquired)), 'presented_total': per(len(presented)),
    'presented_mean': per(len(presented)), 'presented_p50': per(len(presented)), 'presented_p95': per(len(presented)),
    'golden_recall': per(None), 'selectivity': per(len(presented) / len(inventory)),
    'not_applicable_reason': 'Unchanged retrieval implementation. Measured session-wide article coordinates; no paired effect or approved-key recall claim.',
    'stage_ledger': {'mode': 'measured', 'schema_version': 'retrieval-stage-ledger-v1', 'accounting_unit': 'case_id + canonical article-root coordinate', 'summary_run_id': 'run-001', 'artifact_path': str(lp.relative_to(ROOT)), 'sha256': sha(lp), 'not_applicable_reason': None},
}
m['runs'][0].update(status='complete', sha256=sha(RUN / 'result.json'))
m['results'].update(
    status='complete', by_arm={'baseline': {'reference_only': True, 'physical_calls': 0}, 'integrated': summary},
    comparisons=[], judge_disagreements=0,
    usage={k: summary[k] for k in ('physical_calls', 'reported_cost_usd', 'reported_prompt_tokens', 'reported_completion_tokens', 'unknown')},
    latency={k: summary[k] for k in ('request_seconds', 'model_seconds')},
    error_taxonomy=semantic['error_taxonomy'],
)
put(ADR / '실험/manifest.json', m)

intro = semantic['conclusion_ko']
env = '완료1332와 정확히 동일한528파일을 격리했다. SQLite 원문·격리 기록, Qwen3.8-27b FP8/추론none, Parasail 우선 및 알려진429일 때만 NearAI 1회 전환 정책이다. 기존 검토표를 켠 기본 프로필·ontologyOFF·출력상한 없음. 이번 제품수정0, MAIN140/현장/내부모델/메일 변경0.'
cost = (f'물리{summary["physical_calls"]} / 정상HTTP200 {summary["http200"]} /429 {summary["http429"]} /UNKNOWN {summary["unknown"]}, 보고비용 ${summary["reported_cost_usd"]:.9f}. '
        f'요청 총{summary["request_seconds"]:.3f}초, 물리 모델관측{summary["model_seconds"]:.3f}초. 미보고 사용량 추정0. '
        f'원문{summary["source_checks"]}/전달{summary["delivered_checks"]}, 원문·ACL·wire 불일치 {summary["source_mismatches"]}/{summary["acl_violations"]}/{summary["wire_mismatches"]}, 예산일치{summary["budget_matches"]}, 동일요청 재조회 추가{summary["duplicate_extra_model_calls"]}회.')
limits = '동일 네 질문의 순차 단회 관측이다. 이전1319와 입력 이력·모델 출력이 같지 않으므로 속도 개선율·품질 향상의 인과 비교를 하지 않는다. R4 통테60개나 GENOS 내부모델 통과 인증이 아니다. 실패·미실행을 통과로 바꾸지 않았고, 관측 뒤 제품/질문/프롬프트를 수정하거나 UNKNOWN 요청을 재전송하지 않았다.'
answers = []
for item in semantic['turns']:
    num = item['number']
    result = next((t for t in turns if t['step']['number'] == num), None)
    answer = (base / f'turn-{num}/answer.txt').read_text() if result else '(앞선 중단에 따른 미실행)'
    answers.append(f'{num}. {item["question"]}\n판정: {item["verdict_ko"]}\n' + (f'시간 {result["request_seconds"]:.3f}초 / 모델{result["physical_calls"]}회 / API{result["http_status"]}\n' if result else '') + f'실제 표시 답변:\n{answer}')
archive_count = len(read(ART / 'runtime-archives.json')['rows'])
text = '\n\n'.join([intro, env, *answers, '원인과 수정 방향\n' + '\n'.join(semantic['findings_ko']), cost, limits, '원응답·원장·단계별 기록: ' + str(ADR.relative_to(ROOT)) + f'/artifacts. runtime{archive_count}개는 전파일 SHA 대조한 무손실 보관본과 복원 안내로 보존.']) + '\n'
(OUT / '실제질문_멀티턴_실험결과.txt').write_text(text)
heads = ['결정 요약', '문제와 변경 전 구조', '가설과 사전 판정 기준', '실험 설계', '데이터·모델·재현성', '결과', '사례별 오류 분석', '비용·지연·회수 규모', '해석', '한계와 일반화 가능 범위', '운영 결정·롤백 조건', '재현 명령']
values = [intro,
    '앞선1332는 정확한 반복 목표 유지·범위 주장 번호 연결 조립·실제 탐색 지침·불완전 보완 처리와 작업 병행 변경을 통합했다. 이 실험은 그 수정본 그대로의 실제 모델 관측이며 신규 후보가 아니다.',
    json.dumps(read(DES / 'criteria.json'), ensure_ascii=False),
    '새4턴: 정기총회 → 같은 질문 반복 → 임시총회 후속 → 의결권 주제 전환. 사전 동결 한 세션, 각1회. 동일 request 재조회는 새 모델 호출 금지. UNKNOWN/비200이면 후속 중단. 실행 전 무전송 준비·grant replay 확인.',
    env, '\n\n'.join(answers), '\n'.join(semantic['findings_ko']), cost + '\n단계 원장 artifacts/retrieval-stage-ledger-corrected.json.gz; 승인 정답지 없음으로 recall=null.',
    intro, limits,
    '이번 실제 관측만 기록. 선택 MAIN140와 작업528파일 SHA를 실행 전후 대조해 보존했다. 다음 제품 변경·재시험은 기존 원본을 유지한 새 ADR에서 한다. 실제모델 판단/기술 실패가 품질 승격 승인으로 바뀌지 않는다.',
    'setup → live_public.py repeat integrated --admission --grant-replay → live_public.py repeat integrated 1회 → audit.py → inspect_results.py → 실제 원문 수동 대조 → archive_runtime.py → finish.py → adr_structure hash/status/validate --final/graph. 실제 모델 명령을 자동 재실행하지 않는다. 보관 runtime은 각 receipt의 복원법을 따른다.',
]
front = (ADR / 'README.md').read_text().split('---', 2)[1]
front = re.sub(r'(?m)^status:.*$', 'status: ' + ('Proposed' if semantic['all_criteria_passed'] else 'Rejected'), front)
(ADR / 'README.md').write_text('---' + front + '---\n\n# 반복·근거 연결 수정본 실제 멀티턴 검증\n\n' + '\n\n'.join(f'## {n}. {h}\n\n{v}' for n, (h, v) in enumerate(zip(heads, values), 1)) + '\n')
qh = ['실행 메타', '사용자 질문 원문', '기준답변 — 채점 전용, 제품 입력 비공개', '제품 입력을 구성한 원값', '제품 모델 호출 — run·arm별 실제 원문', '중간 LLM 호출 — router/compiler/verifier/repair', '채점 호출과 반복 판정', '사례 최종 판정']
qv = ['run-001 / integrated / isolated rev001; baseline reference only, model0.', json.dumps(read(DES / 'live-cases.json'), ensure_ascii=False),
    '승인 정답지 없음. 저장 상법365/369 원문과 실제 전달된 주장·인용을 대조. 반복/후속/주제전환의 goal과 실제 내용을 별도 판정. 평가 결과는 제품 입력에 넣지 않음.',
    '### 회수·탈락 단계 원장 — run·arm별\n\nartifacts/retrieval-stage-ledger-corrected.json.gz 및 source-wire-audit.json. 전체 대화는 repeat 한 case, 사전 계획의 integrated arm만 집계. baseline은 실모델 run을 계획하지 않은 참조다. 세대·원문·ACL·wire SHA 대조 결과 보존.',
    '실제 system/user/schema/provider 원응답은 artifacts/public-live/repeat-integrated/raw/call-*/*.json.gz. canonical 입력/출력과 runtime 전파일 무손실 보관본을 함께 유지. 미도달 턴에는 원응답 없음.',
    '각 stage·순서·실패는 calls.json/generations.json 및 inspection-records.json.gz에 보존. 무전송 grant replay는 실제 모델 호출수에 합산하지 않음.',
    '채점 LLM0. artifacts/semantic-review.json의 저장 원문 수동 대조 및 source-wire-audit의 기계 대조. 동일 네 질문 한 번이므로 일반 정답률·전후효과로 확대하지 않음.',
    json.dumps(semantic, ensure_ascii=False),
]
(ADR / '실험' / m['questions'][0]['file']).write_text('# 공개4턴 실제 검증\n\n' + '\n\n'.join(f'## {n}. {h}\n\n{v}' for n, (h, v) in enumerate(zip(qh, qv), 1)) + '\n')
(ADR / '실험/README.md').write_text('# 실제4턴 세션\n\n- [질문과 결과](질문-001-repeat.md)\n')
paths = [p for p in ART.rglob('*') if p.is_file() and p != ART / 'manifest.json' and '.observer-versions' not in p.parts]
paths += list(Path(__file__).parent.glob('*.py')) + [p for p in OUT.glob('*') if p.is_file()]
put(ART / 'manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-1333', 'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'bytes': p.stat().st_size, 'description': 'Frozen inputs, complete raw actual-model outcomes, source/wire/memory audit and lossless closed runtime', 'contains_raw_prompts_and_outputs': 'raw' in p.parts or 'canonical' in p.parts or p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps({k: summary[k] for k in ('executed_turns', 'physical_calls', 'unknown', 'reported_cost_usd', 'source_checks', 'delivered_checks', 'budget_matches')}, ensure_ascii=False))
