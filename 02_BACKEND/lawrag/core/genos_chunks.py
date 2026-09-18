"""Lossless assembly of the observed GENOS indexed text-chunk response.

Transport chunks are evidence, not semantic sections. No overlap deletion, text
rewrite, guessed table cells or invented rectangles occurs in this adapter.
"""
from dataclasses import dataclass
import hashlib

VERSION = 'genos-chunk-assembly-v2-page-metadata'


@dataclass
class ChunkDocument:
    chunks: list
    full_text: str
    spans: list
    pages: dict
    page_metadata: dict

    def dump(self):
        return {'version': VERSION, 'chunks': self.chunks, 'full_text': self.full_text,
                'chunk_spans': self.spans, 'page_count': len(self.pages),
                'page_metadata': self.page_metadata,
                'join_policy': 'one explicit newline between transport chunks; no deduplication',
                'coverage': 'all returned chunks; PDF extraction completeness unverified',
                'text_sha256': hashlib.sha256(self.full_text.encode()).hexdigest()}


def assemble(chunks, source):
    import fitz
    if not chunks or any(not isinstance(c, dict) for c in chunks):
        raise ValueError('GENOS chunk array must contain objects')
    required = ('i_chunk_on_doc', 'n_chunk_of_doc', 'i_page', 'e_page', 'n_page')
    for chunk in chunks:
        if any(type(chunk.get(k)) is not int for k in required):
            raise ValueError('GENOS chunk array requires integer indices, counts and page ranges')
        if not isinstance(chunk.get('text'), str):
            raise ValueError('GENOS chunk text must be a string')
    ordered = sorted(chunks, key=lambda c: c['i_chunk_on_doc'])
    if ([c['i_chunk_on_doc'] for c in ordered] != list(range(len(ordered)))
            or any(c['n_chunk_of_doc'] != len(ordered) for c in ordered)):
        raise ValueError('GENOS chunk sequence incomplete or duplicated')
    with fitz.open(source) as pdf:
        count = len(pdf)
        pages = {i+1: {'width': p.rect.width, 'height': p.rect.height} for i, p in enumerate(pdf)}
    if any(not 1 <= c['i_page'] <= c['e_page'] <= count for c in ordered):
        raise ValueError(f'GENOS chunk page range differs from source PDF (physical pages={count})')
    reported = {c['n_page'] for c in ordered}
    last_start = max(c['i_page'] for c in ordered)
    # Official attachment_processor.compose_vectors computes n_page from the
    # zero-based loader page BEFORE adding one to i_page/e_page. It may also
    # exclude trailing empty pages. Never shift i_page or use n_page to truncate.
    if len(reported) != 1 or next(iter(reported)) not in {count, last_start - 1}:
        raise ValueError(f'GENOS chunk n_page metadata inconsistent (physical pages={count}, '
                         f'reported={sorted(reported)}, last chunk start={last_start})')
    reported_count = next(iter(reported))
    metadata = {'physical_page_count': count, 'reported_n_page': reported_count,
                'n_page_semantics': 'physical_count' if reported_count == count else 'last_zero_based_chunk_start',
                'page_number_base': 1, 'page_numbers_shifted': False,
                'pages_without_chunks': sorted(set(pages) - {c['i_page'] for c in ordered})}
    if any(c['i_page'] != c['e_page'] for c in ordered):
        raise ValueError('GENOS multi-page chunk lacks exact text-page mapping; request page chunks or Docling output')
    if [c['i_page'] for c in ordered] != sorted(c['i_page'] for c in ordered):
        raise ValueError('GENOS chunk page order contradicts document indices')
    if not any(c['text'].strip() for c in ordered):
        raise ValueError('GENOS returned empty chunk text')
    parts, spans, offset = [], [], 0
    for chunk in ordered:
        text = chunk['text']
        if parts:
            offset += 1  # Explicit assembly separator, never claimed as source text.
        spans.append({'chunk': chunk['i_chunk_on_doc'], 'start': offset,
                      'end': offset+len(text), 'page': chunk['i_page']})
        parts.append(text)
        offset += len(text)
    return ChunkDocument(ordered, '\n'.join(parts), spans, pages, metadata)


def elements(document):
    from .parse_adapter import Element
    out = []
    for chunk, span in zip(document.chunks, document.spans):
        offset = span['start']
        # Actual line boundaries provide structure candidates; transport chunk
        # boundaries alone never become a semantic node. Blank bytes remain in
        # full_text and raw chunk evidence even when no text block is emitted.
        for line in chunk['text'].splitlines(keepends=True):
            if line.strip():
                out.append(Element(index=len(out), type='text', text=line,
                    page=span['page'], bbox=None, meta={
                        'source_format': 'genos-chunks', 'chunk_index': span['chunk'],
                        'assembled_char_span': [offset, offset+len(line)],
                        'coordinates': 'unavailable', 'table_structure': 'unavailable',
                        'page_evidence': 'server_chunk_metadata'}))
            offset += len(line)
    return out


def parse_result(document, source, policy, receipt, born, pdf_stats):
    from .parse_adapter import ParseResult
    rows = elements(document)
    return ParseResult(path=str(source), doc_id=policy['source_sha256'][:12],
        parser='GENOS complete chunk text (structure requires PDF VLM)',
        born_digital=born, elements=rows, warnings=[
            '전체 응답 청크를 순서대로 결합했습니다. 청크 중복/겹침은 임의 삭제하지 않았습니다.',
            '청크 응답의 표 셀·정확한 좌표는 미확인입니다. 원본 PDF VLM 틀 검수가 필요합니다.'],
        stats={**pdf_stats, 'parser_identity': policy, 'preprocessor': receipt,
               'elements': len(rows), 'tables': 0, 'pictures': 0,
               'requires_structure_vlm': True, 'source_format': 'genos-chunks',
               'chunk_assembly': {k: v for k, v in document.dump().items()
                                  if k not in {'chunks', 'full_text'}},
               'spatial_fidelity': 'unavailable', 'table_fidelity': 'unavailable'})
