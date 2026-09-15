"""Portable completed MOLEG packages. No network or model dependency."""
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import uuid
import zipfile

from lawrag.datasets.catalog import load_package
from lawrag.sources.moleg_knowledge import catalog_identity
from semantic_runtime.contracts import sha, digest
from semantic_runtime.moleg_links import Matcher

FORMAT = 'moleg-offline-transfer-v1'
CATALOGS = {'legal_terms', 'knowledge_terms', 'everyday_terms'}
RELATIONS = {'everyday_term_relations', 'legal_term_relations', 'term_articles'}


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink path is not allowed')
    return path


def relative(name):
    p = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or p.is_absolute()
            or any(s in {'', '.', '..'} for s in name.split('/'))):
        raise ValueError('invalid transfer path')
    return p


def inspect_package(path):
    path = plain(path)
    package = load_package(path, verify_files=True)
    manifest = json.loads(path.read_text())
    if any(manifest.get(k) != v for k, v in {'source_origin': 'public_external',
            'security_class': 'public', 'authority': 'authoritative', 'representation': 'real'}.items()):
        raise ValueError('completed official public MOLEG package required')
    kind = package.dataset_id.removeprefix('moleg-knowledge-').replace('-', '_')
    if kind not in CATALOGS | RELATIONS | {'legal_term_detail'}:
        raise ValueError('unsupported knowledge package')
    by_name = {Path(a.path).name: a for a in package.artifacts}
    plan = json.loads(by_name['request-plan.json'].resolved_path().read_text())
    if not plan.get('checkpoint', {}).get('completed'):
        raise ValueError('incomplete knowledge package')
    parameters = plan.get('parameters', {})
    if kind in CATALOGS and parameters:
        raise ValueError('catalogue must be a complete unfiltered list')
    aggregate = plan.get('collection_mode') == 'catalogue-enrichment'
    if aggregate and (kind in CATALOGS or not plan.get('catalogue_identity')):
        raise ValueError('invalid catalogue enrichment provenance')
    if kind == 'legal_term_detail' and not aggregate and not parameters.get('trmSeqs'):
        raise ValueError('definition package requires explicit source IDs')
    if kind in RELATIONS and not aggregate and not parameters.get('MST'):
        raise ValueError('relation package requires explicit source MST')
    return package, kind, by_name, plan


def pack(packages, output):
    output = plain(output)
    if output.exists():
        raise ValueError('immutable ZIP already exists')
    entries, selected, seen = {}, [], set()
    for path in map(Path, packages):
        package, kind, _, _ = inspect_package(path)
        if package.package_id in seen:
            raise ValueError('duplicate package identity')
        seen.add(package.package_id)
        prefix = f'packages/{package.package_id}/{package.generation_id}/'
        selected.append({'path': prefix + 'manifest.json', 'kind': kind, 'sha256': sha(path)})
        entries[prefix + 'manifest.json'] = path
        for artifact in package.artifacts:
            relative(artifact.path)
            entries[prefix + artifact.path] = artifact.resolved_path()
    if not selected:
        raise ValueError('no completed packages selected')
    record = {'schema_version': FORMAT, 'packages': selected,
              'files': {name: {'sha256': sha(p), 'bytes': p.stat().st_size} for name, p in sorted(entries.items())}}
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_name(output.name + '.incomplete-' + uuid.uuid4().hex)
    with zipfile.ZipFile(pending, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(entries.items()):
            archive.write(path, name)
        archive.writestr('transfer.json', json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    # Refuse source drift while packing before publishing a transferable ZIP.
    for name, path in entries.items():
        if sha(path) != record['files'][name]['sha256']:
            raise ValueError('package changed during ZIP creation')
    os.link(pending, output)
    pending.unlink()
    return {'path': str(output), 'sha256': sha(output), 'bytes': output.stat().st_size,
            'packages': len(selected), 'files': len(entries)}


def unpack(archive_path, destination):
    archive_path, destination = plain(archive_path), plain(destination)
    fingerprint = sha(archive_path)
    target = destination / fingerprint
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 50000 or sum(m.file_size for m in members) > 2 * 1024**3:
            raise ValueError('knowledge ZIP exceeds size/file limits')
        names = [m.filename for m in members]
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP member')
        for member in members:
            relative(member.filename)
            if member.is_dir() or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('ZIP directories/links are not package artifacts')
        record = json.loads(archive.read('transfer.json'))
        if record.get('schema_version') != FORMAT or set(names) != set(record['files']) | {'transfer.json'}:
            raise ValueError('ZIP manifest/member mismatch')
        for package in record['packages']:
            relative(package['path'])
            if package['path'] not in record['files'] or record['files'][package['path']]['sha256'] != package['sha256']:
                raise ValueError('ZIP package declaration mismatch')
        if not target.exists():
            temporary = destination / (fingerprint + '.incomplete-' + uuid.uuid4().hex)
            temporary.mkdir(parents=True)
            for member in members:
                path = temporary / member.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, path.open('xb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                if member.filename != 'transfer.json':
                    expected = record['files'][member.filename]
                    if path.stat().st_size != expected['bytes'] or sha(path) != expected['sha256']:
                        raise ValueError('ZIP artifact hash mismatch')
            for package in record['packages']:
                relative(package['path'])
                if sha(temporary / package['path']) != package['sha256']:
                    raise ValueError('package manifest hash mismatch')
                inspect_package(temporary / package['path'])
            temporary.rename(target)
        else:
            if not target.is_dir() or target.is_symlink():
                raise ValueError('invalid installed knowledge directory')
            for name, expected in record['files'].items():
                path = plain(target / name)
                if sha(path) != expected['sha256'] or path.stat().st_size != expected['bytes']:
                    raise ValueError('installed knowledge drift')
    packages = [target / row['path'] for row in record['packages']]
    return target, packages


def dictionary(packages, output):
    """Namespaced lexical rows are lookup data; no semantic admission."""
    output = plain(output)
    from .glossary_enrichment import compile_enrichment
    identity = {'packages': [sha(p) for p in packages], 'compiler_sha256': sha(__file__),
                'enrichment_compiler_sha256': sha(Path(__file__).with_name('glossary_enrichment.py')),
                'scope_compiler_sha256': sha(Path(__file__).with_name('glossary_scope.py'))}
    marker = output.with_suffix('.json')
    if output.exists():
        previous = json.loads(marker.read_text())
        if previous['identity'] != identity or previous['sha256'] != sha(output):
            raise ValueError('dictionary identity/hash changed')
        return previous
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.incomplete-' + uuid.uuid4().hex)
    counts = {}
    with closing(sqlite3.connect(temporary)) as db:
        db.execute('CREATE TABLE term(id TEXT PRIMARY KEY,kind TEXT NOT NULL,label TEXT NOT NULL,payload TEXT NOT NULL,package_sha256 TEXT NOT NULL)')
        for p in packages:
            _, kind, artifacts, plan = inspect_package(p)
            if kind not in CATALOGS:
                continue
            if kind in counts:
                raise ValueError('choose one completed generation per catalogue')
            count = 0
            package_sha = sha(p)
            with artifacts['records.jsonl'].resolved_path().open() as rows:
                for line in rows:
                    row = json.loads(line)
                    if row.get('entity_type') != kind or not row.get('source_id') or not row.get('label', '').strip():
                        raise ValueError('invalid catalogue row')
                    db.execute('INSERT INTO term VALUES (?,?,?,?,?)',
                               (catalog_identity(row), kind, row['label'], json.dumps(row, ensure_ascii=False), package_sha))
                    count += 1
            checkpoint = plan['checkpoint']; norm = plan.get('normalization', {})
            if (count != norm.get('normalized_record_count', checkpoint['record_count'])
                    or count + len(norm.get('exact_same_page_duplicates', [])) != checkpoint['record_count']
                    or checkpoint['record_count'] != checkpoint['total_count']):
                raise ValueError('catalogue completion count mismatch')
            counts[kind] = count
        db.execute('CREATE INDEX term_label ON term(label)')
        coverage = compile_enrichment(db, packages)
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('dictionary SQLite integrity failure')
    os.replace(temporary, output)
    report = {'identity': identity, 'counts': counts, 'coverage': coverage, 'sha256': sha(output), 'path': output.name,
              'legal_assessment': 'NOT_PERFORMED', 'llm_calls': 0}
    marker.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


class DictionaryHints:
    """Bounded literal matches; do not replace source-defined semantic concepts."""
    def __init__(self, path):
        self.path = plain(path)
        self.fingerprint = sha(path)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            self.matcher = Matcher(db.execute("SELECT id,label FROM term WHERE kind IN ('legal_terms','knowledge_terms')"))

    def enrich(self, source, receipt_path):
        receipt_path = Path(receipt_path)
        marker = source.with_suffix('.knowledge.json')
        if marker.exists():
            saved = json.loads(marker.read_text())
            if saved['dictionary_sha256'] != self.fingerprint or saved['source_sha256'] != sha(source):
                raise ValueError('source/dictionary binding drift')
            return
        from .glossary_enrichment import definition_hints
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as glossary, closing(sqlite3.connect(source)) as db:
            has_senses = glossary.execute("SELECT 1 FROM sqlite_master WHERE name='term_sense'").fetchone()
            rows = db.execute('SELECT job_id,input_json FROM authoring_job').fetchall()
            total = 0
            for ident, payload in rows:
                body = json.loads(payload); hints = []
                for block in body['blocks']:
                    for tid, lo, hi in self.matcher.find(block['text']):
                        if len(hints) >= 24:
                            break
                        hints.append({'term_id': tid, 'block_id': str(block['idx']), 'start': lo,
                                      'end': hi, 'surface': block['text'][lo:hi],
                                      'definitions': definition_hints(glossary, tid) if has_senses else {'candidates': [], 'total': 0, 'truncated': False, 'canonical_approval': False}})
                    if len(hints) >= 24:
                        break
                body['dictionary_lookup'] = {'dictionary_sha256': self.fingerprint,
                    'matches': hints, 'kind': 'LITERAL_LOOKUP_ONLY',
                    'instruction': '표제어 출현과 출처별 정의 후보다. SOURCE_ID는 원천 ID 연결이고 LABEL_CANDIDATE는 표기만 같은 후보다. 후보의 출처·적용 범위를 원문과 대조하고 동음이의어를 합치지 않는다. 의미·조건·효과는 별도로 검토한다.'}
                db.execute('UPDATE authoring_job SET input_json=? WHERE job_id=?',
                           (json.dumps(body, ensure_ascii=False), ident))
                total += len(hints)
            db.commit()
        receipt = json.loads(receipt_path.read_text())
        receipt['sha256'] = sha(source)
        receipt['dictionary_sha256'] = self.fingerprint
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        marker.write_text(json.dumps({'dictionary_sha256': self.fingerprint, 'source_sha256': sha(source),
                                     'hints': total}, indent=2) + '\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Pack completed public MOLEG packages for offline GENOS import')
    parser.add_argument('--package', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(pack(args.package, args.output), ensure_ascii=False, indent=2))
