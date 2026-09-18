"""Synthetic truncation recovery contracts; no model/quality experiment."""
import copy
import json

import pytest
import jsonschema

from lawrag.core.structure import recipe_output as output, recipe_regions as regions
from lawrag.core.structure import recipe_template as grammar, recipe_runtime as runtime, pipeline
from .test_recipe_runtime import isolated_env, regional_document, install_transport, response


def truncated():
    return runtime.NeedsReview('synthetic output cutoff', diagnostic={'code': 'OUTPUT_LENGTH_LIMIT'})


def rule(parent='$document'):
    return {'parent_family': parent, 'heading_position': 'line_start', 'sequence': 'consecutive',
            'reset_scope': 'document', 'rationale': 'Synthetic source evidence'}


def test_rule_batches_keep_all_source_and_allow_parent_in_another_batch():
    catalog = {f'f{i}': {} for i in range(7)}
    data = {'catalog': catalog, 'source_blocks': [{'idx': 0, 'text': 'All original source'}]}
    original = copy.deepcopy(data)
    seen = []
    def call(phase, system, request, schema, vision):
        assert request['catalog'] == catalog and request['source_blocks'] == data['source_blocks']
        chosen = request.get('output_families', list(catalog))
        seen.append(chosen)
        if len(chosen) > 2:
            raise truncated()
        return {'families': {f: rule('$document' if f == 'f0' else f'f{int(f[1:])-1}') for f in chosen}}
    checked = []
    result = grammar.compose(data, catalog, call, checked.append, lambda *a: None)
    assert data == original
    assert set(result['heading_rules']) == set(catalog)
    assert result['parent_map']['f6'] == 'f5'
    assert checked == [result]
    assert [len(x) for x in seen] == [7, 4, 2, 2, 2, 1]


def test_split_family_omission_is_not_accepted():
    catalog = {'a': {}, 'b': {}}
    def call(phase, system, request, schema, vision):
        if 'output_families' not in request:
            raise truncated()
        return {'families': {'a': rule()}}
    with pytest.raises(ValueError,match='document_template_validation_exhausted'):
        grammar.compose({'catalog': catalog}, catalog, call,
                        lambda *a: pytest.fail('must not compile incomplete rules'), lambda *a: None)


@pytest.mark.parametrize('bad', ['repeat', 'empty_more', 'over_budget', 'missing_completion'])
def test_output_pages_require_progress_and_explicit_completion(bad):
    schema = regions.detection_schema()
    schema['properties']['regions']['maxItems'] = 2
    item = {'start_block': 0, 'template_id': 'body', 'label': 'body', 'reason': 'source'}
    def call(phase, system, request, requested_schema, vision):
        if bad == 'empty_more': return {'regions': [], 'has_more': True}
        if bad == 'missing_completion': return {'regions': [item]}
        emitted = request['output_page']['emitted']
        row = {**item, 'start_block': len(emitted)} if bad == 'over_budget' else item
        return {'regions': [row], 'has_more': True}
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        output.array_pages('detect', 'test', {}, schema, call,
                           field='regions', save=lambda *a: None, vision=False, width=1)


def install_recovering_provider(monkeypatch, *, fail_detection=False, review_limit=None,
                                truncate_adjudication=False, interrupt_window=None):
    seen = []
    def reply(session, url, payload):
        content = payload['messages'][1]['content']
        data = json.loads(content if isinstance(content, str) else next(x['text'] for x in content if x['type'] == 'text'))
        seen.append(data)
        if 'outline' in data:
            if fail_detection and 'output_page' not in data:
                # Deliberately invalid partial content must never be parsed/used.
                body = response({}, 'length')
                body['choices'][0]['message']['content'] = '{"regions":[{"start_block":99999'
                return body
            rows = [{'start_block': 0, 'template_id': 'body', 'label': 'body', 'reason': 'source'},
                    {'start_block': 3, 'template_id': 'body', 'label': 'appendix', 'reason': 'independent numbering'}]
            if 'output_page' in data:
                page = data['output_page']
                if page['limit'] > 1: return response({}, 'length')
                start = len(page['emitted'])
                return response({'regions': rows[start:start+1], 'has_more': start+1 < len(rows)})
            return response({'regions': rows})
        if 'region_instances' in data:
            return response({'families': {f: rule() for f in data['catalog']}})
        window = data['page_window']
        is_adjudication = 'reviewed_state_id' in data
        if interrupt_window and window == interrupt_window:
            return 503
        if review_limit and len(window) > review_limit and is_adjudication == truncate_adjudication:
            return response({}, 'length')
        if not is_adjudication: return response({'opinions': [], 'summary': 'No visual defects'})
        return response({'verdict': 'approve', 'reviewed_state_id': data['reviewed_state_id'],
                         'issues': [], 'template_changes': [], 'opinion_decisions': []})
    install_transport(monkeypatch, reply)
    return seen


def test_truncated_region_list_is_regenerated_in_complete_pages(tmp_path, monkeypatch):
    pdf, blocks = regional_document(tmp_path, 6)
    original = copy.deepcopy(blocks)
    seen = install_recovering_provider(monkeypatch, fail_detection=True)
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MODE', 'full')
    result, meta = runtime.revise_pdf(pipeline, blocks, pdf, store=tmp_path/'store', document='source')
    pages = [d for d in seen if 'output_page' in d]
    assert [d['output_page']['limit'] for d in pages] == [4, 2, 1, 1]
    assert all(len(d['source_blocks']) == len(blocks) for d in pages)
    assert pages[-1]['output_page']['emitted'][0]['start_block'] == 0
    assert blocks == original
    assert meta['region_count'] == 2 and len(result.nodes()) == 6
    assert meta['coverage']['visually_reviewed_pages'] == list(range(1, 7))
    assert all(r['start_block'] != 99999 for r in result.stats['region_plan'])
    assert all(d.get('output_page', {}).get('field', 'regions') == 'regions' for d in pages)


@pytest.mark.parametrize('adjudication', [False, True])
def test_review_split_keeps_all_pages_and_every_adjacent_pair(tmp_path, monkeypatch, adjudication):
    pdf, blocks = regional_document(tmp_path, 6)
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MODE', 'full')
    seen = install_recovering_provider(monkeypatch, review_limit=2, truncate_adjudication=adjudication)
    _, meta = runtime.revise_pdf(pipeline, blocks, pdf, store=tmp_path/'store', document='source')
    windows = meta['coverage']['windows']
    assert all(len(w) <= 2 for w in windows)
    assert {p for w in windows for p in w} == set(range(1, 7))
    assert all(any(p in w and p+1 in w for w in windows) for p in range(1, 6))
    assert meta['status'] == 'visual_approved'
    checkpoint = json.loads(next((tmp_path/'structure-recipe-runs/checkpoints').glob('*.json')).read_text())['state']
    assert checkpoint['output_splits']
    for approval in checkpoint['approvals'].values():
        assert approval['verdict'] == 'approve'
    # Every fragment still goes through both roles, with the same exact scope.
    for w in windows:
        assert any(d.get('page_window') == w and 'reviewed_state_id' in d for d in seen)
        assert any(d.get('page_window') == w and 'recipe' in d and 'reviewed_state_id' not in d for d in seen)
    if adjudication:
        audit = tmp_path/'structure-recipe-runs'/meta['run_id']
        opinion_calls = [d for d in seen if 'recipe' in d and 'reviewed_state_id' not in d]
        # Parent opinions are evidence even when only the smaller children pass.
        assert len(list(audit.glob('window-review-*-vlm-opinions.json'))) == len(opinion_calls)


def test_split_review_resumes_without_repeating_approved_windows(tmp_path, monkeypatch):
    pdf, blocks = regional_document(tmp_path, 6)
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MODE', 'full')
    first = install_recovering_provider(monkeypatch, review_limit=2, interrupt_window=[4, 5])
    kwargs = dict(store=tmp_path/'store', document='source')
    with pytest.raises(runtime.NeedsReview):
        runtime.revise_pdf(pipeline, blocks, pdf, **kwargs)
    assert not (tmp_path/'structure-recipes.json').exists()
    assert any('outline' in d for d in first)
    resumed = install_recovering_provider(monkeypatch, review_limit=2)
    _, meta = runtime.revise_pdf(pipeline, blocks, pdf, **kwargs)
    assert not any('outline' in d for d in resumed)
    assert all(len(d['page_window']) <= 2 for d in resumed)
    assert not any(d['page_window'] == [1, 2] for d in resumed)
    assert meta['coverage']['visually_reviewed_pages'] == list(range(1, 7))


def test_persistent_truncation_never_drops_adjacent_page_review(tmp_path, monkeypatch):
    pdf, blocks = regional_document(tmp_path, 6)
    monkeypatch.setenv('STRUCTURE_RECIPE_REVIEW_MODE', 'full')
    seen = install_recovering_provider(monkeypatch, review_limit=1)
    with pytest.raises(runtime.NeedsReview) as failure:
        runtime.revise_pdf(pipeline, blocks, pdf, store=tmp_path/'store', document='source')
    assert failure.value.diagnostic['code'] == 'OUTPUT_LENGTH_LIMIT'
    windows = [d['page_window'] for d in seen if 'recipe' in d]
    assert windows and min(map(len, windows)) == 2
    assert not (tmp_path/'structure-recipes.json').exists()


def test_recovery_cannot_bypass_total_call_budget(tmp_path, monkeypatch):
    pdf, blocks = regional_document(tmp_path, 6)
    monkeypatch.setenv('STRUCTURE_RECIPE_MAX_CALLS', '2')
    seen = install_recovering_provider(monkeypatch, fail_detection=True)
    with pytest.raises(runtime.NeedsReview, match='model_call_budget'):
        runtime.revise_pdf(pipeline, blocks, pdf, store=tmp_path/'store', document='source')
    assert len(seen) == 2
    assert not (tmp_path/'structure-recipes.json').exists()
