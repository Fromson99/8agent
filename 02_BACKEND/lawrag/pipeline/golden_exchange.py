"""File-only authoring and answer review. No network, model calls or activation."""
from __future__ import annotations

import html
import json
from pathlib import Path
import shlex

from semantic_runtime.contracts import digest, sha, write
from . import golden as g


def checked_files(folder, required):
    folder = Path(folder).resolve()
    receipt = g.verify(g.read(folder / 'receipt.json'))
    files = receipt['files']
    if not set(required).issubset(files):
        raise ValueError('receipt does not cover required artifacts')
    for relative, expected in files.items():
        path = (folder / relative).resolve()
        path.relative_to(folder)
        if sha(path) != expected:
            raise ValueError('run artifact changed')
    return receipt


def checked_run(folder):
    folder = Path(folder).resolve()
    receipt = checked_files(folder, ['suite.json', 'rows.json'])
    suite = g.verify(g.read(folder / 'suite.json'))
    rows = g.read(folder / 'rows.json')
    expected = [c['id'] for c in suite['cases']]
    if len(rows) != len(expected) or len({r['case_id'] for r in rows}) != len(rows) or set(expected) != {r['case_id'] for r in rows}:
        raise ValueError('run must contain every case exactly once')
    responses = {}
    for row in rows:
        if 'answer_sha256' not in row:
            continue
        relative = str(Path(row['artifact_directory']) / 'response.json')
        if relative not in receipt['files']:
            raise ValueError('receipt does not cover answer response')
        response = g.read(folder / relative)
        if digest(response['answer']) != row['answer_sha256'] or response['answer'] != row.get('answer'):
            raise ValueError('answer hash mismatch')
        responses[row['case_id']] = response
    return suite, rows, responses


def _issue(case_id, code, message):
    return {'case_id': case_id, 'code': code, 'message': message}


def validate_review(bundle, reviewed, cat):
    original = bundle['draft']
    issues = []
    for key in ('schema_version', 'suite_id', 'version', 'mapping_binding', 'import_provenance'):
        if reviewed.get(key) != original.get(key):
            issues.append(_issue(None, 'PACKAGE_MISMATCH', f'{key}: 다른 작성 묶음의 검토본입니다.'))
    binding = {k: v for k, v in cat.items() if k != 'sources'}
    if binding != original.get('mapping_binding'):
        issues.append(_issue(None, 'GENERATION_CHANGED', '원문 세대가 변경됐습니다. 새 세대로 후보를 생성하고 다시 검토하세요.'))
    cases = reviewed.get('cases')
    if not isinstance(cases, list) or any(not isinstance(c, dict) for c in cases):
        return issues + [_issue(None, 'INVALID_FILE', 'cases는 문항 목록이어야 합니다.')]
    ids = [c.get('id') for c in cases]
    expected = [c['id'] for c in original['cases']]
    if any(not isinstance(cid, str) for cid in ids) or len(set(ids)) != len(ids) or set(ids) != set(expected):
        return issues + [_issue(None, 'CASE_SET_CHANGED', '문항이 누락·추가·중복됐습니다. 원래 검토 화면에서 전체 문항을 내려받으세요.')]
    originals = {c['id']: c for c in original['cases']}
    for case in cases:
        cid = case['id']
        base = originals[cid]
        try:
            if case['document_ids'] != base['document_ids'] or case['expected_behavior'] != base['expected_behavior']:
                issues.append(_issue(cid, 'SCOPE_CHANGED', '검색 범위 또는 기대 동작이 변경됐습니다. 원래 입력부터 다시 생성하세요.'))
            groups = case['evidence_groups']
            group_roles = {x['id']: x['role'] for x in groups}
            if len(group_roles) != len(groups) or group_roles != {x['id']: x['role'] for x in base['evidence_groups']}:
                issues.append(_issue(cid, 'GROUPS_CHANGED', '필수/참고 근거 그룹이 누락되거나 변경됐습니다.'))
            for group in groups:
                targets = [m for m in bundle['mappings'] if m['case_id'] == cid and m['group_id'] == group['id']]
                candidates = {sid for m in targets for sid in m['candidate_ids']}
                if any(ref['source_id'] not in candidates for ref in group['any_of']):
                    issues.append(_issue(cid, 'CANDIDATE_CHANGED', '검토 화면에 없던 원문입니다. 입력 수정 후 후보를 다시 생성하세요.'))
            g._freeze_with_catalog({**reviewed, 'cases': [case]}, cat)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            message = str(exc)
            translations = {
                'human approval required before freeze': '미승인 문항입니다. 검토자 입력 후 문항을 승인하세요.',
                'gold quote must match the exact source block': '근거 구절이 선택한 원문 블록과 일치하지 않습니다.',
                'invalid evidence group': '연결되지 않았거나 잘못된 근거 그룹이 있습니다.',
                'required answer/refrain criteria missing': '필수 답변 내용을 입력하세요.',
                'unresolved source/version mapping': '정답 근거의 문서·버전·해시가 원문과 다릅니다.',
            }
            issues.append(_issue(cid, 'CASE_INVALID', translations.get(message, '문항 필드·기준일·승인 시각 또는 근거를 확인하세요.')))
    return issues


def receive(authoring, reviewed_path, generation, output):
    """Keep the upload and all diagnostics; create a suite only when all cases pass."""
    checked_files(authoring, ['mapping.json', 'draft.json'])
    bundle = g.verify(g.read(Path(authoring) / 'mapping.json'))
    if bundle['draft'] != g.read(Path(authoring) / 'draft.json'):
        raise ValueError('authoring draft mismatch')
    raw = Path(reviewed_path).read_bytes()
    try:
        reviewed = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(reviewed, dict):
            raise ValueError('object required')
    except (ValueError, UnicodeError):
        reviewed = None
    cat = g.catalog(generation)
    issues = (validate_review(bundle, reviewed, cat) if reviewed is not None else
              [_issue(None, 'INVALID_JSON', '검토본 JSON이 아닙니다. 화면의 검토본 내려받기로 저장하세요.')])
    suite = g._freeze_with_catalog(reviewed, cat) if not issues else None
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'uploaded.json').write_bytes(raw)
    status = {'schema_version': 'golden-upload-check-v1', 'ok': not issues,
              'case_count': len(bundle['draft']['cases']), 'issues': issues,
              'authoring_sha256': bundle['content_sha256'], 'uploaded_sha256': sha(output / 'uploaded.json')}
    write(output / 'validation.json', g.seal(status))
    title = '검증 통과 · 평가용 골든 생성' if not issues else '수정 후 다시 업로드하세요'
    body = '<!doctype html><html lang="ko"><meta charset="utf-8"><title>골든 업로드 확인</title><h1>' + title + '</h1>'
    body += '<p>총 ' + str(status['case_count']) + '문항. 이 검사는 원문 연결 검사이며 성능 평가가 아닙니다.</p><ul>'
    for item in issues:
        body += '<li>' + html.escape(f"{item['case_id'] or '전체'}: {item['message']}") + '</li>'
    (output / 'validation.html').write_text(body + '</ul></html>', encoding='utf-8')
    if suite:
        write(output / 'suite.json', suite)
    steps = ('검증 통과: suite.json을 기존 golden plan의 --suite에 지정하세요.\n'
             '평가 조건·ADR·내부 모델을 먼저 고정한 뒤 golden run --plan 계획파일 --output 새실행폴더로 실행합니다.\n'
             if suite else 'validation.html에서 수정할 문항을 확인하세요. 원래 review.html에 작업 파일을 불러와 수정·재승인하세요.\n'
             '다시 검토본을 내려받고 receive의 --output을 새 폴더로 지정하세요. 실패 문항을 삭제하지 않습니다.\n')
    (output / 'NEXT_STEPS.txt').write_text(steps, encoding='utf-8')
    write(output / 'receipt.json', g.seal({'files': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
                                         'authoring_sha256': bundle['content_sha256'], 'ok': not issues}))
    return {**status, 'output': str(output)}


def answer_bundle(suite, rows, responses):
    """Bundle actual retrieved/context sources alongside gold so support can be judged."""
    cases = []
    byid = {c['id']: c for c in suite['cases']}
    for row in rows:
        response = responses.get(row['case_id'], {})
        sources = {}
        for source in [*response.get('retrieval', {}).get('candidates', []), *response.get('assembly', {}).get('context', [])]:
            sources[source['id']] = source
        cases.append({'gold': byid[row['case_id']], 'result': row, 'sources': list(sources.values())})
    return {'schema_version': 'golden-answer-ui-v1', 'suite_id': suite['suite_id'],
            'review': g.review_template(suite, rows), 'cases': cases}


def render_answers(suite, rows, responses, path):
    payload = json.dumps(answer_bundle(suite, rows, responses), ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = Path(__file__).with_name('golden_answers.html').read_text(encoding='utf-8')
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(template.replace('__ANSWER_DATA__', payload))


def review_answers(run, output):
    suite, rows, responses = checked_run(run)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    render_answers(suite, rows, responses, output / 'answer-review.html')
    command = ('python 06_TOOLS/pipeline.py golden report --run ' + shlex.quote(str(Path(run).resolve())) +
               ' --reviews /업로드경로/answers-reviewed.json --output /새보고서폴더')
    (output / 'NEXT_STEPS.txt').write_text('answer-review.html을 허용된 내부 PC에서 열어 답변을 채점합니다.\n'
        '작업 저장 파일로 중단·재개할 수 있습니다. 채점본 JSON을 GENOS에 업로드하고 아래 경로를 바꿔 실행하세요.\n' + command + '\n', encoding='utf-8')
    write(output / 'receipt.json', g.seal({'run_receipt_sha256': sha(Path(run) / 'receipt.json'),
        'files': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}}))
