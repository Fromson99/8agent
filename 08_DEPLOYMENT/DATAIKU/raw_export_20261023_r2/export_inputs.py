"""Run in GENOS TRANSFER. Read the actual DEV data; build RAW and support ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import transport as t

VERSION = 'GENOS_RAW_EXPORT_20261023_R2'


def verify_selection_scope(paths, fingerprints, original_paths, exceptions, report):
    """Use the unchanged, bundled R2 filename policy to reject scope drift."""
    import importlib.util
    policy_path = Path(__file__).with_name('filename_versions.py')
    spec = importlib.util.spec_from_file_location('export_filename_policy', policy_path)
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    policy.validate_exceptions(exceptions)

    def retained(names):
        rows = [{'document_id': name, 'path': name, 'filename': Path(name).name,
                 'filename_source': 'raw_filename', 'source_artifact_sha256': fingerprints[name]}
                for name in names if name.startswith('01_DATA/RAW/internal/')
                and Path(name).suffix.lower() in {'.pdf', '.doc', '.docx', '.hwp', '.hwpx', '.xml', '.html', '.htm'}]
        return {r['path'] for r in policy.select(rows, exceptions)
                if not r['physical_exclusion_candidate']}
    before = retained(original_paths)
    after = retained(paths) & set(original_paths)
    report['filename_selection_unchanged'] = before == after
    if before != after:
        report['selection_changes'] = {'newly_selected': sorted(after-before), 'newly_excluded': sorted(before-after)}
        raise ValueError('DEPENDENCY_SELECTION_DRIFT: preserve the selected input scope; review DEPENDENCY_CHECK.json')


def raw_reference(data, name):
    """Catalog references are data-relative RAW paths, never arbitrary local files."""
    if not isinstance(name, str) or not name.startswith(('RAW/internal/', 'RAW/external/')):
        raise ValueError('DEPENDENCY_PATH: ' + str(name))
    return t.checked(data, name)


def require_hash(path, expected):
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ValueError('DEPENDENCY_HASH_FORMAT: ' + str(path))
    if not path.is_file():
        raise ValueError('DEPENDENCY_MISSING: ' + str(path))
    if t.sha(path) != expected:
        raise ValueError('DEPENDENCY_HASH_MISMATCH: ' + str(path))


def include_origins(dev, paths, fingerprints, older, report):
    """Keep catalog-bound native companions without admitting unrelated RAW files.

    The unchanged R2 consumer scans RAW. Automatic additions are therefore limited
    to DOC/HWP companions of an admitted same-directory/same-stem PDF, which wins
    representation selection. Other new dependency types require explicit review;
    in particular, adding a ZIP could expand the job's input scope during unzip.
    """
    data = dev / '01_DATA'
    catalog_path = t.checked(data, 'CATALOG/RAW_DERIVATIVES.json')
    if not catalog_path.exists():
        report.update(status='VERIFIED', catalog_sha256=None)
        return
    catalog_hash = t.sha(catalog_path)
    catalog = t.read(catalog_path)
    if t.sha(catalog_path) != catalog_hash:
        raise ValueError('CATALOG_CHANGED')
    records, extractions = catalog.get('files'), catalog.get('extractions', {})
    if not isinstance(records, dict) or not isinstance(extractions, dict):
        raise ValueError('DEPENDENCY_CATALOG_FORMAT')
    layout_path = t.checked(data, 'CATALOG/TEAM_LAYOUT.json')
    layout_hash = t.sha(layout_path) if layout_path.exists() else None
    layout = t.read(layout_path) if layout_hash else {'files': {}}
    if layout_hash and t.sha(layout_path) != layout_hash:
        raise ValueError('CATALOG_CHANGED')
    registered = layout['files']
    if not isinstance(registered, dict):
        raise ValueError('TEAM_LAYOUT_FORMAT')
    report.update(catalog_sha256=catalog_hash, layout_sha256=layout_hash)
    active, done = set(), set()

    def visit(name, depth=0):
        if name in active:
            raise ValueError('DEPENDENCY_CYCLE: ' + name)
        if name in done:
            return
        if depth > 32:
            raise ValueError('DEPENDENCY_DEPTH: ' + name)
        active.add(name)
        relative = name.removeprefix('01_DATA/')
        meta = records.get(relative)
        edges = []
        if meta is not None:
            require_hash(paths[name], meta['sha256'])
            edges.append(('derived_origin', meta['origin'], meta['origin_sha256']))
        extraction = extractions.get(relative)
        # Match the existing consumer: registered sources take precedence over
        # extraction metadata; otherwise the archive is required for provenance.
        if extraction and relative not in registered:
            require_hash(paths[name], extraction['sha256'])
            edges.append(('extraction_archive', extraction['archive'], extraction['archive_sha256']))
        for relation, origin, expected in edges:
            original = raw_reference(data, origin)
            require_hash(original, expected)
            key = '01_DATA/' + origin
            edge = {'file': name, 'file_sha256': fingerprints[name],
                    'origin': key, 'origin_sha256': expected, 'relation': relation}
            report['references'].append(edge)
            if key not in paths:
                target = paths[name]
                if (relation != 'derived_origin' or target.suffix.lower() != '.pdf'
                        or original.suffix.lower() not in {'.doc', '.hwp'}
                        or original.parent != target.parent or original.stem != target.stem):
                    raise ValueError('DEPENDENCY_SCOPE_REVIEW: ' + origin)
                if expected in older:
                    raise ValueError('DEPENDENCY_SELECTION_CONFLICT: ' + origin)
                # A differing registered checksum would be rejected by RAW
                # preparation; report it now, before exporting either ZIP.
                registration = registered.get(origin)
                if registration and registration['sha256'] != expected:
                    raise ValueError('DEPENDENCY_REGISTRATION_MISMATCH: ' + origin)
                paths[key] = original
                fingerprints[key] = expected
                report['included_dependencies'].append({
                    'path': key, 'sha256': expected, 'required_by': name,
                    'reason': 'catalog-bound-native-companion',
                    'selection_role': 'companion_of_selected_pdf'})
            elif fingerprints[key] != expected:
                raise ValueError('DEPENDENCY_INPUT_CONFLICT: ' + origin)
            visit(key, depth+1)
        active.remove(name)
        done.add(name)

    for name in sorted(paths):
        visit(name)
    if t.sha(catalog_path) != catalog_hash or (layout_hash and t.sha(layout_path) != layout_hash):
        raise ValueError('CATALOG_CHANGED')
    report['status'] = 'VERIFIED'


def verify_archive(archive, expected):
    """Verify selected/dependency bytes as actually packed, without restoring data."""
    with zipfile.ZipFile(archive) as z:
        if z.getinfo('TRANSPORT.json').file_size > 64 * t.CHUNK:
            raise ValueError('MANIFEST_TOO_LARGE')
        manifest = json.loads(z.read('TRANSPORT.json'))
        for name, fingerprint in expected.items():
            if manifest['files'].get(name, {}).get('sha256') != fingerprint:
                raise ValueError('PACKED_INPUT_CHANGED: ' + name)
    return manifest


def latest_mapping(dev, *, selection_file=None):
    """The user's RAG selection, never a filesystem newest-file guess."""
    config_path = dev / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    config = t.read(config_path) if config_path.exists() else {}
    binding = config.get('search_selection')
    default = binding['path'] if binding else 'GENOS_LATEST_SELECTION_DATA_20261021_R1.zip'
    path = t.checked(dev, selection_file or default)
    if not path.is_file():
        raise ValueError('RAG_SELECTION_MISSING: ' + str(path))
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as z:
            if sorted(z.namelist()) != ['BUNDLE.json', 'generation.json'] or any(i.file_size > 32*t.CHUNK for i in z.infolist()):
                raise ValueError('SELECTION_ZIP_MEMBERS')
            bundle, raw = json.loads(z.read('BUNDLE.json')), z.read('generation.json')
            if (bundle.get('version') != 'GENOS_SEARCH_SELECTION_TRANSFER_20261021_R1'
                    or hashlib.sha256(raw).hexdigest() != bundle['selection_sha256']):
                raise ValueError('SELECTION_ZIP_HASH')
        value = json.loads(raw)
    else:
        if not binding or str(path.relative_to(dev)) != binding['path'] or t.sha(path) != binding['sha256']:
            raise ValueError('RAG_SELECTION_BINDING')
        value = t.read(path)
    if value.get('schema_version') != 'filename-search-selection-v2':
        raise ValueError('LATEST_V2_SELECTION_REQUIRED')
    marks = value['latest_documents']
    if (len({m['document_id'] for m in marks}) != len(marks)
            or any(type(m.get('is_latest')) is not bool for m in marks)
            or {m['document_id'] for m in marks if not m['is_latest']} != {m['document_id'] for m in value['excluded']}):
        raise ValueError('LATEST_SELECTION_INCONSISTENT')
    if binding and selection_file and path.suffix.lower() == '.zip':
        active = t.checked(dev, binding['path'])
        if t.sha(active) != binding['sha256'] or t.read(active) != value:
            raise ValueError('ZIP_DIFFERS_FROM_ACTIVE_RAG_SELECTION')
    return path, value


def export(dev, output, *, selection_file=None):
    dev = Path(dev).resolve(strict=True)
    output = Path(output).resolve()
    if output.is_relative_to(dev / '01_DATA'):
        raise ValueError('OUTPUT_INSIDE_DATA')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('OUTPUT_NOT_EMPTY: preserve prior artifacts; choose a new output directory')
    t.write(output / 'export-status.json', {'status': 'STARTED', 'source': str(dev), 'exporter': VERSION})
    dependency = {'status': 'CHECKING', 'references': [], 'included_dependencies': []}
    try:
        selected, value = latest_mapping(dev, selection_file=selection_file)
        raw = dev / '01_DATA/RAW'
        if not raw.is_dir():
            raise ValueError('RAW_NOT_FOUND')
        latest = {m['source_artifact_sha256'] for m in value['latest_documents'] if m['is_latest']}
        older = {m['source_artifact_sha256'] for m in value['latest_documents'] if not m['is_latest']} - latest
        paths, omitted, matched, fingerprints = {}, [], set(), {}
        for path in t.files(raw):
            rel = str(path.relative_to(dev))
            internal = path.relative_to(raw).parts[0] == 'internal'
            fingerprint = t.sha(path)
            if fingerprint in older or (internal and fingerprint not in latest):
                omitted.append({'path': rel, 'sha256': fingerprint,
                                'reason': 'older-version' if fingerprint in older else 'not-in-rag-latest-selection'})
                continue
            paths[rel] = path
            fingerprints[rel] = fingerprint
            if fingerprint in latest:
                matched.add(fingerprint)
        selection = {'path': str(selected.relative_to(dev)), 'sha256': t.sha(selected),
                     'policy': 'RAG-latest-v2-artifact-hash', 'omitted': omitted,
                     'missing_latest_hashes': sorted(latest - matched),
                     'external_policy': 'preserve-RAW-external; supplied selection marks internal versions'}
        t.write(output / 'RAW_SELECTION_REPORT.json', selection)
        if latest - matched:
            raise ValueError('LATEST_RAW_MISSING: see RAW_SELECTION_REPORT.json; no silent partial export')
        original_paths = set(paths)
        include_origins(dev, paths, fingerprints, older, dependency)
        verify_selection_scope(paths, fingerprints, original_paths, value['exceptions']['value'], dependency)
        added = {r['path'] for r in dependency['included_dependencies']}
        selection['omitted'] = [r for r in omitted if r['path'] not in added]
        selection['included_dependencies'] = dependency['included_dependencies']
        selection['exporter'] = VERSION
        t.write(output / 'DEPENDENCY_CHECK.json', dependency)
        t.write(output / 'RAW_SELECTION_REPORT.json', selection)
        t.write(output / 'generation.json', value)
        t.write(output / 'filename-exceptions.json', value['exceptions']['value'])
        paths['01_DATA/INPUT_MAPPING/generation.json'] = output / 'generation.json'
        paths['01_DATA/INPUT_MAPPING/filename-exceptions.json'] = output / 'filename-exceptions.json'
        paths['01_DATA/INPUT_MAPPING/RAW_SELECTION_REPORT.json'] = output / 'RAW_SELECTION_REPORT.json'
        paths['01_DATA/INPUT_MAPPING/DEPENDENCY_CHECK.json'] = output / 'DEPENDENCY_CHECK.json'
        config_path = dev / '00_SYSTEM/GLOSSARY_PIPELINE.json'
        config_hash = t.sha(config_path)
        config = t.read(config_path)
        draft = config['draft_assembly']['current_draft'] if 'current_draft' in config['draft_assembly'] else config['current_draft']
        knowledge = config['knowledge_bundle']
        support = {}
        for item in (draft, knowledge):
            if item.get('root_id', 'data') != 'data':
                raise ValueError('SUPPORT_ROOT')
            folder = t.checked(dev / '01_DATA', item['path'])
            if not folder.is_dir():
                raise ValueError('SELECTED_SUPPORT_MISSING: ' + str(folder))
            for p in t.files(folder):
                support[str(p.relative_to(dev))] = p
        for p in t.files(dev / '01_DATA/CATALOG'):
            support[str(p.relative_to(dev))] = p
        # All preflight checks precede the large ZIP writes. Keep source bytes and
        # original catalogs intact; compare the packed snapshots to those checked.
        for name, fingerprint in fingerprints.items():
            if t.sha(paths[name]) != fingerprint:
                raise ValueError('SOURCE_CHANGED: ' + name)
        raw_result = t.pack(paths, output / 'RAW_INPUT.zip', metadata={'mapping': selection})
        verify_archive(output / 'RAW_INPUT.zip', fingerprints)
        support_result = t.pack(support, output / 'PIPELINE_SUPPORT.zip',
                                metadata={'glossary_config_sha256': config_hash})
        catalogs = {path: fingerprint for path, fingerprint in (
            ('01_DATA/CATALOG/RAW_DERIVATIVES.json', dependency.get('catalog_sha256')),
            ('01_DATA/CATALOG/TEAM_LAYOUT.json', dependency.get('layout_sha256'))) if fingerprint}
        verify_archive(output / 'PIPELINE_SUPPORT.zip', catalogs)
        if t.sha(config_path) != config_hash or t.sha(selected) != selection['sha256']:
            raise ValueError('SOURCE_SELECTION_CHANGED')
        result = {'status': 'EXPORTED', 'exporter': VERSION, 'source': str(dev),
                  'raw': raw_result, 'support': support_result, 'mapping': selection,
                  'dependency_check': dependency}
        t.write(output / 'export-status.json', result)
        return result
    except Exception as exc:
        dependency.update(status='FAILED', error=str(exc))
        t.write(output / 'DEPENDENCY_CHECK.json', dependency)
        t.write(output / 'export-status.json', {'status': 'FAILED', 'source': str(dev),
                                               'exporter': VERSION, 'error': str(exc)})
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dev', type=Path, default=Path.home() / 'DEV')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--selection-file', help='DEV-relative selection ZIP/JSON; default is active RAG binding, otherwise the named 20261021 ZIP')
    a = p.parse_args()
    result = export(a.dev, a.output, selection_file=a.selection_file)
    print(result['status'], 'RAW_INPUT.zip', 'PIPELINE_SUPPORT.zip')
