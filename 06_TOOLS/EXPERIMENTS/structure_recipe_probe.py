#!/usr/bin/env python3
"""Offline ADR0348 recipe probe. Writes a fresh report; never calls a model."""
from __future__ import annotations
import argparse
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))
CANDIDATE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0348/recipes'


def load_candidate():
    manifest = json.loads((CANDIDATE / 'candidate.json').read_text())
    revision = next(r for r in manifest['revisions'] if r['revision_id'] == 'rev-002')
    if revision['revision_sha256'] != '4ca914587954301262a4dce72b17a42d860a8bd89cc59919ca23687b2c51b37d':
        raise ValueError('unexpected candidate revision')
    for row in revision['files']:
        path = ROOT / row['frozen_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['snapshot_sha256']:
            raise ValueError('frozen candidate drift')
    path = CANDIDATE / 'revisions/rev-002/snapshot/02_BACKEND/lawrag/core/structure_recipes.py'
    spec = importlib.util.spec_from_file_location('adr0348_recipes', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--document-name', required=True, help='Unique relative path used as JSON key')
    p.add_argument('--existing', action='append', default=[], help='Registered doc_type to test')
    p.add_argument('--tags', type=Path, help='Document-name JSON registry; stale hashes rejected')
    p.add_argument('--proposal', type=Path, help='Previously obtained model proposal JSON; no implicit API call')
    p.add_argument('--attachments', type=Path, help='Explicit attachment inventory JSON list; omit to withhold pass')
    p.add_argument('--vision-page', action='append', type=int, default=[], help='Original PDF page, maximum four')
    p.add_argument('--output', required=True, type=Path, help='New output directory, never overwrite')
    args = p.parse_args()
    from lawrag.core import router, parse_adapter
    opt = load_candidate()
    opt.document_key(args.document_name)
    if len(args.existing) > 8 or len(args.vision_page) > 4:
        p.error('maximum eight existing formats and four image pages')
    source = args.source.resolve(strict=True)
    if source.suffix.lower() in {'.xml', '.html', '.htm'}:
        p.error('native XML/HTML recipes not replaced; annex inventory adapter is still required')
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    tagged = opt.tag_record(json.loads(args.tags.read_text()), args.document_name, sha) if args.tags else None
    if tagged and tagged['tag'] not in args.existing:
        args.existing.insert(0, tagged['tag'])
    if len(args.existing) > 8:
        p.error('tag plus shortlist may contain at most eight formats')
    parsed = parse_adapter.parse(source)
    registry = router.load()
    routes = [registry.get(tag) for tag in args.existing]
    existing = []
    for route in routes:
        glossary, fmt = router.assets(route)
        existing.append((fmt, glossary))
    all_formats = [router.assets(route)[1] for route in registry.routes]
    catalog = opt.marker_catalog(all_formats)
    images = []
    if args.vision_page:
        if source.suffix.lower() != '.pdf':
            p.error('vision requires original PDF pages; synthetic HWP pages are not layout evidence')
        from lawrag.core.structure.viewer import page_png
        for page in args.vision_page:
            images.append(dict(page=page, source_sha256=sha, render_kind='original_page',
                               data_uri=page_png(source, page, scale=1.2)))
    packet = opt.request_packet(parsed, sha, catalog, images=images, supports_images=bool(images))
    proposal = json.loads(args.proposal.read_text()) if args.proposal else None
    attachments = json.loads(args.attachments.read_text()) if args.attachments else None
    result = opt.choose(parsed, sha, existing, catalog,
                        proposer=(lambda: proposal) if proposal is not None else None,
                        attachments=attachments)
    if hashlib.sha256(source.read_bytes()).hexdigest() != sha:
        raise ValueError('source changed during parsing')
    report = dict(document=args.document_name, source_sha256=sha, llm_calls=0,
                  main_changed=False, parser=parsed.parser, parser_warnings=parsed.warnings, result=result)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in [('request.json', packet), ('report.json', report)]:
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    if result.get('recipe'):
        (args.output / 'recipe.candidate.json').write_text(json.dumps(result['recipe'], ensure_ascii=False, indent=2)+'\n')
    tags = dict(schema_version='document-recipe-tags-v1', documents={})
    if result.get('recipe'):
        tags = opt.propose_tag(tags, args.document_name, sha, result['recipe'], result['selected'])
    elif result['status'] == 'existing_candidate':
        selected = result['selected']
        tags['documents'][args.document_name] = dict(display_name=source.name,
            source_sha256=sha, tag=selected['document']['doc_type'],
            recipe_version=selected['document']['format_version'],
            format_sha256=selected['format_sha256'], status='candidate',
            evaluation_sha256=opt.digest(selected))
    (args.output / 'tags.candidate.json').write_text(json.dumps(tags, ensure_ascii=False, indent=2)+'\n')
    (args.output / 'report.html').write_text('<meta charset="utf-8"><h1>구조화 후보 검토 — 운영 미반영</h1><pre>'
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + '</pre>')
    print(json.dumps({'output':str(args.output), 'status':result['status'], 'llm_calls':0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
