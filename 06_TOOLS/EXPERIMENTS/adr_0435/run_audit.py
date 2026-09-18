"""Frozen v32, synthetic PDFs, actual Gemini transport; no production registration."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0435-image-pattern-gemini-audit'
ART = ADR / 'artifacts'
CAND = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0435/v32/candidate.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def load():
    freeze = json.loads((ART / 'freeze.json').read_text())
    for path, expected in freeze['files'].items():
        assert sha(ROOT / path) == expected, path
    cand = json.loads(CAND.read_text())
    rev = cand['revisions'][-1]
    for row in rev['files']:
        assert sha(ROOT / row['frozen_path']) == row['snapshot_sha256'], row['frozen_path']
    example = next(r for r in rev['files'] if r['frozen_path'].endswith('structure/recipe_basic.py'))
    frozen_core = (ROOT / example['frozen_path']).parents[1]
    backend = frozen_core.parent.parent
    sys.path.insert(0, str(ROOT / '02_BACKEND'))
    # Only this research subprocess loads the explicit frozen package. Production
    # discovery, runtime registries and environment switches are not modified.
    import lawrag.core
    import lawrag.research
    import semantic_runtime
    lawrag.core.__path__.insert(0, str(frozen_core))
    lawrag.research.__path__.insert(0, str(backend / 'lawrag/research'))
    semantic_runtime.__path__.insert(0, str(backend / 'semantic_runtime'))
    from lawrag.core.structure import pipeline, recipe_runtime, recipe_visual_loop, recipe_basic
    from lawrag.core.structure.model import Block
    from lawrag.core.llm import Exchange
    from lawrag.research.experiment_client import GeminiExperimentClient
    for name, module in list(sys.modules.items()):
        if name.startswith('lawrag.core.structure'):
            assert Path(module.__file__).is_relative_to(frozen_core), name
    return pipeline, recipe_runtime, recipe_visual_loop, recipe_basic, Block, Exchange, GeminiExperimentClient


def parent_map(result):
    values = {}
    def visit(nodes, parent=None):
        for n in nodes:
            key = str(n.block_idx)
            if key in values:
                raise ValueError('Multiple headings in fixture block: ' + key)
            values[key] = parent
            visit(n.children, n.block_idx)
    visit(result.tree)
    return values


def main():
    pipeline, runtime, loop, basic, Block, Exchange, Client = load()
    settings = {'STRUCTURE_RECIPE_PROTOCOL': 'basic', 'STRUCTURE_RECIPE_VLM': 'on',
                'STRUCTURE_RECIPE_MAX_TOKENS': '16384', 'STRUCTURE_RECIPE_MAX_PAGES': '3',
                'STRUCTURE_RECIPE_MAX_CALLS': '24', 'STRUCTURE_RECIPE_MAX_CORRECTIONS': '6',
                'STRUCTURE_RECIPE_REVIEW_MAX_CHARS': '24000', 'STRUCTURE_RECIPE_MAX_CHARS': '160000',
                'STRUCTURE_RECIPE_REVIEW_MODE': 'full'}
    for k in list(os.environ):
        if k.startswith('STRUCTURE_RECIPE_'):
            del os.environ[k]
    os.environ.update(settings)
    cases = json.loads((ART / 'dataset/cases.json').read_text())
    # No gold file is read until every product call is finished.
    report = {'provider': 'gemini', 'model': 'gemini-3.1-flash-lite', 'runtime': runtime.VERSION,
              'run_id': 'run-001', 'source_kind': 'synthetic', 'main_wiring': 'unchanged',
              'settings': settings, 'cases': [], 'transport_note':
              'Research adapter substitutes Gemini for GENOS only; frozen GenosCalls._request and review/rebuild logic retained. Production metadata backend label remains genos and is not evidence of a GENOS call.'}
    started = time.monotonic()
    for case in cases:
        cid = case['case_id']; directory = ART / 'runs' / cid
        directory.mkdir(parents=True, exist_ok=False)
        client = Client(ROOT, directory / 'provider', max_calls=24, max_output_tokens=16384)
        blocks = [Block(**b) for b in json.loads((ROOT / case['blocks']).read_text())]
        baseline = pipeline.interpret(copy.deepcopy(blocks), doc=cid, llm=None, ledger=None, **case['hints'])
        write(directory / 'baseline.json', loop.tree_record(baseline))
        result = {'case_id': cid, 'baseline_parents': parent_map(baseline), 'started_at': time.time()}
        before = loop.digest([b.dump() for b in blocks])

        class Adapter:
            def __init__(self):
                self.log = []

            def structured(self, *, kind, system, user, schema, max_tokens, images=None):
                phase = kind.removeprefix('structure_recipe_'); then = time.monotonic()
                value = None; caught = None
                print(json.dumps({'event': 'call.start', 'case': cid, 'call': client.calls + 1,
                                  'phase': phase, 'input_chars': len(user), 'images': len(images or [])}), flush=True)
                try:
                    value = client.generate(system, json.loads(user), schema, images=images or [], phase=phase)
                except Exception as exc:
                    caught = exc
                path = directory / 'provider' / f'call-{client.calls:03d}-{phase}'
                raw = json.loads((path / 'response.json').read_text()) if (path / 'response.json').exists() else {}
                candidate = next(iter(raw.get('candidates', [])), {})
                text = ''.join(p['text'] for p in candidate.get('content', {}).get('parts', []) if 'text' in p and not p.get('thought'))
                finish = candidate.get('finishReason')
                error = ''
                if caught:
                    # The shared client validates locally; retain complete JSON
                    # schema errors for the unchanged small-response retry owner.
                    if finish == 'STOP':
                        try:
                            value = json.loads(text)
                        except ValueError:
                            error = 'JSONDecodeError: incomplete or invalid response'
                    else:
                        error = type(caught).__name__ + ': ' + str(caught)
                usage = raw.get('usageMetadata', {})
                exchange = Exchange(kind=kind, system=system, user=user, raw_response=text,
                    parsed=value, model=raw.get('modelVersion', client.model),
                    usage={'input_tokens': usage.get('promptTokenCount'),
                           'output_tokens': usage.get('candidatesTokenCount'),
                           'thinking_tokens': usage.get('thoughtsTokenCount', 0)},
                    stop_reason='end_turn' if finish == 'STOP' else 'max_tokens' if finish == 'MAX_TOKENS' else str(finish),
                    error=error, images=len(images or []), dur_ms=round((time.monotonic() - then) * 1000))
                self.log.append(exchange)
                print(json.dumps({'event': 'call.end', 'case': cid, 'call': client.calls,
                                  'phase': phase, 'finish': finish, 'usage': usage, 'error': error}), flush=True)
                return value

        class Calls(runtime.GenosCalls):
            def __init__(self, journal, images, *, max_calls=24):
                self.journal = journal; self.images = images; self.protocol = 'basic'
                self.calls = 0; self.max_calls = max_calls; self.max_tokens = 16384
                self.client = Adapter(); self.model = client.model
                journal.event('provider.configured', backend='gemini-research', model=self.model, protocol=self.protocol)

        runtime.GenosCalls = Calls
        os.environ['STRUCTURE_RECIPE_TAGS'] = str(directory / 'tags.json')
        t = time.monotonic()
        try:
            tree, meta = runtime.revise_pdf(pipeline, blocks, ROOT / case['pdf'], store=directory / 'store',
                                          document=cid, hints=case['hints'])
            result.update(status='complete', meta=meta, final_parents=parent_map(tree))
            count = client.calls
            replay, cached = runtime.revise_pdf(pipeline, blocks, ROOT / case['pdf'], store=directory / 'store',
                                               document=cid, hints=case['hints'])
            result.update(cache_calls=client.calls - count,
                          replay_identical=loop.tree_record(replay) == loop.tree_record(tree), cached_meta=cached)
        except Exception as exc:
            result.update(status='failed', error=str(exc), diagnostic=getattr(exc, 'diagnostic', None))
            (directory / 'traceback.txt').write_text(traceback.format_exc())
        result.update(seconds=round(time.monotonic() - t, 3), calls=client.calls, usage=client.usage,
                      source_unchanged=before == loop.digest([b.dump() for b in blocks]) and sha(ROOT / case['pdf']) == case['pdf_sha256'])
        write(directory / 'result.json', result); report['cases'].append(result)
        write(ART / 'results.partial.json', report)
        print(json.dumps({'event': 'case.end', 'case': cid, 'status': result['status'], 'calls': client.calls}), flush=True)
    gold = json.loads((ART / 'dataset/gold.json').read_text())
    for result in report['cases']:
        expected = gold[result['case_id']]['parents_by_block']
        result['expected_parents'] = expected
        result['baseline_correct'] = result['baseline_parents'] == expected
        result['final_correct'] = result.get('final_parents') == expected
        result['pass'] = result['status'] == 'complete' and result['final_correct'] and result['source_unchanged'] and result.get('replay_identical') and result.get('cache_calls') == 0
        result['false_visual_approval'] = result['status'] == 'complete' and not result['final_correct']
    report.update(status='complete', seconds=round(time.monotonic() - started, 3))
    write(ART / 'results.json', report)
    print(json.dumps({'event': 'audit.end', 'passed': sum(bool(x['pass']) for x in report['cases']), 'total': len(cases)}), flush=True)


if __name__ == '__main__':
    main()
