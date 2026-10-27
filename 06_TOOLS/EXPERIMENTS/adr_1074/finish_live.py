"""Close only the frozen nine-cell live observation, preserving implementation history.

No model, corpus database, rerun, ADR status transition, or MAIN change is made.
The root operator performs final ADR validation and graph/status updates later.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import statistics

from common import ROOT, ADR, ART, read, save, sha
import report_results as report

BEGIN = '<!-- ADR1074_LIVE_RESULT_BEGIN -->'
END = '<!-- ADR1074_LIVE_RESULT_END -->'


def rel(path):
    return str(Path(path).relative_to(ROOT))


def json_receipt(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    return {'path': rel(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def verify_files(files):
    for name, expected in files.items():
        path = (ROOT / name).resolve()
        report.require(path.is_relative_to(ROOT.resolve()) and path.is_file(), 'missing/outside preserved file: ' + name)
        report.require(sha(path) == expected, 'preserved file changed: ' + name)


def implementation_files():
    names = ('RESULT.md', 'implementation-result.json', 'ACTION_CONTRACT_RESULT.md',
             'ACTION_CONTRACT_IMPLEMENTATION_PLAN.md', 'action-contract-result.json',
             'validation-binding.json')
    paths = {ART / name for name in names}
    for pattern in ('action-*', 'input-unlimited-*'):
        paths.update(p for p in ART.glob(pattern) if p.is_file())
    report.require(all(p.is_file() for p in paths), 'implementation evidence missing')
    return {rel(p): sha(p) for p in sorted(paths)}


def insert_live_section(original, section):
    """Keep front matter and every byte outside the explicitly owned live block."""
    if BEGIN in original or END in original:
        report.require(original.count(BEGIN) == original.count(END) == 1, 'ambiguous README live block')
        start, end = original.index(BEGIN), original.index(END) + len(END)
        report.require(start < end, 'reversed README live block')
        return original[:start] + section + original[end:]
    report.require(original.startswith('---\n'), 'README front matter missing')
    front = re.match(r'\A---\n.*?\n---\n', original, re.S)
    report.require(front is not None, 'README front matter incomplete')
    title = re.search(r'^# [^\n]*\n', original[front.end():], re.M)
    report.require(title is not None, 'README title missing')
    split = front.end() + title.end()
    return original[:split] + '\n' + section + '\n' + original[split:]


def live_readme(summary, validation):
    rows = '\n'.join(
        f"| {arm} | {summary['arms'][arm]['product_observations']['completed']} / 3 | "
        f"{summary['arms'][arm]['semantic']['pass']} | {summary['arms'][arm]['semantic']['unknown']} |"
        for arm in report.ARMS)
    completion = ('전체 9셀과 3개 평가 절차의 관찰을 기록했다. 관찰 완료와 제품 성공·법률 품질은 다르다.'
        if summary['complete_observations'] else
        '부분 중단 run은 failed로 남기고 원래 9셀·3개 질문을 유지한다. 미실행을 0점·0원이나 빈 원장으로 만들지 않는다.')
    return f'''{BEGIN}
## 1. 결정 요약

사용자 “실험해봐” 승인으로 기존 3문항 × A0/A1/A2의 **9셀만** 실행한 관찰이다. 상태 **{summary['status']}**, 제품 관찰 **{summary['completed_product_cells']}/9**, 평가 절차 **{summary['finished_evaluation_cases']}/3**, 운영 기준 통과 **{summary['operational_success']}**. MAIN104의 SQL 변경 확인 뒤 진행한 별도 온톨로지 후보이며, 이번 실험이 MAIN에 온톨로지 기능을 활성화하지 않는다. GENOS 현장·운영 골드는 미변경이다.

## 2. 문제와 변경 전 구조

완료 부모 ADR1072/B2의 SQL 수정과1067에서 검증한 재표시 동일성·요청 내 스키마 준비 최적화를 선택 합성했다. 기존 행동별 최소 계약과 입력 문자 차단 해제를 유지했다. 이전 실패 arm을 완료 부모나 새 관찰로 계산하지 않았다.

## 3. 가설과 사전 판정 기준

[라이브 사전 계획](artifacts/implementation-plan.json)과 [실행 동결](artifacts/design-freeze.json)을 따른다. 일차 지표는 원래 9셀 중 발행된 native 서비스 답변이며 원문 도달·전달, 행동 계약 실패와 의미 정확도를 따로 기록한다. 입력 문자 hard-stop 해제·출력 토큰 상한 없음, 총 40호출·1,024도구·1,800초와 자원 기준을 유지한다. 실제 모델 서버의 문맥 한도는 별도다.

## 4. 실험 설계

알려진 FSC005·CM023·FSC008만 사용한다. A0은 온톨로지 없음, A1/A2는 같은 승인 원문·메타데이터의 표시 구조 차이다. 동일 조건의 동시 대조는 이 9셀의 arm 사이이며, 과거1065는 설명용 이력이다. 추가 102셀·10번째 셀·반복·재채점은 이번 범위에 없다.

## 5. 데이터·모델·재현성

동일하게 검사한 749파일을 arm별 후보에 결속했다. 라이브 전 합성 계약/API **{validation['passed']}개** 통과는 실제 생성·품질 인증과 구분한다. [검사](artifacts/validation-binding.json), [코드 결속](artifacts/candidate-bindings.json), [보존 기록](artifacts/implementation-plan.json), 실행 동결의 코드·데이터·모델·제공자·권한 해시를 따른다. 기준답변과 필수근거 좌표는 평가 전용이다.

## 6. 결과

[라이브 전체 결과](artifacts/LIVE_RESULT.md) · [기계 집계](artifacts/matrix-summary.json) · [9셀 운영 기준](artifacts/gate.json) · [원문 원장](artifacts/retrieval-ledger.json).

| arm | 완료 관찰 | 의미 pass | 의미 unknown |
|---|---:|---:|---:|
{rows}

{completion} ADR 최종 검증·graph·예약 종료는 root의 별도 단계이며 이 도구가 통과나 완료를 주장하지 않는다.

## 7. 사례별 오류 분석

[질문별 기록](실험/README.md)과 원시 요청·응답·저널에서 전송, 행동 형식, 판단 보완, 도구, 원문/권한/상태, 발행 실패를 구분한다. 최초 원인과 후속 보완 실패를 하나로 합치지 않는다. 미확보를 원문 부재나 사용자 사실 부족으로 단정하지 않는다.

## 8. 비용·지연·회수 규모

제품과 평가의 호출·usage·p50/p95·원문 확보/전달/인용은 기계 집계에 연결한다. 누락된 사용량·미실행 셀을 0으로 채우지 않는다. 이전 구현 검사 80개와 이번 실모델 호출 수를 합산하지 않는다.

## 9. 해석

HTTP200, 정상 출력 수신, canonical 검증, 실제 도구 실행, 원문 전달, 온톨로지 사용, 최종 발행과 의미 정확도는 각각 다른 관측이다. A1/A2의 효과는 실제 승인 묶음 도달·확보·전달이 관측된 범위에서만 해석한다. 기록으로 확인하지 못한 값은 미확인이다.

## 10. 한계와 일반화 가능 범위

알려진 3문항의 in-sample 결합 수정 probe이며 decision_eligible=false다. 모든 원문·연결 유형이나 미사용 질문, GENOS 내부 모델 성능을 인증하지 않는다. 관찰 분모와 미완료·미확인을 공개하며, 단계별 변경의 독립적인 인과 효과라고 설명하지 않는다.

## 11. 운영 결정·롤백 조건

Proposed, quality_certified=false, MAIN103 유지다. 구현 원본 RESULT.md·ACTION_CONTRACT_RESULT.md와 rev-001/12검사·rev-002/80검사 기록은 보존한다. 결과 후 코드 변경·재실행은 별도 ADR로 남긴다.

## 12. 재현 명령

`.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1074/run_matrix.py --inspect-only`로 동결 입력을 확인한다. 이미 예약·종료한 셀은 재실행하지 않는다. 원시 기록의 종료 보고에는 `.venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_1074/finish_live.py`를 사용하며, 이는 모델 호출·상태 전환·MAIN 승격을 수행하지 않는다.

아래 본문은 라이브 실행 전 작성한 구현 이력이다. 당시의 “외부 모델0회·실험 미동결” 표기는 그 시점의 기록이다.
{END}'''


def main():
    freeze = read(ART / 'design-freeze.json')
    records=read(ART/'validation-binding.json')['records']
    validation=read(ROOT/records[0]['path'])
    preserved=read(ART/'implementation-plan.json')['preservation']
    verify_files(preserved)
    report.require(validation['status']==0 and validation['failed']==0 and validation['passed']>0
        and not validation['import_leaks'] and not validation['candidate_changed'], 'current frozen validation failed')
    report.require(freeze['files']==validation['files'], 'selected code does not match tested map')
    code=ROOT/freeze['code_root']
    verify_files({rel(code/name):value for name,value in freeze['files'].items()})
    verify_files(freeze['runner_hashes'])
    loaded, cases, cells, judges, summary, ledger = report.load_inputs()
    report.require(loaded == freeze, 'freeze changed while reporting')
    report.require(summary['complete_observations'] or bool(summary['stop']),
        'close only all observations or an explicitly recorded stopped matrix')
    report.require(len(cases) == 3 and len(cells) == 9 and len(freeze['execution_order']) == 9, 'live scope changed')
    summary['retrieval_ledger'] = json_receipt(ART / 'retrieval-ledger.json', ledger)
    summary['implementation_validation'] = report.receipt(ART / 'validation-binding.json')
    documents = []
    manifest = read(ADR / '실험/manifest.json')
    implementation = {k: deepcopy(manifest[k]) for k in ('implementation_result', 'implementation_extension') if k in manifest}
    manifest['questions'] = []
    for number, case in enumerate(cases, 1):
        path = ADR / '실험' / f"질문-{number:03d}-{case['case_id']}.md"
        body = report.question_markdown(number, case, freeze, cells, judges, summary)
        documents.append((path, body))
        manifest['questions'].append({'number': number, 'case_id': case['case_id'], 'file': path.name,
            'sha256': hashlib.sha256(body.encode('utf-8')).hexdigest()})
    corpus_total = freeze.get('corpus_total_article_roots')
    report.require(all(c['metrics']['corpus_total_article_roots'] == corpus_total
        for c in cells.values() if c.get('metrics')), 'cell corpus total differs from freeze')
    arm_metrics = {}
    for arm in report.ARMS:
        rows = [c['ledger'] for c in cells.values() if c['cell']['arm'] == arm and c.get('ledger')]
        counts = [r['stages'][-1]['after_count'] for r in rows]
        total = sum(r['gold_total'] for r in rows)
        gold = sum(r['stages'][-1]['gold_after'] for r in rows)
        arm_metrics[arm] = {'presented_total': sum(counts) if counts else None,
            'presented_mean': statistics.mean(counts) if counts else None,
            'presented_p50': statistics.median(counts) if counts else None,
            'presented_p95': sorted(counts)[round((len(counts) - 1) * .95)] if counts else None,
            'golden_recall': gold / total if total else None,
            'selectivity': statistics.mean(counts) / corpus_total if counts and corpus_total else None}
    manifest['retrieval_accounting'].update(corpus_total=corpus_total,
        before_filter={'status': 'unavailable', 'reason': 'No full pre-filter snapshot; not inferred from candidate pages'},
        after_filter={'status': 'unavailable', 'reason': 'Exact acquisition/delivery/citation coordinates retained'},
        **{key: {a: arm_metrics[a][key] for a in report.ARMS} for key in
           ('presented_total', 'presented_mean', 'presented_p50', 'presented_p95', 'golden_recall', 'selectivity')})
    manifest['retrieval_accounting']['stage_ledger'].update(artifact_path=rel(ART / 'retrieval-ledger.json'),
        sha256=summary['retrieval_ledger']['sha256'])
    status = 'complete' if summary['complete_observations'] else 'failed'
    runs = [r for r in manifest['runs'] if r['id'] == 'run-001']
    report.require(len(runs) == 1, 'expected one live run-001')
    runs[0].update(status=status, artifact_path=rel(ART / 'matrix-summary.json'),
        sha256=json_receipt(ART / 'matrix-summary.json', summary)['sha256'], terminal_execution_status=summary['status'],
        observed_cells=summary['completed_product_cells'], planned_cells=9,
        note='Fixed nine-cell observation. Complete means all observations, not product/quality success. Partial stops remain failed; no sample reduction or invented empty records.')
    manifest['results'] = {'status': status,
        'by_arm': {a: {'status': status, 'total': summary['arms'][a]['product_observations']['completed'],
            'planned_total': 3, 'correct': summary['arms'][a]['semantic']['pass'],
            'accuracy': summary['arms'][a]['semantic']['determinate_accuracy'],
            'unknown': summary['arms'][a]['semantic']['unknown']} for a in report.ARMS},
        'comparisons': [], 'judge_disagreements': None,
        'usage': {a: summary['arms'][a]['usage'] for a in report.ARMS},
        'latency': {a: summary['arms'][a]['latency_seconds'] for a in report.ARMS},
        **{k: deepcopy(summary[k]) for k in ('terminal_execution_status', 'secondary_required_body_reach',
            'primary_native_service_completion', 'primary_service_completion', 'first_nine_gate',
            'final_validation_constraint', 'final_validation_note') if k in summary},
        'terminal_execution_status': summary['status'], 'quality_certified': False,
        'operational_success': summary['operational_success'], 'adr_final_validation_completed': False,
        'adr_completion_claimed': False}
    report.require(all(manifest[k] == v for k, v in implementation.items()), 'implementation metadata changed')
    readme = ADR / 'README.md'
    original_readme = readme.read_text(encoding='utf-8')
    documents.extend([(ART / 'LIVE_RESULT.md', report.report_markdown(summary)),
        (readme, insert_live_section(original_readme, live_readme(summary, validation))),
        (ADR / '실험/README.md', '# ADR1074 질문별 라이브 관찰\n\n[동결](../artifacts/design-freeze.json) · '
         '[라이브 결과](../artifacts/LIVE_RESULT.md) · [구현 이력](../artifacts/candidate-bindings.json)\n\n' +
         '\n'.join(f"- [{q['case_id']}]({q['file']})" for q in manifest['questions']) + '\n')])
    for artifact in summary.get('input_artifacts', []):
        report.verify_ref(artifact)
    verify_files(preserved)
    save(ART / 'retrieval-ledger.json', ledger)
    save(ART / 'matrix-summary.json', summary)
    for path, body in documents:
        path.write_text(body, encoding='utf-8')
    save(ADR / '실험/manifest.json', manifest)
    verify_files(preserved)
    save(ART / 'manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-1074',
        'created_at': manifest['reservation']['created_at'], 'files': [
            {'path': rel(p), 'sha256': sha(p), 'bytes': p.stat().st_size,
             'description': 'Preserved implementation history and frozen nine-cell live observation',
             'contains_raw_prompts_and_outputs': 'model' in p.parts or p.name == 'journal.sqlite'}
            for p in sorted(ART.rglob('*')) if p.is_file() and p != ART / 'manifest.json' and p.suffix != '.lock']})
    print(summary['status'], summary['completed_product_cells'], summary['finished_evaluation_cases'])


if __name__ == '__main__':
    main()
