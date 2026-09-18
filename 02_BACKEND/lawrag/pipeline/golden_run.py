"""Explicit GENOS codespace batch execution through the existing ASGI ask route."""
from __future__ import annotations

import asyncio
from contextlib import closing
import os
from pathlib import Path
import time

from lawrag.platform.workspace import load_layout
from semantic_runtime.contracts import digest, sha, write
from .golden import (catalog, now, product_request, read, report, review_template,
                     score, seal, verify)


def code_binding():
    layout = load_layout()
    files = {layout.root / 'service.py', layout.path('tools') / 'pipeline.py',
             layout.path('system') / 'PIPELINE.json',
             layout.path('backend') / 'lawrag/pipeline/golden.py',
             layout.path('backend') / 'lawrag/pipeline/golden_authoring.py',
             layout.path('backend') / 'lawrag/pipeline/golden_authoring.html',
             layout.path('backend') / 'lawrag/pipeline/golden_exchange.py',
             layout.path('backend') / 'lawrag/pipeline/golden_answers.html',
             layout.path('backend') / 'lawrag/pipeline/golden_run.py'}
    for directory in ('semantic_runtime', 'ENGINES/term_runtime', 'lawrag/platform'):
        files.update(p for p in (layout.path('backend') / directory).rglob('*') if p.suffix in ('.py', '.json'))
    files.update((layout.path('system') / 'SCHEMAS').glob('*.json'))
    return {str(p.relative_to(layout.root)): sha(p) for p in sorted(files)}


def environment_binding():
    # Secrets are neither copied nor hashed into persistent evaluation records.
    return {key: os.environ.get(key, '') for key in
            ('GENOS_BASE_URL', 'GENOS_QWEN_SERVING_ID', 'SEMANTIC_LLM_BACKEND')}


def check_adr(path, run_id, arm_id):
    value = read(path)
    if value.get('reservation', {}).get('status') != 'in_progress':
        raise ValueError('evaluation requires an in-progress ADR; completed experiments are immutable')
    design = value.get('design', {})
    if design.get('criteria_frozen_before_run') is not True or not design.get('success_criteria'):
        raise ValueError('freeze ADR criteria before planning evaluation')
    run = next((r for r in value.get('runs', []) if r['id'] == run_id), None)
    if not run or arm_id not in run['arm_ids'] or run.get('status') == 'complete':
        raise ValueError('ADR run/arm missing or already complete')
    return value


def make_plan(suite_path, generation, adr_manifest, run_id, arm_id, model):
    suite = verify(read(suite_path))
    current = catalog(generation); current.pop('sources')
    if current != suite['binding']:
        raise ValueError('gold mapping requires revalidation for this generation')
    adr = check_adr(adr_manifest, run_id, arm_id)
    env = environment_binding()
    if env['SEMANTIC_LLM_BACKEND'] != 'genos' or not env['GENOS_BASE_URL'] or not env['GENOS_QWEN_SERVING_ID']:
        raise ValueError('plan in GENOS with explicit internal model environment')
    if not model.strip(): raise ValueError('exact internal model ID required')
    return seal({'schema_version': 'term-golden-plan-v1', 'created_at': now(),
                 'suite_path': str(Path(suite_path).resolve()), 'suite_sha256': sha(suite_path),
                 'generation': str(Path(generation).resolve()), 'binding': current,
                 'adr_manifest': str(Path(adr_manifest).resolve()), 'adr_sha256': sha(adr_manifest),
                 'experiment_id': adr['experiment_id'], 'run_id': run_id, 'arm_id': arm_id,
                 'model': model, 'environment': env, 'code': code_binding(),
                 'execution_path': 'GENOS codespace / semantic_runtime.app / POST /v1/rag/ask',
                 'deployment_gateway_verified': False, 'gold_visible_to_product': False})


def check_plan(plan):
    verify(plan)
    if sha(plan['suite_path']) != plan['suite_sha256'] or sha(plan['adr_manifest']) != plan['adr_sha256']:
        raise ValueError('suite or ADR changed after planning')
    check_adr(plan['adr_manifest'], plan['run_id'], plan['arm_id'])
    if code_binding() != plan['code'] or environment_binding() != plan['environment']:
        raise ValueError('code or model environment drift after planning')
    cat = catalog(plan['generation']); cat.pop('sources')
    if cat != plan['binding']:
        raise ValueError('generation drift after planning')
    suite = verify(read(plan['suite_path']))
    if suite['binding'] != plan['binding']:
        raise ValueError('suite binding mismatch')
    return suite


async def run_cases(suite, call, output):
    """call receives only a product request; gold is applied after raw output is saved."""
    rows = []
    for index, case in enumerate(suite['cases']):
        folder = output / 'cases' / f'{index + 1:05d}'
        request = product_request(case)
        write(folder / 'request.json', request)
        started = time.monotonic()
        try:
            result = await call(request)
            write(folder / 'response.json', result)
            row = score(case, result, suite['binding'])
            row['answer'] = result['answer']
        except Exception as exc:
            # Error messages may contain credentials or provider response text.
            row = {'case_id': case['id'], 'execution_failed': True, 'execution_status': 'ERROR',
                   'error_type': type(exc).__name__, 'answer_quality': 'NOT_SCORED'}
        row['duration_seconds'] = time.monotonic() - started
        row['artifact_directory'] = str(folder.relative_to(output))
        write(folder / 'score.json', row)
        rows.append(row)
        print(f"[{index + 1}/{len(suite['cases'])}] {case['id']}: {row['execution_status']}", flush=True)
    return rows


def execute(plan_path, output):
    plan = verify(read(plan_path))
    suite = check_plan(plan)
    if os.environ.get('SEMANTIC_LLM_BACKEND') != 'genos' or not os.environ.get('GENOS_QWEN_KEY'):
        raise ValueError('GENOS internal provider credentials required; no fallback')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'plan.json', plan)
    write(output / 'suite.json', suite)
    # Single execution claim across output paths. No automatic replay of costly calls.
    claim_id = digest([plan['experiment_id'], plan['run_id'], plan['arm_id']])
    claim = Path(plan['adr_manifest']).parent / ('golden-' + claim_id + '.claim.json')
    write(claim, {'plan_sha256': plan['content_sha256'], 'output': str(output), 'started_at': now()})
    from semantic_runtime.app import create_app
    from semantic_runtime.provider import Haiku
    from semantic_runtime.storage import Store
    layout = load_layout()
    provider = Haiku(layout.root, output / 'providers', False, backend='genos', trust_zone='internal')
    # Discovery is internal and runs only after immutable execution records exist.
    _, actual_model = provider._resolve_genos({})
    if actual_model != plan['model']:
        raise ValueError('internal advertised model differs from frozen plan')
    app = create_app(output, plan['generation'], contracts_root=layout.root, provider=provider,
                     release={'evaluation_plan': plan['content_sha256']})

    async def run():
        import httpx
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://genos-codespace') as client:
                async def call(body):
                    response = await client.post('/v1/rag/ask', json=body)
                    response.raise_for_status()
                    return response.json()
                return await run_cases(suite, call, output)
    rows = asyncio.run(run())
    # Detect concurrent source/code drift; retain raw artifacts even when invalid.
    check_plan(plan)
    with closing(Store(plan['generation'])):
        pass
    write(output / 'rows.json', rows)
    write(output / 'reviews-template.json', review_template(suite, rows))
    report(suite, rows, output / 'report')
    from .golden_exchange import render_answers
    responses = {r['case_id']: read(output / r['artifact_directory'] / 'response.json')
                 for r in rows if 'answer_sha256' in r}
    render_answers(suite, rows, responses, output / 'answer-review.html')
    files = {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    write(output / 'receipt.json', seal({'schema_version': 'term-golden-run-v1',
          'completed_at': now(), 'plan_sha256': plan['content_sha256'], 'model': actual_model,
          'files': files, 'quality_certified': False, 'deployment_gateway_verified': False,
          'adr_finalization': 'REQUIRED_SEPARATELY'}))
