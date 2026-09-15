"""Bounded PDF evidence windows over one immutable, globally rebuilt structure.

Page types are deterministic layout hints, not semantic classifications. Sampled
visual review never implies that a model inspected every page.
"""
import copy
from collections import defaultdict

from . import recipe_visual_loop as loop, recipe_rules, recipe_evidence, recipe_template, recipe_regions

VERSION = 'pdf-format-region-review-v1'


def inventory(pdf, blocks):
    """Inspect every PDF page and account for every original source block."""
    if [b.idx for b in blocks] != list(range(len(blocks))):
        raise ValueError('noncontiguous_source_blocks')
    if [b.page for b in blocks] != sorted(b.page for b in blocks):
        raise ValueError('source_page_order_changed')
    by_page = defaultdict(list)
    for b in blocks:
        if type(b.page) is not int or not 1 <= b.page <= len(pdf):
            raise ValueError('invalid_source_page')
        by_page[b.page].append(b)
    result = []
    for index, page in enumerate(pdf):
        p = index + 1; rows = by_page[p]
        text = page.get_text().strip()
        pictures = bool(page.get_images())
        types = {'body'}; risks = set()
        if not text and pictures: types.add('scan')
        if any(b.kind == 'table' for b in rows): types.add('table')
        if any(b.kind == 'figure' for b in rows): types.add('figure')
        if any(b.text.lstrip().startswith(('별표', '[별표', '별지', '[별지')) for b in rows): types.add('annex')
        if not rows:
            risks.add('no_source_blocks')
            if text or pictures: risks.add('missing_text_or_ocr')
            else: types.add('empty_or_vector_only')
        if 'scan' in types and not any(b.text.strip() and b.kind in {'text', 'table'} for b in rows):
            risks.add('missing_text_or_ocr')
        if rows and not any(b.text.strip() for b in rows): risks.add('no_readable_blocks')
        styles = sorted({(b.font_name, bool(b.bold), bool(b.is_heading), round(b.size_ratio or 1, 1)) for b in rows if b.kind == 'text'})
        signature = loop.digest([sorted(types), styles, round(page.rect.width/page.rect.height, 1)])
        result.append({'page': p, 'types': sorted(types), 'risks': sorted(risks),
                       'layout': signature, 'block_ids': [b.idx for b in rows]})
    return result


def audit(blocks, result, pages, *, strict=True):
    """Check whole-document ordering/ancestry/spans; nominate anomalies for vision."""
    risks = defaultdict(set)
    def issue(node, message):
        if strict: raise ValueError(message)
        if not 0 <= node.block_idx < len(blocks): raise ValueError('invalid_source_block')
        risks[blocks[node.block_idx].page].add(message)
    def visit(nodes, parent=None):
        last = -1; ordinals = {}
        for n in nodes:
            lo, hi = n.span
            if not 0 <= lo < hi <= len(blocks) or n.block_idx != lo:
                issue(n, 'invalid_tree_source_span')
            if lo < last: issue(n, 'overlapping_sibling_spans')
            last = hi
            if parent and not (parent.span[0] <= lo < hi <= parent.span[1] and n.level > parent.level):
                issue(n, 'invalid_tree_parent')
            if 0 <= lo < len(blocks) and n.page != blocks[lo].page: issue(n, 'tree_page_mismatch')
            if n.ordinal and len(n.ordinal) == 1:
                previous = ordinals.get(n.family)
                if previous is not None and n.ordinal[0] != previous+1:
                    risks[n.page].add('number_sequence_change')
                ordinals[n.family] = n.ordinal[0]
            visit(n.children, n)
    visit(result.tree)
    for family, ordinal, idx, offset in result.stats.get('recipe_missing_anchors', []):
        risks[blocks[idx].page].add('numbered_anchor_missing_without_reference_decision')
    try: loop.check_source_anchors(result, blocks)
    except ValueError as exc:
        if strict: raise
        groups = defaultdict(list)
        for n in result.nodes(): groups[n.block_idx].append(n)
        for idx, ns in groups.items():
            if len(ns)>1:
                try: loop.check_source_anchors(result, blocks, only_blocks={idx})
                except ValueError as local_exc: risks[blocks[idx].page].add(str(local_exc))
    covered = set()
    for n in result.tree: covered.update(range(*n.span))
    for b in blocks:
        if b.kind != 'furniture' and b.idx not in covered and b.text.strip(): risks[b.page].add('outside_structure')
    for p in pages:
        risks[p['page']].update(p['risks'])
    return {p: sorted(v) for p, v in sorted(risks.items()) if v}


def select(pages, blocks, result, risks):
    """First/last of every layout + transitions + structural families + anomalies."""
    reasons = defaultdict(set)
    by_type = defaultdict(list)
    for p in pages: by_type[p['layout']].append(p['page'])
    for values in by_type.values():
        reasons[values[0]].add('layout_first'); reasons[values[-1]].add('layout_last')
    for before, after in zip(pages, pages[1:]):
        if before['layout'] != after['layout']:
            reasons[before['page']].add('layout_boundary'); reasons[after['page']].add('layout_boundary')
    families = defaultdict(list)
    for n in result.nodes(): families[n.family].append(n.page)
    for values in families.values():
        reasons[min(values)].add('family_first'); reasons[max(values)].add('family_last')
    for b in blocks:
        if b.kind == 'table':
            # Tables are sensitive; include adjoining pages for continued tables.
            reasons[b.page].add('table')
    for page, values in risks.items(): reasons[page].update(values)
    return {p: sorted(v) for p, v in sorted(reasons.items())}


def windows(selected, total, width):
    """Contiguous windows include neighbours while retaining global page/block IDs."""
    if width < 3: raise ValueError('adaptive_window_requires_at_least_3_pages')
    output = []
    for page in sorted(selected):
        lo = max(1, page-1); hi = min(total, page+1)
        if output and hi-output[-1][0]+1 <= width:
            output[-1][1] = max(output[-1][1], hi)
        else: output.append([lo, hi])
    return [list(range(lo, hi+1)) for lo, hi in output]


def context(blocks, catalog, pages, result, recipe=None):
    wanted = set(pages); rows = [b for b in blocks if b.page in wanted]
    ids = {b.idx for b in rows}
    data = loop.context(rows, catalog, recipe)
    flat = []
    def visit(nodes, parent=None):
        for n in nodes:
            # Include ancestors crossing the window without copying their outside text.
            if n.block_idx in ids or any(n.span[0] <= idx < n.span[1] for idx in ids):
                flat.append({'block': n.block_idx, 'parent_block': parent, 'family': n.family,
                             'level': n.level, 'ordinal': n.ordinal, 'surface': n.surface,
                             'title': n.title, 'page': n.page, 'span': list(n.span),
                             'context_only': n.block_idx not in ids})
                visit(n.children, n.block_idx)
    visit(result.tree)
    data['numbering_evidence'] = [{k:v for k,v in c.items() if k not in {'id','required_as_heading','excluded_as_reference'}} for c in loop.source_candidates(result, rows)]
    data.pop('candidate_decision_scope',None)
    data['actual_structure'] = {'ladder': result.ladder.dump(), 'nodes': flat,
                                'representation': 'window_nodes_with_global_ancestors'}
    data['page_window'] = pages
    data['scope'] = ('Review only supplied global pages and block IDs. Ancestors may start outside this window. '
                     'Do not renumber IDs, infer unseen content, or certify unseen pages. '
                     'Tables continuing beyond the window retain source blocks; flag ambiguous boundaries.')
    return data


def run(engine, blocks, pdf, baseline, catalog, anchors, call, journal, *, width,
        render, max_corrections=2, max_inductions=4, full_review=False):
    pages = inventory(pdf, blocks)
    journal.save('page-inventory.json', pages)
    if any('missing_text_or_ocr' in p['risks'] for p in pages):
        raise ValueError('source_blocks_missing_ocr_required')
    initial_risks = audit(blocks, baseline, pages, strict=False)
    initial_selection = select(pages, blocks, baseline, initial_risks)
    if full_review:
        for page in pages: initial_selection.setdefault(page["page"], []).append("full_review")
    plan = windows(initial_selection, len(pages), width)
    journal.save('page-plan.json', {'version': VERSION, 'selected': initial_selection, 'windows': plan})
    journal.event('recipe.sampling', total_pages=len(pages), selected_pages=len(initial_selection), full_review=full_review)
    # Empty source blocks cannot support declarative structure induction.
    if not blocks: raise ValueError('no_source_blocks_for_rule_generation')
    rules=[];recipe=None;result=baseline;corrections=replans=0;seen=set();seen_levels=set()

    evidence_cache = {}
    evidence_count = 0

    def invoke(phase, system, data, schema, vision=True):
        if vision and data.get("visual_evidence"):
            call.images = [evidence_cache[row["sha256"]] for row in data["visual_evidence"]["images"]]
        else:
            call.images = render(data["page_window"]) if vision else []
        return call(phase, system, data, schema, vision)

    recipe=recipe_regions.compose(engine,blocks,pdf,baseline,pages,catalog,invoke,journal)
    while True:
        loop.validate(recipe, catalog)
        fingerprint = loop.digest([loop.recipe_signature(recipe), rules])
        if fingerprint in seen: raise ValueError('recipe_cycle')
        seen.add(fingerprint)
        journal.event('recipe.rebuild', revision=len(seen), corrections=corrections)
        seen_levels.add(loop.recipe_signature(recipe))
        result = loop.build(engine, blocks, recipe, catalog, anchors, draft=True)
        risks = audit(blocks, result, pages, strict=False)
        selection = select(pages, blocks, result, risks)
        if full_review:
            for page in pages: selection.setdefault(page["page"], []).append("full_review")
        for region in recipe['regions']:
            for idx in {region['start_block'],region['end_block']-1,max(0,region['start_block']-1)}:
                p=blocks[idx].page
                selection[p]=sorted(set(selection.get(p,[]))|{'format_boundary'})
        # A repair may not remove an already scheduled review from the worklist.
        for p, reasons in initial_selection.items():
            selection[p] = sorted(set(selection.get(p, [])) | set(reasons))
        plan = windows(selection, len(pages), width)
        journal.save(f'window-tree-{len(seen)}.json', loop.tree_record(result))
        journal.save(f'template-compilation-{len(seen)}.json',{'recipe':recipe,'decisions':result.stats.get('template_compilation',[]),'issues':result.stats.get('template_issues',[])})
        journal.save(f'window-plan-{len(seen)}.json', {'risks': risks, 'selected': selection, 'windows': plan})
        reviewed = set(); changed = False
        for number, window in enumerate(plan):
            journal.event('recipe.review.start', revision=len(seen), window_number=number+1,
                          window_count=len(plan), pages=window, corrections=corrections)
            data = context(blocks, catalog, window, result, recipe)
            data['active_regions']=[r for r in recipe['regions'] if any(r['start_block']<=b.idx<r['end_block'] for b in blocks if b.page in window)]
            data['template_diagnostics'] = [x for x in result.stats.get('template_issues',[]) if blocks[x['block']].page in window]
            data['code_issues'] = {str(p):v for p,v in risks.items() if p in window}
            soft={'number_sequence_change','outside_structure','no_source_blocks','no_readable_blocks'}
            data['hard_code_issues']=[{'page':p,'errors':[v for v in values if v not in soft]} for p,values in risks.items() if p in window and any(v not in soft for v in values)]
            data['hard_code_issues'].extend(data['template_diagnostics'])
            evidence_count += 1
            from pathlib import Path
            # Hash the exact images into the context BEFORE request_review binds its state ID.
            images, evidence = recipe_evidence.review_images(pdf.name, blocks, result, window,
                Path(journal.directory) / f'viewer-evidence-{evidence_count}')
            evidence_cache.update({row['sha256']:uri for row,uri in zip(evidence['images'],images)})
            data['visual_evidence'] = evidence
            data['source_blocks'] = [{**{k:r[k] for k in ('idx','page','text')}, 'kind':r.get('kind','text')} for r in data['source_blocks']]
            response = recipe_regions.request_review(f'window-review-{len(seen)}-{number}', data, catalog, invoke,
                                           seen_levels=seen_levels, save=journal.save)
            loop.validate(response['recipe'], catalog)
            supplied = {r['idx'] for r in data['source_blocks']}
            for issue in response['issues']:
                if not set(issue['blocks']) <= supplied: raise ValueError('review_cites_unseen_block')
            verdict = response['verdict']
            journal.event('recipe.review.result', revision=len(seen), window_number=number+1,
                          window_count=len(plan), verdict=verdict, issue_count=len(response['issues']))
            if verdict == 'approve':
                if response['issues'] or response['recipe'] != recipe: raise ValueError('inconsistent_approval')
                reviewed.update(window); continue
            if verdict == 'source_error':
                journal.save('source-evidence-insufficient.json', response)
                raise ValueError('source_evidence_insufficient')
            if verdict == 'hold': raise ValueError('reviewer_hold')
            if verdict == 'resegment':
                if replans>=2 or corrections>=max_corrections:raise ValueError('Format boundary replan budget exhausted')
                replans+=1;corrections+=1
                recipe=recipe_regions.compose(engine,blocks,pdf,baseline,pages,catalog,invoke,journal,previous=recipe,issues=response['issues'])
            elif verdict == 'missing_rules':
                journal.save('unsupported-document-grammar.json',response)
                raise ValueError('document_grammar_extension_required')
            elif verdict == 'revise':
                if corrections >= max_corrections: raise ValueError('correction_budget_exhausted')
                corrections += 1; recipe = response['recipe']
            else: raise ValueError('invalid_review_verdict')
            # Any global rule edit invalidates every prior window approval.
            journal.event('recipe.correction', corrections=corrections, replans=replans,
                          change=verdict, approvals_invalidated=True)
            initial_selection = selection; changed = True; break
        if changed: continue
        loop.build(engine, blocks, recipe, catalog, anchors)
        audit(blocks, result, pages)
        coverage = {'version': VERSION, 'total_pages': len(pages),
                    'code_checked_pages': list(range(1, len(pages)+1)),
                    'visually_reviewed_pages': sorted(reviewed),
                    'not_visually_reviewed_pages': sorted(set(range(1,len(pages)+1))-reviewed),
                    'visual_scope': 'full' if len(reviewed)==len(pages) else 'sampled',
                    'selection_reasons': {str(p):v for p,v in selection.items()}, 'windows': plan,
                    'code_risks': {str(p):v for p,v in risks.items()}, 'source_blocks': len(blocks),
                    'table_boundary_policy': 'original blocks preserved; neighbours reviewed; no inferred cell merge'}
        journal.save('coverage.json', coverage)
        return result, recipe, rules, coverage
