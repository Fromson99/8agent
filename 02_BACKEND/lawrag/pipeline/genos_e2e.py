"""One raw document through common ingest and the registered legal-rag pipeline.

Explicit operational GENOS adapter, never a change to default/MAIN selection.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

from .genos_unified import ROOT, _build_source_store
from semantic_runtime.contracts import sha, write
from semantic_runtime.genos_backend import Genos, FileVectors, safe
from semantic_runtime.pipeline import Pipeline
from semantic_runtime.provider import obj, array, STR
from semantic_runtime.storage import Store, publish


@contextmanager
def paths(root):
    """Override, not setdefault: no inherited path may write to production data."""
    mappings = {'GENOS_DATA_ROOT': root, 'STRUCTURE_STORE': root / 'structure',
                'CORPUS_DIR': root / 'corpus', 'PIPELINE_DIR': root / 'pipeline',
                'PIPELINE_INBOX': root / 'inbox', 'GLOSSARY_STORE': root / 'glossary.json',
                'RAG_VECTOR_STORE': root / 'vectors', 'RAG_LOG_DIR': root / 'rag',
                'RAG_RULES_DIR': root / 'rules', 'OPS_DIR': root / 'ops'}
    previous = {k: os.environ.get(k) for k in mappings}
    os.environ.update({k: str(v) for k, v in mappings.items()})
    try:
        yield
    finally:
        for k, value in previous.items():
            if value is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = value


def choose_document(data_root, document, source):
    from lawrag.core import batch
    with paths(data_root):
        targets = batch.ingest_targets()
    if document == 'auto':
        candidates = [t for t in targets if t['via'] == 'law'
                      and Path(t['path']).suffix.lower() == '.xml'
                      and 1000 <= Path(t['path']).stat().st_size <= 100000]
        if source == 'internal' or not candidates:
            raise ValueError('자동 선택할 등록 법령 XML이 없습니다. --document /실제/문서경로 --source internal 또는 external을 지정하세요.')
        return min(candidates, key=lambda t: (Path(t['path']).stat().st_size, t['path']))
    path = Path(document).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in batch.INBOX_EXTS:
        raise ValueError('지원 원문 형식: XML/HTML/HTM/PDF/HWP/HWPX/DOCX')
    matched = [t for t in targets if Path(t['path']).resolve() == path]
    if matched and source == 'auto':
        return matched[0]
    if source == 'auto':
        raise ValueError('미등록 파일은 --source internal 또는 external로 출처를 지정하세요.')
    via = 'law' if source == 'external' and path.suffix.lower() == '.xml' else 'file'
    return {'path': str(path), 'name': path.stem, 'via': via,
            'source': 'law' if via == 'law' else 'uploads',
            'folder': '내규' if source == 'internal' else '외부문서',
            'kind': 'internal' if source == 'internal' else None,
            'item': {'name': path.stem, 'kind': 'internal' if source == 'internal' else None}}


def stage_document(target, run):
    """Copy one file; never move the user's upload or inherit old LLM artifacts."""
    original = Path(target['path'])
    if original.stat().st_size > 50 * 1024 * 1024:
        raise ValueError('one-document test raw limit is 50 MiB')
    raw_dir = run / 'raw'
    raw_dir.mkdir()
    copied = raw_dir / ('document' + original.suffix.lower())
    original_sha = sha(original)
    shutil.copyfile(original, copied)
    if sha(copied) != original_sha:
        raise ValueError('source changed during copy')
    t = dict(target)
    source = t.get('source') or 'uploads'
    if source not in {'law', 'krx', 'kofia'}:
        source = 'uploads'
    # A staged upload must not be moved to _done by the batch adapter.
    t.update(path=str(copied), source=source, doc_id=original_sha[:16])
    if t['via'] == 'inbox':
        t['via'] = 'file'
    item = dict(t.get('item') or {})
    item.update(body_file=str(copied), body_html_file=str(copied), name=t['name'],
                folder=t['folder'], status='ok', body_sha256=original_sha, doc_id=original_sha[:16])
    # This run covers the chosen body only, not extra linked/attached documents.
    item['attachments'] = []
    t['item'] = item
    write(run / 'corpus' / source / 'manifest.json', {'items': [item]})
    return t, {'path': str(original), 'sha256': original_sha,
               'copy': str(copied), 'document_id': t['doc_id'], 'name': t['name'],
               'coverage': 'one body file; linked documents/annex attachments excluded'}


def chunks_from_store(store, chunk_chars, max_chunks):
    chunks = []
    for source in store.db.execute('SELECT * FROM source_block ORDER BY document_id,CAST(block_id AS INTEGER)'):
        text = source['text']
        if not text.strip():
            continue
        for start in range(0, len(text), chunk_chars):
            end = min(start + chunk_chars, len(text))
            chunks.append({'id': f'K{len(chunks)+1}', 'document_id': source['document_id'],
                           'block_id': source['block_id'], 'start': start, 'end': end,
                           'text': text[start:end], 'text_sha256': hashlib.sha256(text.encode()).hexdigest()})
    if not chunks:
        raise ValueError('문서에서 비어 있지 않은 청크를 만들지 못했습니다.')
    if len(chunks) > max_chunks:
        raise ValueError(f'청크 {len(chunks)}개 > --max-chunks {max_chunks}; 더 작은 문서를 선택하거나 명시적으로 한도를 올리세요. 부분 실행하지 않습니다.')
    return chunks


def review_and_embed(chunks, provider, store, run, batch_size, emit):
    indexed = []
    dim = None
    for start in range(0, len(chunks), batch_size):
        group = chunks[start:start+batch_size]
        emit(f'[3/6] LLM 핵심 원문 구절 추출 {start+1}~{start+len(group)}/{len(chunks)}')
        schema = obj({'chunks': array(obj({'id': {'type': 'string', 'enum': [c['id'] for c in group]}, 'quote': STR}))})
        result, receipt = provider.call('chunk-review',
            '각 청크에서 검색 시 중요한 원문 구절 한 개를 그대로 복사하세요. 모든 청크 ID를 정확히 한 번씩 반환하세요. '
            '요약/새 문장/생략부호를 만들지 마세요. 이는 미검증 검색 보조 자료이며 법적 승인이나 온톨로지 생성이 아닙니다.',
            {'chunks': [{'id': c['id'], 'text': c['text']} for c in group]}, schema)
        quotes = {x['id']: x['quote'] for x in result['chunks']}
        if len(quotes) != len(result['chunks']) or set(quotes) != {c['id'] for c in group}:
            raise ValueError('LLM chunk-review missing/duplicate chunk IDs')
        for c in group:
            quote = quotes[c['id']]
            if not quote.strip() or quote not in c['text']:
                raise ValueError(f'LLM 구절이 원문과 불일치: {c["id"]}')
        write(run / 'reviews' / f'{start:05d}.json',
              {'status': 'DRAFT', 'result': result, 'provider_receipt': receipt})
        emit(f'[4/6] 임베딩 생성 {start+1}~{start+len(group)}/{len(chunks)}')
        texts = [c['text'] + '\n핵심 원문 구절: ' + quotes[c['id']] for c in group]
        vectors, _ = provider.embed(texts, 'document-embedding')
        for chunk, text, vector in zip(group, texts, vectors):
            if dim is None:
                dim = len(vector)
            if len(vector) != dim:
                raise ValueError('embedding dimensions changed between batches')
            indexed.append({**chunk, 'embedding_input': text, 'vector': vector})
        emit(f'완료: 누적 {len(indexed)}개, 벡터 {dim}차원')
    path = run / 'vectors.json'
    write(path, {'format': 'genos-file-vectors-v1', 'model': provider.models['embed'],
                 'endpoint': provider.targets['embed'].root, 'dimensions': dim,
                 'source_store_sha256': store.manifest['source_store_sha256'], 'rows': indexed})
    return FileVectors(store, provider, path, sha(path))


class TracedPipeline(Pipeline):
    """Instrument existing engine methods without replacing their algorithms."""
    def __init__(self, *args, output, emit, **kwargs):
        super().__init__(*args, **kwargs)
        self.output, self.emit = output, emit

    def retrieve(self, *args, **kwargs):
        self.emit('[5/6] 질문 임베딩 → 파일 벡터 검색 + 기존 검색 통합')
        value = super().retrieve(*args, **kwargs)
        write(self.output / 'retrieval.json', value)
        self.emit(f'검색: {len(value["candidates"])}개, 경로별 {value["routes"]}')
        if not value['candidates'] or not value['routes'].get('vector'):
            raise ValueError('필수 벡터 검색 결과가 비었습니다.')
        return value

    def select(self, *args, **kwargs):
        self.emit('[5/6] 기존 LLM 근거 선택')
        value = super().select(*args, **kwargs)
        # The base implementation historically labels every provider "haiku".
        if value['provider_receipt']:
            value['method'] = 'genos'
        write(self.output / 'selection.json', value)
        if not value['selected']:
            raise ValueError('질문에 관련된 근거를 선택하지 못했습니다. 질문을 문서 내용에 맞춰 바꾸세요.')
        return value

    def assemble(self, *args, **kwargs):
        value = super().assemble(*args, **kwargs)
        write(self.output / 'assembled.json', value)
        self.emit(f'원문 근거 조립: {len(value["context"])}개')
        return value

    def answer(self, *args, **kwargs):
        self.emit('[6/6] 기존 답변 계약으로 LLM 호출 → 원문 인용 검사')
        value = super().answer(*args, **kwargs)
        write(self.output / 'answer.json', value)
        return value


def validate_rag_bindings():
    config = json.loads((ROOT / '00_SYSTEM/PIPELINE.json').read_text())
    for step in config['profiles']['legal-rag']['nodes']:
        entry = config['engines'][step['engine']]
        path = ROOT / entry['manifest']
        if sha(path) != entry['sha256']:
            raise ValueError(f'engine manifest hash mismatch: {path}')
        for file, expected in json.loads(path.read_text())['files'].items():
            if sha(ROOT / file) != expected:
                raise ValueError(f'engine code hash mismatch: {file}; 패치 ZIP 전체 적용이 필요합니다.')


def run(args):
    from lawrag.core.llm import load_env
    load_env()
    roots = [Path(args.data_root)] if args.data_root else [
        ROOT / 'GENOS_DATA', ROOT / '01_DATA/INBOX/AUTHORING']
    data_root = next((p.resolve() for p in roots if (p / 'corpus').is_dir() or (p / 'inbox').is_dir()), roots[0].resolve())
    target = choose_document(data_root, args.document, args.source)
    if not args.execute:
        print(json.dumps({'execute': False, 'document': target['path'], 'name': target['name'],
                          'next': '실제 GENOS 모델 호출은 --execute를 붙이세요.'}, ensure_ascii=False, indent=2))
        return 0
    validate_rag_bindings()  # Fail before any inference, not after paid embedding.
    base = Path(args.run_root or os.environ.get('GENOS_RUNTIME_DIR') or ROOT / 'runtime') / 'e2e'
    base.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='one-doc-', dir=base.resolve()))
    os.chmod(output, 0o700)
    log = output / 'run.log'
    started = time.monotonic()

    def emit(message):
        line = safe(f'[{time.monotonic()-started:7.1f}s] {message}')
        print(line, flush=True)
        with log.open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')

    emit(f'출력 폴더: {output}; 기존 데이터·CURRENT·Git·환경설정 변경 없음')
    try:
        with paths(output):
            emit(f'[1/6] 원문 한 개 복사: {target["name"]}')
            staged, source = stage_document(target, output)
            write(output / 'input.json', {'source': source, 'question': args.question,
                                          'parameters': vars(args), 'status': 'DRAFT'})
            emit('[2/6] 기존 공통 ingest → 구조화 원문 블록')
            from lawrag.core import batch
            batch._ingest_one(staged)
            source_store, receipt = _build_source_store(output)
            if receipt['documents'] != 1 or receipt['document_ids'] != [source['document_id']]:
                raise ValueError('one-document/source provenance invariant failed')
            scope = {'source_set_sha256': receipt['source_fingerprint'],
                     'authority_generation': 'genos-one-doc-' + source['sha256'][:16],
                     'document_version_ids': receipt['document_ids'], 'jurisdiction': 'KR', 'as_of': None}
            publish(ROOT, source_store, [], output / 'generation', scope=scope, export_allowed=False)
            store = Store(output / 'generation')
            try:
                chunks = chunks_from_store(store, args.chunk_chars, args.max_chunks)
                write(output / 'chunks.json', chunks)
                emit(f'구조화: {receipt["units"]}개 단위, {receipt["blocks"]}개 블록 → {len(chunks)}개 청크 (본문 전체)')
                for c in chunks[:3]:
                    emit(f'청크 예시 {c["id"]}: {c["text"][:160]}')
                provider = Genos(ROOT, output / 'calls', max_tokens=args.max_tokens, timeout=args.timeout, progress=emit)
                identities = provider.prepare()
                write(output / 'run-binding.json', {'adr': 'ADR-0305', 'source': source,
                      'question': args.question, 'identities': identities, 'parameters': vars(args),
                      'code_sha256': {str(p.relative_to(ROOT)): sha(p) for p in
                                     [Path(__file__), ROOT / '02_BACKEND/semantic_runtime/genos_backend.py',
                                      ROOT / '02_BACKEND/semantic_runtime/genos.py',
                                      ROOT / '02_BACKEND/semantic_runtime/pipeline.py', ROOT / '00_SYSTEM/PIPELINE.json']}})
                vector = review_and_embed(chunks, provider, store, output, args.batch_size, emit)
                runtime = TracedPipeline(ROOT, store, provider=provider, vector=vector, output=output, emit=emit)
                result = runtime.run(args.question, receipt['document_ids'], use_llm=True)
                write(output / 'pipeline-result.json', result)
                answer = result['answer']
                if not answer['text'].strip() or not answer['claims']:
                    raise ValueError('답변은 반환됐지만 인용된 주장이 없습니다. answer.json의 unresolved를 확인하세요.')
                (output / 'answer.txt').write_text(answer['text'] + '\n', encoding='utf-8')
                emit('최종 답변:\n' + answer['text'])
                write(output / 'result.json', {'ok': True, 'status': 'DRAFT', 'documents': 1,
                      'chunks': len(chunks), 'api_inference_calls': provider.calls,
                      'vector_search': True, 'cited_claims': len(answer['claims']),
                      'seconds': time.monotonic()-started, 'legal_accuracy': 'NOT_EVALUATED',
                      'main_activated': False, 'output': str(output)})
                emit(f'E2E 성공 — {output}/answer.txt / run.log / result.json')
            finally:
                store.db.close()
        return 0
    except Exception as exc:
        detail = safe(f'{type(exc).__name__}: {exc}')
        write(output / 'failure.json', {'ok': False, 'error': detail, 'seconds': time.monotonic()-started})
        emit(f'E2E 실패: {detail}\n기록 보존: {output}')
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', default=os.environ.get('GENOS_DATA_ROOT', ''))
    parser.add_argument('--json', action='store_true', help='호환 옵션; 단계 로그도 출력합니다')
    parser.add_argument('command', choices=['e2e'])
    parser.add_argument('--backend', choices=['genos'], required=True)
    parser.add_argument('--document', default='auto')
    parser.add_argument('--source', choices=['auto', 'internal', 'external'], default='auto')
    parser.add_argument('--question', default='이 문서의 목적과 주요 의무 또는 적용 대상을 원문 근거와 함께 설명해 주세요.')
    parser.add_argument('--run-root', default='')
    parser.add_argument('--chunk-chars', type=int, default=1400)
    parser.add_argument('--max-chunks', type=int, default=64)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--max-tokens', type=int, default=80000)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    for key, low, high in [('chunk_chars', 200, 4000), ('max_chunks', 1, 512),
                           ('batch_size', 1, 8), ('max_tokens', 256, 80000), ('timeout', 10, 600)]:
        if not low <= getattr(args, key) <= high:
            parser.error(f'--{key.replace("_", "-")}: {low}..{high}')
    if not args.question.strip() or len(args.question) > 10000:
        parser.error('question must be 1..10000 characters')
    try:
        return run(args)
    except Exception as exc:
        print(safe(f'E2E 준비 실패: {type(exc).__name__}: {exc}'), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
