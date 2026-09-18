"""GENOS PDF structural parser, based on the pinned official parser facade.

Install as /app/src/preprocessor.py in an image containing the dependencies of
genonai/doc_parser_code_serving@aa610c3db24aaa02c65e953279f1a60d014babaf.
The platform main.py wraps our return value in {code, errMsg, data} exactly once.
"""
from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path

import yaml
from docling_core.types.doc import DoclingDocument
from genon.preprocessor.facade.parser_processor import DocumentProcessor as BaseProcessor

VERSION = '8agent-structured-pdf-v1'
UPSTREAM_REVISION = 'aa610c3db24aaa02c65e953279f1a60d014babaf'


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def document_payload(document):
    """Preserve the model dump; add ordered text with links into the same tree."""
    items, parts, offset = [], [], 0
    for item, _level in document.iterate_items():
        label = str(getattr(item, 'label', '')).split('.')[-1].lower()
        table = getattr(item, 'data', None)
        if hasattr(table, 'table_cells'):
            # A text convenience view only. Logical cell spans remain in document.
            text = '\n'.join(cell.text for cell in table.table_cells)
        else:
            text = getattr(item, 'text', '') or ''
            marker = getattr(item, 'marker', '') or ''
            if marker and not text.lstrip().startswith(marker):
                text = marker + ' ' + text
        if parts:
            offset += 1
        start = offset
        parts.append(text)
        offset += len(text)
        items.append({'ref': item.self_ref, 'label': label, 'text': text,
                      'char_span': [start, offset],
                      'pages': sorted({p.page_no for p in getattr(item, 'prov', [])})})
    return {'schema_version': VERSION, 'document': document.model_dump(mode='json'),
            'full_text': '\n'.join(parts), 'reading_order': items,
            'text_view_policy': 'newline between items; tables use logical cell order; document is authoritative',
            'capabilities': {'docling_document': True, 'chunked': False,
                             'coordinates': 'preserved where emitted by parser',
                             'table_cells': 'preserved where emitted by parser',
                             'generated_enrichment': False}}


class DocumentProcessor(BaseProcessor):
    IS_PARSER = True

    def __init__(self, config_path=None):
        selected = config_path or os.environ.get('GENOS_STRUCTURE_CONFIG')
        if not selected:
            raise ValueError('Set GENOS_STRUCTURE_CONFIG to the prepared parser YAML')
        config = Path(selected).resolve(strict=True)
        cfg = yaml.safe_load(config.read_text(encoding='utf-8'))
        if (not isinstance(cfg, dict) or cfg.get('enrichment') != []
                or (cfg.get('output') or {}).get('format') != 'docling'):
            raise ValueError('Structured parser requires enrichment: [] and output.format: docling')
        self._structure_config_sha = sha(config)
        self._structure_base_sha = sha(inspect.getfile(BaseProcessor))
        super().__init__(str(config))

    async def __call__(self, request, file_path, **kwargs):
        source = Path(file_path)
        if (not source.is_absolute() or source.suffix.lower() != '.pdf'
                or any(p.is_symlink() for p in (source, *source.parents))
                or not source.is_file()):
            raise ValueError('Structured parser requires an existing absolute non-symlink PDF')
        with source.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                raise ValueError('Input is not a PDF')
        before = sha(source)
        # Server-owned options: callers cannot inject generated summaries into
        # the raw evidence contract. Layout/OCR/model settings stay in the YAML.
        params = dict(kwargs)
        for key in ('img_desc', 'chart_desc', 'chart_detection', 'doc_summary',
                    'table_desc', 'table_refine', 'table_text_desc', 'toc', 'metadata', 'custom_fields'):
            params[key] = 0
        result = await super().__call__(request, str(source), **params)
        if not isinstance(result, dict) or not isinstance(result.get('document'), dict):
            raise ValueError('Installed parser did not return a Docling document')
        document = DoclingDocument.model_validate(result['document'])
        import fitz
        with fitz.open(source) as pdf:
            if pdf.needs_pass or set(document.pages) != set(range(1, len(pdf)+1)):
                raise ValueError('Source PDF and parsed page set do not match')
        if not document.pages or not (document.texts or document.tables):
            raise ValueError('Parser returned an empty document')
        if sha(source) != before:
            raise ValueError('Source PDF changed while parsing')
        output = document_payload(document)
        output['provenance'] = {'source_sha256': before, 'config_sha256': self._structure_config_sha,
                                'base_module_sha256': self._structure_base_sha,
                                'implementation': VERSION, 'reference_upstream_revision': UPSTREAM_REVISION}
        # Preserve audit classifications if the configured upstream guardrail emits them.
        for key in ('usage', 'sensitive_infos'):
            if key in result:
                output[key] = result[key]
        return output
