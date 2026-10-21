"""Explicit onsite DRAFT builder: document structure and term navigation.

This is an offline command, not a MAIN promotion or an automatic API data importer.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import uuid
from xml.etree import ElementTree

from .genos_unified import ROOT, _build_source_store
from .genos_e2e import paths
from semantic_runtime.contracts import digest, sha
from semantic_runtime.document_roles import role_of_row
from semantic_runtime.genos_backend import Genos, safe, error_detail

EXTENSIONS = {'.xml', '.html', '.htm', '.pdf', '.hwp', '.hwpx', '.docx', '.doc'}


from .document_representations import (metadata as document_metadata, select as select_representations,
                                      PRIORITY as REPRESENTATION_PRIORITY, POLICY as REPRESENTATION_POLICY)


def route_summary(row):
    """Describe only the explicitly selected route; never infer a document tag."""
    if row.get('source_parser'):
        return '외규 전용 파서: ' + str(row['source_parser'])
    suffix = Path(row.get('path') or row['relative']).suffix.lower()
    if suffix == '.pdf' and os.environ.get('GENOS_PDF_PARSER', 'preprocessor').strip() == 'preprocessor':
        return 'GENOS 전처리기 Docling JSON → ' + ('등록 형식: ' + row['doc_type'] if row.get('doc_type') else '원문 구조화·용어 적재')
    if row.get('doc_type'):
        from lawrag.core import router
        selected = router.load().get(row['doc_type'])
        return f'등록 형식: {row["doc_type"]} / 파서: {selected.parser}'
    if suffix == '.xml':
        return 'XML 원문 태그 구조화'
    if suffix in {'.html', '.htm'}:
        return '조문 HTML 전용 구조화'
    if row.get('engine') == 'docxstyle':
        return '명시적 DOCX 제목 스타일 구조화'
    return f'{suffix or "파일"} 파서 + 기본 구조 유도 (등록 형식 태그 없음)'


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)


@contextmanager
def isolated(root):
    previous = os.environ.get('STRUCTURE_LEDGER')
    os.environ['STRUCTURE_LEDGER'] = str(root / 'structure_ledger.json')
    try:
        with paths(root):
            yield
    finally:
        if previous is None:
            os.environ.pop('STRUCTURE_LEDGER', None)
        else:
            os.environ['STRUCTURE_LEDGER'] = previous




def inventory(input_root, source, bindings=None, *, selected=None, allow_duplicates=False):
    """Only explicit file tags / registered bindings, never inferred legal types."""
    from lawrag.core import router
    router.load.cache_clear()
    root = Path(input_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('--input-root must be a mounted source directory')
    mapping = json.loads(Path(bindings).read_text()) if bindings else {'docs': {}, 'folders': {}}
    if not isinstance(mapping, dict) or set(mapping) - {'docs', 'folders'}:
        raise ValueError('bindings must contain docs/folders mappings')
    if any(not isinstance(mapping.get(k, {}), dict) for k in ('docs', 'folders')):
        raise ValueError('bindings docs/folders must be objects')
    files, ignored, seen, assets = [], [], {}, {}
    for path in sorted(root.rglob('*') if selected is None else selected):
        rel = path.relative_to(root)
        if any(p.startswith('.') for p in rel.parts):
            continue
        if path.is_symlink():
            raise ValueError('source symlinks are not followed: ' + str(path))
        if not path.is_file():
            continue
        if path.name=='manifest.json':
            continue  # Optional collection metadata, never an input contract.
        sidecar = path.with_name(path.name + '.genos.json')
        if sidecar.is_symlink():
            raise ValueError('source tag symlinks are not followed: ' + str(sidecar))
        if path.suffix.lower() not in EXTENSIONS and not sidecar.exists():
            if not path.name.endswith('.genos.json'):
                ignored.append(str(rel))
            continue
        tags = json.loads(sidecar.read_text()) if sidecar.exists() else {}
        if not isinstance(tags, dict) or set(tags) - {'doc_type', 'engine', 'name', 'folder'}:
            raise ValueError('unknown document tag: ' + str(sidecar))
        if any(not isinstance(v, str) or not v.strip() for v in tags.values()):
            raise ValueError('document tags must be nonempty strings: ' + str(sidecar))
        fingerprint = sha(path)
        folder = tags.get('folder', rel.parent.as_posix() if rel.parent != Path('.') else ('내규' if source == 'internal' else '외규'))
        doc_type = tags.get('doc_type') or mapping.get('docs', {}).get(fingerprint[:16]) or mapping.get('folders', {}).get(folder)
        engine = tags.get('engine', '')
        if path.suffix.lower() not in EXTENSIONS and not doc_type:
            raise ValueError('this file format requires a registered doc_type tag: ' + str(path))
        if engine not in {'', 'induce', 'docxstyle'}:
            raise ValueError('engine must be induce or docxstyle: ' + str(path))
        if engine == 'docxstyle' and path.suffix.lower() not in {'.docx', '.doc'}:
            raise ValueError('docxstyle requires DOCX: ' + str(path))
        if doc_type and engine:
            raise ValueError('choose a registered doc_type OR an engine, not both: ' + str(path))
        if path.suffix.lower() in {'.xml', '.html', '.htm'} and (doc_type or engine):
            raise ValueError('XML/HTML uses its registered tag parser; format overrides are not supported: ' + str(path))
        if doc_type:
            route = router.load().get(doc_type)
            router.assets(route)  # Validate all tags before the first model request.
            for asset in (router.DEFAULT_REGISTRY, route.format_path(), route.glossary_path()):
                if asset:
                    assets[str(asset.relative_to(ROOT))] = sha(asset)
        title = tags.get('name');abbreviation = None
        if path.suffix.lower() == '.xml':
            try:
                law = ElementTree.fromstring(path.read_bytes())
                # law.go.kr 법령명약칭 (자본시장법) names the same document; only with the XML's own title.
                official = (law.findtext('.//법령명_한글') or '').strip()
                abbreviation = (law.findtext('.//법령명약칭') or '').strip() if official else None
                title = title or official
            except ElementTree.ParseError:
                pass  # The registered ingest parser will report the malformed source.
        row = {'path': str(path), 'relative': str(rel), 'sha256': fingerprint,
               'document_id': fingerprint[:16], 'source': source, 'folder': folder,
               'name': title.strip() if title and title.strip() else path.stem, 'doc_type': doc_type, 'engine': engine,
               'sidecar_sha256': sha(sidecar) if sidecar.exists() else None,
               **({'official_abbreviation': abbreviation} if abbreviation else {})}
        if row['document_id'] in seen and not allow_duplicates:
            raise ValueError('duplicate content/document ID: ' + seen[row['document_id']] + ' / ' + str(path))
        seen[row['document_id']] = str(path)
        files.append(row)
    if not files:
        raise ValueError('no supported documents in ' + str(root))
    files,alternatives=select_representations(files)
    return {'input_root': str(root), 'files': files, 'ignored': ignored, 'representation_exclusions':alternatives,'format_assets': assets,
            'bindings_sha256': sha(bindings) if bindings else None}


def registered_ingest(raw, filename, row, build):
    """Honor BOTH the parser and the format named by the existing registry."""
    from lawrag.core import rawstore, router
    from lawrag.core.structure import from_format, viewer
    registered = rawstore.ensure(raw, filename, name=row['name'], folder=row['folder'],
                                 kind=row.get('kind') or ('internal' if row['source'] == 'internal' else 'law'),
                                 via='genos-build', corpus=build / 'corpus')
    # On an interrupted run rawstore may have already committed the source registration.
    if registered['path']:
        copied = Path(registered['path'])
    else:
        from lawrag.core import batch
        copied = next(Path(t['path']) for t in batch.ingest_targets() if t['doc_id'] == row['document_id'])
    if sha(copied) != row['sha256']:
        raise ValueError('registered raw copy hash mismatch')
    # Offline DRAFT admission is mechanical; fitness is retained as advisory data.
    # route() still enforces registered assets and parser/type validity.
    routed = router.route(copied, row['doc_type'])
    result, blocks = from_format.result_from_document(routed.parsed, routed.doc, routed.fitness, doc_type=row['doc_type'])
    review = None
    parser_evidence = None
    if routed.parsed.stats.get('requires_structure_vlm'):
        from lawrag.core.structure import pipeline, recipe_runtime
        from lawrag.core.structure.model import Block
        if copied.suffix.lower() != '.pdf' or not recipe_runtime.enabled():
            raise recipe_runtime.NeedsReview('Chunk input requires original PDF and STRUCTURE_RECIPE_VLM=on')
        parser_evidence = {key:routed.parsed.stats[key] for key in
                           ('source_format','chunk_assembly','spatial_fidelity','table_fidelity')}
        blocks = Block.from_elements(routed.parsed.elements)
        result, review = recipe_runtime.revise_pdf(pipeline, blocks, copied,
            store=build/'structure', document=row['document_id'], source_evidence=parser_evidence)
    data = viewer.payload(result, blocks, pdf_path=copied if copied.suffix.lower() == '.pdf' else None,
                          elements=routed.parsed.elements, images=routed.parsed.images)
    data.update(doc=row['name'], bound_doc_type=row['doc_type'], format_version=routed.fmt.format_version,
                parser=routed.parsed.parser, parser_warnings=routed.parsed.warnings)
    if routed.parsed.stats.get('preprocessor'):
        data.update(preprocessor=routed.parsed.stats['preprocessor'],
                    parser_identity=routed.parsed.stats['parser_identity'])
    if review:
        data.update(recipe_review=review, parser_evidence=parser_evidence,
                    bound_format_scope='reference only; chunk input rebuilt by reviewed recipe')
    folder = build / 'structure' / row['document_id']
    meta = {'doc_id': row['document_id'], 'name': row['name'], 'folder': row['folder'],
            'kind': row.get('kind') or ('internal' if row['source'] == 'internal' else 'law'),
            'passed': routed.fitness.passed, 'score': routed.fitness.score,
            'source_kind': copied.suffix.lower().lstrip('.'),
            'structured_by': f'format:{row["doc_type"]}@v{routed.fmt.format_version}', 'used_llm': False}
    if review:
        meta.update(recipe_review=review, used_llm=bool(review['model_calls']),
                    structured_by='recipe-vlm:'+review['tag'], passed=result.fitness_passed,
                    score=result.fitness_score)
    atomic(folder / 'result.json', data)
    atomic(folder / 'meta.json', meta)
    return {'doc_id': row['document_id'], 'meta': meta}


def ingest_files(plan, build, emit):
    errors = []
    for number, row in enumerate(plan['files'], 1):
        emit(f'[1/5] 문서 {number}/{len(plan["files"])}: {row["relative"]}')
        try:
            _ingest_files({**plan, 'files': [row]}, build, emit)
        except Exception as exc:
            import traceback
            error = safe({'document_id': row['document_id'], 'path': row['path'],
                          'error': error_detail(exc), 'type': type(exc).__name__, 'traceback': traceback.format_exc()})
            if getattr(exc, 'diagnostic', None):
                error['diagnostic'] = safe(exc.diagnostic)
            errors.append(error)
            emit('[STRUCTURE ERROR] ' + json.dumps(error, ensure_ascii=False))
    atomic(build / 'structure-errors.json', errors)
    if errors:
        reasons = ' / '.join(e['error'] for e in errors[:3])
        raise ValueError(f'{reasons}; {len(errors)} document(s) failed structure; 오류 요약: {build / "structure-errors.json"}')


def _ingest_files(plan, build, emit):
    from lawrag.core.ingest import ingest
    from lawrag.core.internal_rules import PROFILE
    state = build / 'ingest'
    state.mkdir(exist_ok=True)
    for n, row in enumerate(plan['files'], 1):
        ident = row['document_id']
        marker = state / (ident + '.json')
        result = build / 'structure' / ident / 'result.json'
        meta = result.with_name('meta.json')
        emit(f'[1/5] 구조화 {n}/{len(plan["files"])}: {row["relative"]} → {row["doc_type"] or row["engine"] or "형식별 기본 엔진"}')
        if marker.exists():
            saved = json.loads(marker.read_text())
            if saved != {'result_sha256': sha(result), 'meta_sha256': sha(meta)}:
                raise ValueError('completed structure changed: ' + ident)
            emit('  완료 결과 재사용 (LLM 호출 없음)')
            continue
        original = Path(row['path'])
        raw = original.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('source changed after inventory: ' + str(original))
        filename = original.stem + '.html' if original.suffix.lower() == '.htm' else original.name
        if row.get('source_parser'):
            from .genos_corpus import ingest_case
            response = ingest_case(raw, filename, row, build)
        elif row.get('external_source') in {'krx', 'kofia'} and original.suffix.lower() in {'.html', '.htm'}:
            from lawrag.core import rawstore
            from lawrag.core.ingest import ingest_rulehtml_bytes, manifest_item_for
            rawstore.ensure(raw, filename, name=row['name'], folder=row['folder'], kind=row['kind'],
                            via='genos-all-corpus', corpus=build / 'corpus')
            # 별표·서식은 조문 HTML 에 없다. 수집 manifest 가 가리키는 첨부의 변환
            # 사이드카를 같은 문서에 실어야 조문이 부르는 별표가 원문으로 남는다.
            item, manifest = manifest_item_for(original, raw, collection_root=plan.get('input_root'))
            response = ingest_rulehtml_bytes(raw, row['name'], build / 'structure', row['folder'],
                                            extra_meta={'kind': row['kind']}, site=row['external_source'],
                                            manifest_item=item, manifest=manifest)
            emit(f'  별표·서식 {response.get("annex_md", 0)}/{response.get("annex_have", 0)}건 적재')
        else:
            from lawrag.core.ingest import manifest_item_for
            item, manifest = manifest_item_for(original, raw, collection_root=plan.get('input_root'))
            response = registered_ingest(raw, filename, row, build) if row['doc_type'] else ingest(
                          raw, filename, store=build / 'structure', name=row['name'], folder=row['folder'],
                          use_llm=False, engine=row['engine'],
                          hints=PROFILE if row['source'] == 'internal' else None,
                          binding_of=lambda _id, _folder, tag=row['doc_type']: tag,
                          extra_meta={'kind': row.get('kind') or ('internal' if row['source'] == 'internal' else 'law')},
                          manifest_item=item or {}, manifest=manifest, raw_via='genos-build')
        if response['doc_id'] != ident:
            raise ValueError(f'문서 ID 불일치: 예상 {ident}, 결과 {response["doc_id"]}')
        context = document_metadata(row)
        for key in ('external_source', 'kind', 'raw_role', 'aliases', 'source_metadata', 'conversion', 'input_collection',
                    'representations', 'pdf_references', 'representation_policy', 'pairing_basis',
                    'pairing_content_verified', 'source_title', 'filename_version', 'is_latest'):
            if key in row:
                context[key] = row[key]
        context['document_role'] = row.get('document_role') or role_of_row(row)
        data = json.loads(result.read_text())
        metadata = json.loads(meta.read_text())
        from .genos_admission import validate_structure, preserve_unowned_source
        data = preserve_unowned_source(data)
        admission = validate_structure(ident, metadata, data)
        metadata['structure_admission'] = admission
        for warning in admission['warnings']:
            emit('[STRUCTURE WARNING] '+warning)
        if not metadata.get('passed', False):
            emit('[STRUCTURE WARNING] 구조 점수는 참고용입니다. 점수로 제외하지 않음: '
                 + str(metadata.get('score')))
        # Stored alongside the structure, not spliced into evidence blocks/offsets.
        # Companion PDFs are reference artifacts, never substituted for native
        # parsing coordinates. Their hashes are bound in the structure receipt.
        references = []
        for rep in row.get('pdf_references', []):
            src = Path(rep['path'])
            if sha(src) != rep['sha256']: raise ValueError('reference PDF changed')
            dest = result.parent / 'reference-pdfs' / (rep['sha256'] + '.pdf')
            dest.parent.mkdir(exist_ok=True)
            if not dest.exists(): shutil.copyfile(src, dest)
            if sha(dest) != rep['sha256']: raise ValueError('reference PDF copy mismatch')
            references.append({**rep, 'stored_path': str(dest.relative_to(result.parent)),
                               'coordinate_alignment': 'unverified', 'purpose': 'visual_reference'})
        context['pdf_references'] = references
        data.update(document_metadata=context, doc=context['display_name'])
        metadata.update(document_metadata=context, name=context['display_name'])
        atomic(result, data)
        atomic(meta, metadata)
        atomic(marker, {'result_sha256': sha(result), 'meta_sha256': sha(meta)})


def source_jobs(build, plan):
    """Persist structured original text without creating semantic extraction jobs."""
    target=build/'source.sqlite';marker=build/'source.json'
    if marker.exists():
        receipt=json.loads(marker.read_text())
        if sha(target)!=receipt['sha256']:raise ValueError('source store changed')
        return target,receipt
    source,receipt=_build_source_store(build,allow_score_advisory=True)
    if set(receipt['document_ids'])!={r['document_id'] for r in plan['files']}:
        raise ValueError('some input documents did not reach the source store')
    shutil.copyfile(source,target)
    receipt={**receipt,'sha256':sha(target),'source_set_sha256':receipt['source_fingerprint']}
    atomic(marker,receipt)
    return target,receipt


def embeddings(build, source, provider, batch_size, chunk_chars, emit):
    """SQLite batch commits allow resume without repeating completed embeddings."""
    from semantic_runtime.genos_index import FORMAT
    index = build / 'vectors.sqlite'
    identity = {'format': FORMAT, 'source_store_sha256': sha(source), 'model': provider.models['embed'],
                'endpoint': provider.targets['embed'].root, 'chunk_chars': chunk_chars,
                'input_recipe': 'document-folder-title-alias-v2'}
    with sqlite3.connect(index) as out, sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        out.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);'
                          'CREATE TABLE IF NOT EXISTS chunk(id INTEGER PRIMARY KEY,document_id TEXT,block_id TEXT,start INTEGER,end INTEGER,text TEXT,text_sha256 TEXT,vector TEXT,receipt TEXT);')
        previous = out.execute('SELECT value FROM meta WHERE key="identity"').fetchone()
        if previous:
            if json.loads(previous[0]) != identity:
                raise ValueError('embedding model/source identity changed')
        else:
            out.execute('INSERT INTO meta VALUES (?,?)', ('identity', json.dumps(identity)))
            for did, bid, text in src.execute('SELECT document_id,block_id,text FROM source_block ORDER BY document_id,CAST(block_id AS INTEGER)'):
                if not text.strip():
                    continue
                for start in range(0, len(text), chunk_chars):
                    end = min(start + chunk_chars, len(text))
                    out.execute('INSERT INTO chunk(document_id,block_id,start,end,text,text_sha256) VALUES (?,?,?,?,?,?)',
                                (did, bid, start, end, text[start:end], hashlib.sha256(text.encode()).hexdigest()))
            out.commit()
        total = out.execute('SELECT count(*) FROM chunk').fetchone()[0]
        if not total:
            raise ValueError('no embedding input chunks')
        dim_row = out.execute('SELECT value FROM meta WHERE key="dimensions"').fetchone()
        dimension = int(dim_row[0]) if dim_row else None
        while True:
            batch = out.execute('SELECT id,text,document_id FROM chunk WHERE vector IS NULL ORDER BY id LIMIT ?', (batch_size,)).fetchall()
            if not batch:
                break
            done = out.execute('SELECT count(*) FROM chunk WHERE vector IS NOT NULL').fetchone()[0]
            emit(f'[3/5] 임베딩 {done+1}~{done+len(batch)}/{total} (요청당 최대 {batch_size})')
            texts = []
            for _, text, did in batch:
                doc = src.execute('SELECT name,json FROM document WHERE document_id=?', (did,)).fetchone()
                if not doc:
                    raise ValueError('embedding source document missing: ' + did)
                aliases = json.loads(doc[1]).get('document_metadata', {}).get('aliases', [])
                names = '\n'.join(dict.fromkeys([doc[0], *[a['display_name'] for a in aliases]]))
                texts.append('문서 경로/제목: ' + names + '\n본문:\n' + text)
            vectors, receipt = provider.embed(texts, 'schema-build-embedding')
            if len(vectors) != len(batch):
                raise ValueError('embedding batch count mismatch')
            for (ident, _, _), vector in zip(batch, vectors):
                from semantic_runtime.genos_backend import unit_vector
                vector = unit_vector(vector)
                dimension = dimension or len(vector)
                if len(vector) != dimension:
                    raise ValueError('embedding dimensions changed')
                out.execute('UPDATE chunk SET vector=?,receipt=? WHERE id=?',
                            (json.dumps(vector), json.dumps(receipt), ident))
            out.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('dimensions', str(dimension)))
            out.commit()
        if out.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('vector SQLite integrity error')
    descriptor = {**identity, 'path': index.name, 'sha256': sha(index), 'rows': total, 'dimensions': dimension}
    atomic(build / 'vectors.json', descriptor)
    return descriptor


def execute(args, *, provider_factory=Genos, emit=print, prepared_plan=None):
    """Use the maintained source/term stages for every new document build."""
    from . import genos_stages
    from .genos_progress import Progress
    plan=prepared_plan if prepared_plan is not None else inventory(args.input_root,args.source,args.bindings)
    if args.external_root:
        extra=inventory(args.external_root,'external',args.bindings)
        if {r['document_id'] for r in plan['files']} & {r['document_id'] for r in extra['files']}:
            raise ValueError('ambiguous duplicate document authority')
        plan['files']+=extra['files']
    if not args.execute:return {'status':'INPUT_CHECK_ONLY','selected':len(plan['files'])}
    data=Path(args.build_dir).resolve();logs=data/'LOGS';logs.mkdir(parents=True,exist_ok=True)
    progress=Progress(logs,sys.stdout)
    try:return genos_stages.execute(plan,args,data,'build','all',provider_factory=provider_factory,progress=progress)
    finally:progress.close()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', help='defaults to code-root/data; default input is corpus/internal')
    p.add_argument('--json', action='store_true')
    p.add_argument('command', choices=['build'])
    p.add_argument('--input-root', default=os.environ.get('GENOS_INPUT_ROOT') or os.environ.get('GENOS_UPLOAD_ROOT'))
    p.add_argument('--source', choices=['internal', 'external'], default='internal')
    p.add_argument('--external-root', help='optional external raw directory, processed through the SAME pipeline into this generation')
    p.add_argument('--bindings', default=os.environ.get('FORMAT_BINDINGS_FILE'))
    p.add_argument('--build-dir', required=True)
    p.add_argument('--glossary-dir',type=Path,help='versioned glossary for term and definition indexing')
    p.add_argument('--timeout', type=int, default=1800)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--execute', action='store_true', help='explicit authorization to call configured onsite models')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.timeout < 1:
            raise ValueError('all size/time/call limits must be positive')
        execute(args)
        return 0
    except ModuleNotFoundError as exc:
        print(safe(f'BUILD STOPPED: 파서/런타임 패키지 {exc.name} 없음. GENOS에서 기존 requirements-pipeline.txt를 설치한 Python으로 실행하세요. '
                   '외부 다운로드가 막혀 있으면 사내 패키지 미러/승인된 오프라인 wheel을 사용하세요. 구조화 미완료 문서는 적재하지 않았습니다.'), file=sys.stderr)
        return 1
    except Exception as exc:
        print('BUILD STOPPED: ' + error_detail(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
