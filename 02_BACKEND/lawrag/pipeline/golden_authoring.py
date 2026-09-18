"""Human-friendly golden import and portable, network-free source review sheet."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import unicodedata

from semantic_runtime.contracts import sha, write
from .golden import VERSION, catalog, read, seal

FIELDS = ['문항ID', '질문', '기준답변', '기준일', '문서명', '조문', '구분', '근거그룹', '역할', '근거구절']
LIFTED = ('collection', 'tags')


def csv_template(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(FIELDS)
        writer.writerow(['case-001', '질문을 입력하세요', '기준답변을 입력하세요', '2026-09-16',
                         '문서의 정식 이름', '제1조', 'body', 'basis-1', 'required', ''])


def normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', str(value)))


def article_of(source):
    match = re.match(r'제\d+(?:-\d+)?조(?:의\d+)?', normalized(source['heading']))
    return match.group() if match else None


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if set(FIELDS) - set(reader.fieldnames or []): raise ValueError('CSV columns must match csv-template')
        return list(reader)


def csv_target(row, n):
    """One evidence row of the authoring sheet; n numbers groups left blank by the author."""
    role = {'필수': 'required', '참고': 'reference'}.get(row['역할'], row['역할']) or 'required'
    if role not in ('required', 'reference'): raise ValueError('role must be required or reference')
    scope = {'본칙': 'body', '부칙': 'addendum'}.get(row['구분'], row['구분']) or 'body'
    locator = normalized(row['조문'])
    if locator.startswith('부칙'): scope = 'addendum'; locator = locator.removeprefix('부칙')
    match = re.fullmatch(r'(제\d+(?:-\d+)?조(?:의\d+)?)(.*)', locator)
    article, detail = match.groups() if match else (row['조문'], '')
    return {'law': row['문서명'], 'article': article, 'hang_ho': detail,
            'coordinate_scope': scope, 'quote': row['근거구절'],
            'group_id': row['근거그룹'] or f'basis-{n}', 'role': role}


def input_cases(path, fmt, labels=None):
    path = Path(path)
    lineage = {'input_path': str(path.resolve()), 'input_sha256': sha(path), 'format': fmt}
    if fmt == 'csv':
        grouped = {}
        for row in csv_rows(path):
            cid = row['문항ID'].strip()
            values = (row['질문'], row['기준답변'], row['기준일'])
            if not cid or not all(v.strip() for v in values): raise ValueError('case ID, question, reference answer and as-of required')
            if cid in grouped and grouped[cid]['_values'] != values: raise ValueError('same case ID has conflicting question/answer/date')
            case = grouped.setdefault(cid, {'id': cid, 'question': values[0], 'reference_answer': values[1],
                                            'as_of': values[2], 'targets': [], '_values': values})
            case['targets'].append(csv_target(row, len(case['targets']) + 1))
        for case in grouped.values(): case.pop('_values')
        cases = list(grouped.values())
    elif fmt == 'moleg':
        if labels is None: raise ValueError('moleg import requires --labels marked.json')
        source = read(path)
        if 'law.go.kr' not in source.get('source', ''): raise ValueError('expected public law.go.kr interpretation index')
        marked = read(labels)['cases']; lineage.update(labels_path=str(Path(labels).resolve()), labels_sha256=sha(labels))
        cases = []
        for case in source['cases']:
            tag = marked.get(case['case_no'])
            if not tag or not tag.get('decisive'): continue
            targets = []
            full = list(tag.get('decisive_full', []))
            for i, (law, article) in enumerate(tag['decisive']):
                detail = next((d for d in full if d.get('law') == law and d.get('jo') == article), {})
                if detail: full.remove(detail)
                scope = 'addendum' if article.startswith('부칙 ') else 'body'
                targets.append({'law': law, 'article': article.removeprefix('부칙 '),
                                'coordinate_scope': scope, 'role': 'required', 'group_id': f'basis-{i+1}',
                                'quote': detail.get('text', ''), 'hang_ho': detail.get('hang_ho', ''),
                                'legacy_node_id': detail.get('node_id'), 'why': detail.get('why', '')})
            cases.append({'id': case['case_no'], 'question': case['issue'], 'reference_answer': case['answer'],
                          'as_of': case['decided'], 'targets': targets,
                          'legacy_notes': tag, 'public_source': {'serial': case.get('serial'), 'label': case.get('label')}})
        missing = set(marked) - {c['case_no'] for c in source['cases']}
        if missing: raise ValueError('marked case missing from source index: ' + ','.join(sorted(missing)))
        lineage['source'] = source['source']
    elif fmt == 'cm':
        # Intended for GENOS when the selected source is restricted internal data.
        source = read(path); cases = []
        for case in source['cases']:
            targets = []
            for bucket, role in [('expected_articles', 'required'), ('required_companions', 'required'), ('auxiliary_evidence', 'reference')]:
                for row in case.get(bucket, []):
                    targets.append({**row, 'group_id': f'basis-{len(targets)+1}', 'role': role, 'legacy_bucket': bucket})
            raw_date = source.get('evidence_contract', {}).get('authority_as_of', '')
            date = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}' if len(raw_date) == 8 else raw_date
            cases.append({'id': case['id'], 'question': case['question'], 'reference_answer': case['reference_answer'],
                          'as_of': date, 'targets': targets, 'legacy_notes': {'reference_sha256': case.get('reference_sha256')}})
    elif fmt == 'registry':
        from .golden_registry import ready_cases
        cases, deferred = ready_cases(read(path))
        lineage['deferred'] = deferred
    else:
        raise ValueError('unsupported import format')
    if not cases or len({c['id'] for c in cases}) != len(cases): raise ValueError('empty or duplicate input cases')
    return cases, lineage


def match_target(target, sources):
    """Never guess aliases, revisions, addendum identities or a missing exact node."""
    matches = [s for s in sources if normalized(s['document_name']) == normalized(target.get('law', ''))
               and article_of(s) == normalized(target.get('article', ''))
               and s.get('coordinate_scope') == target.get('coordinate_scope', 'body')]
    if target.get('doc_id'): matches = [s for s in matches if s['document_id'] == target['doc_id']]
    if target.get('node') is not None: matches = [s for s in matches if str(s['unit_id']) == str(target['node'])]
    if target.get('quote'): matches = [s for s in matches if any(target['quote'] in b['text'] for b in s['blocks'])]
    return matches


def candidate_ref(source, target):
    quote = target.get('quote', '')
    block = next((b for b in source['blocks'] if quote and quote in b['text']), None)
    if block is None:
        block = next((b for b in source['blocks'] if len(b['text']) > 40), source['blocks'][0])
    return {'source_id': source['id'], 'document_id': source['document_id'],
            'source_artifact_sha256': source['source_artifact_sha256'], 'block_id': block['block_id'],
            'quote': quote or block['text'], 'locator': f"{target.get('coordinate_scope', 'body')} {target['article']}{target.get('hang_ho', '')}",
            'quote_selection': 'input_exact' if quote else 'suggested_block_requires_review'}


def prepare(path, fmt, generation, output, *, labels=None, suite_id='imported-golden', version='1'):
    cases, lineage = input_cases(path, fmt, labels)
    cat = catalog(generation); sources = cat.pop('sources')
    index = defaultdict(list)
    for s in sources: index[(normalized(s['document_name']), article_of(s))].append(s)
    draft = {'schema_version': VERSION, 'suite_id': suite_id, 'version': version,
             'import_provenance': lineage, 'mapping_binding': cat, 'cases': []}
    maps = []; used = {}; counts = Counter()
    for original in cases:
        case = {'id': original['id'], 'question': original['question'], 'reference_answer': original['reference_answer'],
                'as_of': original['as_of'], 'document_ids': [], 'expected_behavior': 'answer',
                'required_points': [original['reference_answer']], 'evidence_groups': [],
                'review': {'status': 'draft', 'by': '', 'at': ''},
                'import_notes': {k: v for k, v in original.items() if k not in LIFTED + ('targets', 'question', 'reference_answer')}}
        # Registry slicing fields travel with the case through review and freeze into the report.
        case.update({k: original[k] for k in LIFTED if k in original})
        groups = {}
        for n, target in enumerate(original['targets']):
            gid = target['group_id']; role = target['role']
            if gid in groups and groups[gid]['role'] != role: raise ValueError('conflicting roles in evidence group')
            group = groups.setdefault(gid, {'id': gid, 'role': role, 'any_of': []})
            matches = match_target(target, index.get((normalized(target.get('law', '')), normalized(target.get('article', ''))), []))
            status = 'UNIQUE_CANDIDATE' if len(matches) == 1 else 'AMBIGUOUS' if matches else 'NOT_FOUND'
            if not matches and target.get('quote'):
                matches = match_target({**target, 'quote': ''}, index.get((normalized(target.get('law', '')), normalized(target.get('article', ''))), []))
                if matches: status = 'TEXT_MISMATCH'
            counts[status] += 1
            entry = {'case_id': original['id'], 'target_index': n, 'group_id': gid, 'target': target,
                     'status': status, 'candidate_ids': [s['id'] for s in matches],
                     'version_status': 'HUMAN_REVIEW_REQUIRED', 'selected_source_id': matches[0]['id'] if status == 'UNIQUE_CANDIDATE' else None}
            maps.append(entry)
            for s in matches: used[s['id']] = s
            if status == 'UNIQUE_CANDIDATE': group['any_of'].append(candidate_ref(matches[0], target))
        case['evidence_groups'] = list(groups.values()); draft['cases'].append(case)
    bundle = {'schema_version': 'term-golden-authoring-v1', 'draft': draft, 'mappings': maps, 'sources': used,
              'summary': {'cases': len(cases), 'targets': len(maps), **dict(counts), 'approved_cases': 0},
              'note': 'Coordinate mapping only. Version/meaning approval and retrieval evaluation have not run.'}
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    write(output / 'draft.json', draft)
    write(output / 'mapping.json', seal(bundle))
    payload = json.dumps(bundle, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template_path = Path(__file__).with_name('golden_authoring.html')
    with (output / 'review.html').open('x', encoding='utf-8') as stream:
        stream.write(template_path.read_text(encoding='utf-8').replace('__GOLDEN_DATA__', payload))
    # Readable input sheet for Excel. Re-import after editing to regenerate candidates.
    with (output / 'questions.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(FIELDS)
        for case in cases:
            for t in case['targets']:
                writer.writerow([case['id'], case['question'], case['reference_answer'], case['as_of'],
                                 t.get('law', ''), t.get('article', '') + t.get('hang_ho', ''), t.get('coordinate_scope', 'body'),
                                 t['group_id'], t['role'], t.get('quote', '')])
    import shlex
    instructions = ('review.html을 허용된 내부 PC에서 열고 검토자 이름을 입력하세요.\n'
        '문항별 원문·기준답변을 검토하고 승인한 뒤 검토본 JSON을 내려받습니다.\n'
        '작업 저장 파일로 중단·재개할 수 있습니다. HTML 자체에는 수정 내용이 저장되지 않습니다.\n'
        '검토본을 GENOS에 업로드하고 아래 /업로드경로 및 /새검증폴더를 실제 경로로 바꿔 실행하세요.\n\n'
        'python 06_TOOLS/pipeline.py golden receive --authoring ' + shlex.quote(str(output.resolve())) +
        ' --generation ' + shlex.quote(str(Path(generation).resolve())) +
        ' --reviewed /업로드경로/' + shlex.quote(suite_id + '-reviewed.json') + ' --output /새검증폴더\n\n'
        'validation.html에서 결과를 확인하세요. 전 문항 통과 시 suite.json이 생성됩니다.\n'
        'suite.json을 기존 golden plan → run에 전달합니다. ADR·평가 조건·내부 모델 고정은 기존 절차를 따릅니다.\n'
        '평가 후 answer-review.html에서 답변을 채점하고, 채점본을 업로드해 golden report에 전달합니다.\n')
    (output / 'NEXT_STEPS.txt').write_text(instructions, encoding='utf-8')
    write(output / 'receipt.json', seal({'input': lineage, 'binding': cat,
          'summary': bundle['summary'], 'files': {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}}))
    return bundle
