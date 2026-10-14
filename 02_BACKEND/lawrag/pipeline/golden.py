"""Offline golden registry and scoring. Never imported by the product pipeline."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path

from semantic_runtime.contracts import digest, sha, write
from semantic_runtime.storage import Store
from semantic_runtime.term_index import TermIndex, ro

VERSION = 'term-golden-v1'
STAGES = ('initial', 'first_round', 'cumulative', 'selected', 'cited')
# reconciliation: 여러 규범(위계·특별법·내규↔외규)을 함께 정리해야 답이 나온다.
# temporal: 개정·시행일·경과규정이 답을 가른다.
TAGS = ('reconciliation', 'temporal')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def now():
    return datetime.now(timezone.utc).isoformat()


def seal(value):
    return {**value, 'content_sha256': digest(value)}


def verify(value):
    if value.get('content_sha256') != digest({k: v for k, v in value.items() if k != 'content_sha256'}):
        raise ValueError('content hash mismatch')
    return value


def catalog(generation):
    """Resolve only the selected generation's verified navigation index."""
    with closing(Store(generation)) as store:
        binding = store.manifest.get('navigation')
        if binding:
            index_root = store.path
        else:
            # Existing releases bind the index through the same PIPELINE config
            # that TermAgent uses. It is not always inside the generation folder.
            from lawrag.platform.workspace import load_layout
            index_root = load_layout().root
            config = read(index_root / '00_SYSTEM/PIPELINE.json')
            binding = next(n for n in config['profiles']['legal-rag']['nodes'] if n['id'] == 'retrieve')['parameters']['term_agent']['index']
        index_path = (index_root / binding['path']).resolve()
        index_path.relative_to(index_root)
        if sha(index_path / 'manifest.json') != binding['manifest_sha256']:
            raise ValueError('navigation manifest hash mismatch')
        index = TermIndex(index_path, store)
        with closing(ro(index.path / 'navigation.sqlite')) as db:
            sources = [json.loads(r[0]) for r in db.execute('SELECT json FROM source ORDER BY id')]
        for source in sources:
            if source['unit_id'] is not None:
                # Read only ancestors, not the entire article again for catalog.
                ancestors = []; uid = source['unit_id']; seen = set()
                while uid is not None:
                    if uid in seen: raise ValueError('source ancestor cycle')
                    seen.add(uid)
                    row = store.db.execute('SELECT parent_id,json FROM source_unit WHERE document_id=? AND unit_id=?', (source['document_id'], str(uid))).fetchone()
                    if not row: raise ValueError('missing catalog ancestor')
                    unit = json.loads(row['json'])
                    if uid == source['unit_id']: source['coordinate_scope'] = unit.get('coordinate_scope')
                    ancestors.append({'id': str(uid), 'title': unit.get('title', unit.get('surface', '')), 'family': unit.get('family')})
                    uid = str(row['parent_id']) if row['parent_id'] is not None else None
                source['ancestors'] = list(reversed(ancestors))
                if not source.get('coordinate_scope'):
                    source['coordinate_scope'] = 'addendum' if any('부칙' in str(a['family']) or str(a['title']).startswith('부칙') for a in ancestors) else 'body'
            else:
                source['coordinate_scope'] = 'unstructured'
        return {
            'generation_id': store.manifest['generation_id'],
            'store_sha256': store.manifest['store_sha256'],
            'manifest_sha256': sha(store.path / 'manifest.json'),
            'index_sha256': index.manifest['index_sha256'],
            'sources': sources,
        }


def template():
    return {'schema_version': VERSION, 'suite_id': 'internal-golden', 'version': '1',
            'cases': [{'id': 'case-001', 'question': '질문을 입력하세요',
                       'as_of': 'YYYY-MM-DD', 'document_ids': [],
                       'expected_behavior': 'answer',
                       'required_points': ['필수 결론과 조건·예외를 작성하세요'],
                       'evidence_groups': [{'id': 'basis-1', 'role': 'required', 'any_of': [
                           {'source_id': 'catalog에서 선택', 'document_id': '문서 버전 ID',
                            'source_artifact_sha256': '원본 문서 SHA256',
                            'locator': '본칙 제1조 제1항', 'block_id': '블록 ID',
                            'quote': '해당 블록의 정답 근거 원문'}]}],
                       'review': {'status': 'draft', 'by': '', 'at': ''}}]}


def freeze(draft, generation):
    return _freeze_with_catalog(draft, catalog(generation))


def _freeze_with_catalog(draft, source_catalog):
    """Shared validation for an entire suite or per-case upload diagnostics."""
    if draft.get('schema_version') != VERSION:
        raise ValueError('unsupported golden schema')
    if not draft.get('suite_id') or not draft.get('version') or not draft.get('cases'):
        raise ValueError('suite ID, version and nonempty cases required')
    cat = dict(source_catalog)
    sources = {s['id']: s for s in cat.pop('sources')}
    if draft.get('mapping_binding') is not None and draft['mapping_binding'] != cat:
        raise ValueError('authoring generation changed; remap and review before freeze')
    cases = json.loads(json.dumps(draft['cases']))
    ids = set()
    known_docs = {s['document_id'] for s in sources.values()}
    for case in cases:
        cid = case['id']
        if not isinstance(cid, str) or not cid.strip() or cid in ids:
            raise ValueError('empty or duplicate case ID')
        ids.add(cid)
        if not isinstance(case.get('question'), str) or not case['question'].strip():
            raise ValueError('question required')
        datetime.strptime(case['as_of'], '%Y-%m-%d')
        docs = case['document_ids']
        if not isinstance(docs, list) or any(not isinstance(d, str) for d in docs) or set(docs) - known_docs:
            raise ValueError('unknown document scope')
        review = case['review']
        if review.get('status') != 'approved' or not review.get('by', '').strip():
            raise ValueError('human approval required before freeze')
        datetime.fromisoformat(review['at'])
        behavior = case['expected_behavior']
        if behavior not in ('answer', 'ask_user', 'abstain'):
            raise ValueError('unknown expected behavior')
        points = case['required_points']
        if not isinstance(points, list) or not points or any(not isinstance(p, str) or not p.strip() for p in points):
            raise ValueError('required answer/refrain criteria missing')
        groups = case['evidence_groups']
        if behavior == 'answer' and not any(g['role'] == 'required' for g in groups):
            raise ValueError('answer case requires evidence')
        tags = case.get('tags', [])
        if not isinstance(tags, list) or set(tags) - set(TAGS):
            raise ValueError('unknown case tag')
        if 'collection' in case and (not isinstance(case['collection'], str) or not case['collection'].strip()):
            raise ValueError('invalid case collection')
        if 'reconciliation' in tags and len({ref['document_id'] for g in groups if g['role'] == 'required'
                                             for ref in g['any_of']}) < 2:
            raise ValueError('reconciliation case needs required evidence from two documents')
        gids = set()
        for group in groups:
            if not group['id'] or group['id'] in gids or group['role'] not in ('required', 'reference') or not group['any_of']:
                raise ValueError('invalid evidence group')
            gids.add(group['id'])
            for ref in group['any_of']:
                source = sources.get(ref['source_id'])
                if not source or source['document_id'] != ref['document_id'] or source['source_artifact_sha256'] != ref['source_artifact_sha256']:
                    raise ValueError('unresolved source/version mapping')
                if docs and source['document_id'] not in docs:
                    raise ValueError('gold outside requested scope')
                block = next((b for b in source['blocks'] if b['block_id'] == ref['block_id']), None)
                if not ref.get('locator') or not ref.get('quote') or not block or ref['quote'] not in block['text']:
                    raise ValueError('gold quote must match the exact source block')
                ref['article_coordinate'] = source['article_coordinate']
                ref['text_sha256'] = source['text_sha256']
    return seal({'schema_version': VERSION, 'suite_id': draft['suite_id'], 'version': draft['version'],
                 'frozen_at': now(), 'binding': cat, 'cases': cases,
                 'metric_unit': 'required evidence group; alternatives are OR, groups are AND',
                 'gold_visible_to_product': False,
                 'import_provenance': draft.get('import_provenance')})


def product_request(case):
    # An explicit allowlist prevents answers, golden coordinates and review from leaking.
    return {'question': case['question'], 'document_ids': case['document_ids'], 'use_llm': True}


def score(case, result, binding, *, native_journal=None):
    answer = result['answer']
    if answer['generation_id'] != binding['generation_id'] or answer['source_store_sha256'] != binding['store_sha256']:
        raise ValueError('result generation mismatch')
    if result['query']['question'] != case['question']:
        raise ValueError('result question mismatch')
    if case['document_ids'] and set(result['query']['scope']['document_version_ids']) != set(case['document_ids']):
        raise ValueError('result scope mismatch')
    retrieval = result['retrieval']
    state = retrieval['term_agent']
    native = None
    if result.get('response_schema') == 'legal-agent-unified-response-v1':
        if native_journal is None:
            raise ValueError('native golden scoring requires an explicit journal')
        from .native_trace import native_result_stages
        native = native_result_stages(result, native_journal)
    elif state.get('use_llm') is not True:
        raise ValueError('source-only result cannot evaluate answer quality')
    trace = state.get('trace', [])
    # No resolved term is an observed empty search; absent trace on failure is unknown.
    first = trace[0] if trace else None
    initial = ([r['id'] for r in first['search_results']] if first and 'search_results' in first
               else ([] if state.get('status') == 'NO_RESOLVED_TERM' else None))
    first_round = first.get('after_evidence_ids') if first else initial
    stages = {name: native['stages'][name] for name in STAGES} if native else {'initial': initial, 'first_round': first_round,
              'cumulative': [s['id'] for s in retrieval['candidates']],
              'selected': [s['id'] for s in result['assembly']['context']],
              'cited': [sid for c in answer['claims'] for sid in c['source_ids']]}
    groups = [g for g in case['evidence_groups'] if g['role'] == 'required']
    metrics = {}
    previous = set()
    for name, raw in stages.items():
        observed = raw is not None
        found = set(raw or [])
        hits = {g['id'] for g in groups if found & {r['source_id'] for r in g['any_of']}}
        metrics[name] = {'observed': observed, 'source_ids': sorted(found), 'count': len(found),
                         'hit_groups': sorted(hits) if observed else [],
                         'missing_groups': sorted({g['id'] for g in groups} - hits) if observed else [],
                         'recall': len(hits) / len(groups) if groups and observed else None,
                         'all_required': len(hits) == len(groups) if groups and observed else None,
                         'lost_groups_from_previous': sorted(previous - hits) if observed else []}
        previous = hits if observed else set()
    selected = set(stages['selected'] or [])
    row = {'case_id': case['id'], 'execution_status': native['run_status'] if native else state['status'],
            'execution_failed': native['run_status'] != 'COMPLETED' if native else state['status'] == 'EXECUTION_FAILURE',
            'provider_calls': native['usage']['attempts'] if native else state.get('calls'),
            'metrics': metrics, 'citation_ids_outside_context': sorted(set(stages['cited'] or []) - selected),
            'answer_quality': 'PENDING_HUMAN_REVIEW', 'answer_sha256': digest(answer),
            'note': 'Article presence is not semantic support or paragraph-level answer correctness.'}
    if native:
        # IDs indicate presence. These spans independently expose acquisition and delivery.
        row['native_evidence'] = {k: native[k] for k in ('journal_path', 'snapshot_sha256', 'run_id', 'stage_refs', 'selection_basis', 'evidence_coverage', 'presentation_coverage', 'usage')}
        row['native_evidence']['presented_source_ids'] = native['stages']['presented']
    return row


def review_template(suite, rows):
    byid = {c['id']: c for c in suite['cases']}
    return {'suite_sha256': suite['content_sha256'],
            'run_binding': digest([suite['content_sha256'], rows]), 'reviews': [
        {'case_id': r['case_id'], 'answer_sha256': r['answer_sha256'], 'by': '', 'at': '',
         'required_points_met': [None for _ in byid[r['case_id']]['required_points']],
         'behavior_correct': None, 'citations_supported': None,
         'no_unsupported_claims': None, 'notes': ''}
        for r in rows if 'answer_sha256' in r]}


def apply_reviews(suite, rows, review):
    rows = json.loads(json.dumps(rows))
    if review['suite_sha256'] != suite['content_sha256']:
        raise ValueError('review suite mismatch')
    if review.get('run_binding') is not None and review['run_binding'] != digest([suite['content_sha256'], rows]):
        raise ValueError('review run mismatch')
    byid = {r['case_id']: r for r in rows}
    cases = {c['id']: c for c in suite['cases']}
    seen = set()
    for item in review['reviews']:
        cid = item['case_id']
        if cid in seen or cid not in byid or item['answer_sha256'] != byid[cid].get('answer_sha256'):
            raise ValueError('duplicate, unknown or stale answer review')
        seen.add(cid)
        # Empty templates are pending, never a pass.
        if not item['by'].strip():
            continue
        datetime.fromisoformat(item['at'])
        flags = item['required_points_met']
        if len(flags) != len(cases[cid]['required_points']):
            raise ValueError('review point count mismatch')
        flags = [*flags, item['behavior_correct'], item['citations_supported'], item['no_unsupported_claims']]
        if any(type(f) is not bool for f in flags):
            raise ValueError('review must explicitly judge every criterion')
        byid[cid]['answer_quality'] = ('PASS' if all(flags) and not byid[cid]['execution_failed']
                                      and not byid[cid]['citation_ids_outside_context'] else 'FAIL')
        byid[cid]['human_review'] = item
    return rows


def slice_summary(rows):
    summary = {'total': len(rows), 'failed_or_invalid': sum(r.get('execution_failed', True) for r in rows),
               'reviewed': sum(r.get('answer_quality') in ('PASS', 'FAIL') for r in rows),
               'answer_pass': sum(r.get('answer_quality') == 'PASS' for r in rows), 'stages': {}}
    for stage in STAGES:
        values = [r['metrics'][stage]['recall'] for r in rows if 'metrics' in r and r['metrics'][stage]['recall'] is not None]
        summary['stages'][stage] = {'measured_cases': len(values),
                                    'mean_recall': sum(values) / len(values) if values else None}
    summary['answer_pass_over_all'] = summary['answer_pass'] / len(rows)
    summary['answer_pass_over_reviewed'] = summary['answer_pass'] / summary['reviewed'] if summary['reviewed'] else None
    return summary


def report(suite, rows, output):
    output = Path(output)
    if len(rows) != len(suite['cases']) or {r['case_id'] for r in rows} != {c['id'] for c in suite['cases']}:
        raise ValueError('report must include every case exactly once')
    summary = slice_summary(rows)
    case_map = {c['id']: c for c in suite['cases']}
    # 합친 suite 는 묶음·태그별로도 같은 지표를 낸다. 층이 작을수록 노이즈 폭이 크다.
    for key, values_of in (('by_collection', lambda c: [c['collection']] if c.get('collection') else []),
                           ('by_tag', lambda c: c.get('tags', []))):
        groups = {}
        for row in rows:
            for value in values_of(case_map[row['case_id']]):
                groups.setdefault(value, []).append(row)
        if groups:
            summary[key] = {value: slice_summary(members) for value, members in sorted(groups.items())}
    durations = sorted(r['duration_seconds'] for r in rows if 'duration_seconds' in r)
    summary['latency_seconds'] = {f'p{p}': durations[max(0, math.ceil(len(durations)*p/100)-1)] if durations else None for p in (50, 95)}
    summary['provider_calls_recorded'] = sum(r.get('provider_calls') or 0 for r in rows)
    write(output / 'report.json', seal({'suite_sha256': suite['content_sha256'], 'summary': summary, 'cases': rows}))
    table = []
    for row in rows:
        cells = [row['case_id'], case_map[row['case_id']]['question']]
        for stage in STAGES:
            value = row.get('metrics', {}).get(stage, {}).get('recall')
            cells.append('미측정/해당 없음' if value is None else f'{value:.1%}')
        cells += [row.get('answer_quality', '미측정'), row.get('execution_status', 'ERROR')]
        table.append('<tr>' + ''.join('<td>' + html.escape(str(c)) + '</td>' for c in cells) + '</tr>')
    content = '<!doctype html><meta charset="utf-8"><title>골든 평가</title><style>body{font:15px system-ui;margin:30px}td,th{border:1px solid #ddd;padding:10px}table{border-collapse:collapse}pre{white-space:pre-wrap}</style><h1>골든 평가</h1><p>회수율은 필수 근거 그룹 기준입니다. 인용 ID 일치는 답변 정확성 판정이 아닙니다. 미측정과 미검토는 통과로 계산하지 않습니다.</p><pre>'
    content += html.escape(json.dumps(summary, ensure_ascii=False, indent=2)) + '</pre><table><tr>'
    content += ''.join('<th>' + h + '</th>' for h in ['문항', '질문', '최초', '첫 확장', '누적', '선택', '인용', '답변 검토', '실행'])
    content += '</tr>' + ''.join(table) + '</table><h2>문항별 상세</h2>'
    for row in rows:
        detail = {'gold': case_map[row['case_id']], 'result': row}
        content += '<details><summary>' + html.escape(row['case_id']) + '</summary><pre>' + html.escape(json.dumps(detail, ensure_ascii=False, indent=2)) + '</pre></details>'
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'report.html').open('x', encoding='utf-8') as stream:
        stream.write(content)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description='GENOS 원문 세대 기반 골든 관리·평가')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('template'); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('catalog'); p.add_argument('--generation', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('freeze'); p.add_argument('--draft', required=True, type=Path); p.add_argument('--generation', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('import', help='간단 CSV 또는 기존 골든을 원문 후보·검토 화면으로 변환')
    p.add_argument('--input', required=True, type=Path); p.add_argument('--format', choices=['csv', 'moleg', 'cm', 'registry'], required=True)
    p.add_argument('--labels', type=Path); p.add_argument('--generation', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p.add_argument('--suite-id', default='imported-golden'); p.add_argument('--version', default='1')
    p = sub.add_parser('registry', help='CM·내규 등 골든 묶음을 하나의 등록부로 합치고 문항별 진행 상태를 계산')
    p.add_argument('--cm', type=Path); p.add_argument('--internal', type=Path, help='내규 골든 작성 CSV')
    p.add_argument('--collection', action='append', nargs=2, metavar=('NAME', 'CSV'),
                   help='이름을 지정한 질문 CSV 묶음; 반복 지정 가능 (예: risk_cm 질문.csv)')
    p.add_argument('--annotations', type=Path, help='{문항ID: {"tags": [...]}}'); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('registry-status'); p.add_argument('--registry', required=True, type=Path)
    p = sub.add_parser('csv-template'); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('receive', help='업로드한 골든 검토본 검증 및 suite 생성')
    for flag in ('authoring', 'reviewed', 'generation', 'output'):
        p.add_argument('--' + flag, required=True, type=Path)
    p = sub.add_parser('review-answers', help='완료된 평가의 오프라인 답변 채점 화면 생성')
    p.add_argument('--run', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('plan')
    for flag in ('suite', 'generation', 'adr_manifest', 'output'): p.add_argument('--' + flag.replace('_', '-'), required=True, type=Path)
    for flag in ('run_id', 'arm_id', 'model'): p.add_argument('--' + flag.replace('_', '-'), required=True)
    p = sub.add_parser('run'); p.add_argument('--plan', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('report'); p.add_argument('--run', required=True, type=Path); p.add_argument('--reviews', type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('score-native', help='명시한 완료 v6 기록과 저장 답변을 대조하여 오프라인 채점')
    for flag in ('suite', 'response', 'journal', 'output'): p.add_argument('--' + flag, required=True, type=Path)
    p.add_argument('--case-id', required=True)
    args = parser.parse_args(argv)
    if args.command == 'template': write(args.output, template())
    elif args.command == 'catalog': write(args.output, catalog(args.generation))
    elif args.command == 'freeze': write(args.output, freeze(read(args.draft), args.generation))
    elif args.command in ('registry', 'registry-status'):
        from . import golden_registry
        if args.command == 'registry':
            registry = golden_registry.build(args.cm, args.internal, args.annotations, collections=args.collection)
            write(args.output, registry)
        else:
            registry = golden_registry.verify(read(args.registry))
        print(json.dumps(registry['summary'], ensure_ascii=False, indent=2))
        return 0
    elif args.command == 'csv-template':
        from .golden_authoring import csv_template
        csv_template(args.output)
    elif args.command == 'receive':
        from .golden_exchange import receive
        result = receive(args.authoring, args.reviewed, args.generation, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['ok'] else 2
    elif args.command == 'review-answers':
        from .golden_exchange import review_answers
        review_answers(args.run, args.output)
    elif args.command == 'import':
        from .golden_authoring import prepare
        prepare(args.input, args.format, args.generation, args.output, labels=args.labels, suite_id=args.suite_id, version=args.version)
    elif args.command == 'plan':
        from .golden_run import make_plan
        write(args.output, make_plan(args.suite, args.generation, args.adr_manifest, args.run_id, args.arm_id, args.model))
    elif args.command == 'run':
        from .golden_run import execute
        execute(args.plan, args.output)
    elif args.command == 'score-native':
        suite = verify(read(args.suite))
        matches = [c for c in suite['cases'] if c['id'] == args.case_id]
        if len(matches) != 1: raise ValueError('exact native golden case required')
        write(args.output, score(matches[0], read(args.response), suite['binding'], native_journal=args.journal))
    elif args.command == 'report':
        from .golden_exchange import checked_run
        suite, rows, _ = checked_run(args.run)
        if args.reviews: rows = apply_reviews(suite, rows, read(args.reviews))
        report(suite, rows, args.output)
    print(json.dumps({'status': 'ok', 'command': args.command, 'output': str(args.output)}, ensure_ascii=False))
    return 0
