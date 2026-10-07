#!/usr/bin/env python3
"""Read-only, two-query PeCab retrieval inspection in the GENOS codespace."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '02_BACKEND'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation', type=Path,
                        default=os.environ.get('GENOS_GENERATION'))
    args = parser.parse_args()
    if not args.generation:
        parser.error('set GENOS_GENERATION or --generation')
    generation = Path(args.generation).resolve(strict=True)
    manifest = json.loads((generation / 'manifest.json').read_text('utf-8'))
    binding = manifest.get('fulltext')
    if not isinstance(binding, dict):
        parser.error('selected generation has no fulltext binding')
    fulltext = (generation / binding['path']).resolve(strict=True)
    fulltext.relative_to(generation)
    tokenizer = json.loads((fulltext / 'manifest.json').read_text('utf-8'))['tokenizer']
    from semantic_runtime.fulltext import expression, question_terms, tokenizer_version
    if tokenizer.get('name') != 'pecab' or tokenizer.get('version') != tokenizer_version():
        parser.error('generation tokenizer is not the installed PeCab version')
    navigation = (generation / manifest['navigation']['path'] / 'navigation.sqlite').resolve(strict=True)
    navigation.relative_to(generation)
    indexed = (fulltext / 'fulltext.sqlite').resolve(strict=True)
    with (sqlite3.connect(indexed.as_uri() + '?mode=ro', uri=True) as search,
          sqlite3.connect(navigation.as_uri() + '?mode=ro', uri=True) as sources):
        for number in (1, 2):
            try:
                query = input(f'내부 문서에서 답을 아는 짧은 검색어 {number}/2: ').strip()
            except EOFError:
                break
            if not query:
                break
            terms = question_terms(query)
            if not terms:
                print('검색 형태소 없음')
                continue
            rows = search.execute(
                'SELECT source_id FROM source_fts WHERE source_fts MATCH ? '
                'ORDER BY bm25(source_fts,0,10,1),source_id LIMIT 5',
                (expression(terms),)).fetchall()
            print(f'상위 {len(rows)}건 (원문 본문은 출력하지 않음)')
            for rank, (source_id,) in enumerate(rows, 1):
                row = sources.execute('SELECT json FROM source WHERE id=?', (source_id,)).fetchone()
                if row is None:
                    raise ValueError('fulltext source is absent from navigation')
                source = json.loads(row[0])
                title = ' '.join((source.get('document_name') or '').split())[:90]
                heading = ' '.join((source.get('heading') or '').split())[:90]
                print(f'{rank}. {title} / {heading} [{source_id}]')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
