"""One rule for binding a 별표·서식 citation to a separately stored annex file.

A file belongs to a regulation only when it sits in an annex folder directly
under that regulation's catalog path and its title carries the cited label.
The same rule is used by the reference builder and by runtime connection menus.
"""
import re

from .document_roles import ANNEX_FOLDERS

RESOLUTION = 'EXACT_DETACHED_ANNEX_FOLDER'
BASIS = 'annex folder directly under the owning regulation path with the same annex label'


def label(kind, number):
    """`별지 제9호서식`·`[서식 9]` and `별표 3의2`·`별표 3-2` compare as one label."""
    kind = '서식' if kind in ('별지', '서식') else kind
    return kind + re.sub(r'\s+', '', number).replace('호', '').replace('의', '-')


def text_label(text, start=0):
    """Label of the first annex citation at or after `start`, read from the full text."""
    from .term_references import ANNEX
    match = ANNEX.search(text or '', start)
    return label(match[1], match[2]) if match else None


def path(document_name):
    return tuple(part.strip() for part in (document_name or '').split(' > '))


def owner_path(document_name):
    """An annex file cites on behalf of its regulation; a body document is its own owner."""
    parts = path(document_name)
    return parts[:-2] if len(parts) >= 3 and parts[-2] in ANNEX_FOLDERS else parts


def file_key(document_name):
    parts = path(document_name)
    if len(parts) < 3 or parts[-2] not in ANNEX_FOLDERS:
        return None
    found = text_label(parts[-1])
    return (parts[:-2], found) if found else None


def index(entries):
    """(source_id, document_id, document_name) rows -> annex files and body-document owners.

    files: {(owner path, label): {document_id: [source_id]}}
    owners: {full name or title: {owner path}} for body documents, to resolve a named citation.
    """
    files, owners = {}, {}
    for source_id, document_id, document_name in entries:
        key = file_key(document_name)
        if key:
            files.setdefault(key, {}).setdefault(document_id, []).append(source_id)
            continue
        parts = path(document_name)
        for name in {(document_name or '').strip(), parts[-1]}:
            owners.setdefault(name, set()).add(parts)
    return {'files': files, 'owners': owners}


def owner_for(annex_index, citing_document_name, document_name_hint):
    """Named citation -> that regulation; unnamed -> the citing document's regulation."""
    hint = (document_name_hint or '').strip()
    if not hint:
        return owner_path(citing_document_name)
    found = annex_index['owners'].get(hint, set())
    return next(iter(found)) if len(found) == 1 else None


def cited_label(reference):
    """Re-read the label from the witness so a clipped mention (`[별지 제11호`) keeps `의8`."""
    text, start = reference.get('source_text'), reference.get('mention_start')
    if isinstance(text, str) and isinstance(start, int) and 0 <= start <= len(text):
        found = text_label(text[start:start + 40])
        if found:
            return found
    return text_label(reference.get('locator') or reference.get('mention_text') or '')


def resolve(annex_index, owner, cited, citing_document_id):
    """-> (document_id, source_ids) | ('AMBIGUOUS', document_ids) | None. Never the citing file itself."""
    found = {did: sids for did, sids in annex_index['files'].get((tuple(owner), cited), {}).items()
             if did != citing_document_id}
    if len(found) > 1:
        return 'AMBIGUOUS', sorted(found)
    if not found:
        return None
    (did, sids), = found.items()
    return did, list(sids)
