"""Run in GENOS TRANSFER. Read the actual DEV data; build RAW and support ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import transport as t


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
    t.write(output / 'export-status.json', {'status': 'STARTED', 'source': str(dev)})
    try:
        selected, value = latest_mapping(dev, selection_file=selection_file)
        raw = dev / '01_DATA/RAW'
        if not raw.is_dir():
            raise ValueError('RAW_NOT_FOUND')
        latest = {m['source_artifact_sha256'] for m in value['latest_documents'] if m['is_latest']}
        older = {m['source_artifact_sha256'] for m in value['latest_documents'] if not m['is_latest']} - latest
        paths, omitted, matched = {}, [], set()
        for path in t.files(raw):
            rel = str(path.relative_to(dev))
            internal = path.relative_to(raw).parts[0] == 'internal'
            fingerprint = t.sha(path)
            if fingerprint in older or (internal and fingerprint not in latest):
                omitted.append({'path': rel, 'sha256': fingerprint,
                                'reason': 'older-version' if fingerprint in older else 'not-in-rag-latest-selection'})
                continue
            paths[rel] = path
            if fingerprint in latest:
                matched.add(fingerprint)
        selection = {'path': str(selected.relative_to(dev)), 'sha256': t.sha(selected),
                     'policy': 'RAG-latest-v2-artifact-hash', 'omitted': omitted,
                     'missing_latest_hashes': sorted(latest - matched),
                     'external_policy': 'preserve-RAW-external; supplied selection marks internal versions'}
        t.write(output / 'RAW_SELECTION_REPORT.json', selection)
        if latest - matched:
            raise ValueError('LATEST_RAW_MISSING: see RAW_SELECTION_REPORT.json; no silent partial export')
        t.write(output / 'generation.json', value)
        t.write(output / 'filename-exceptions.json', value['exceptions']['value'])
        paths['01_DATA/INPUT_MAPPING/generation.json'] = output / 'generation.json'
        paths['01_DATA/INPUT_MAPPING/filename-exceptions.json'] = output / 'filename-exceptions.json'
        paths['01_DATA/INPUT_MAPPING/RAW_SELECTION_REPORT.json'] = output / 'RAW_SELECTION_REPORT.json'
        raw_result = t.pack(paths, output / 'RAW_INPUT.zip', metadata={'mapping': selection})
        config = t.read(dev / '00_SYSTEM/GLOSSARY_PIPELINE.json')
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
        support_result = t.pack(support, output / 'PIPELINE_SUPPORT.zip',
                                metadata={'glossary_config_sha256': t.sha(dev / '00_SYSTEM/GLOSSARY_PIPELINE.json')})
        result = {'status': 'EXPORTED', 'raw': raw_result, 'support': support_result, 'mapping': selection}
        t.write(output / 'export-status.json', result)
        return result
    except Exception as exc:
        t.write(output / 'export-status.json', {'status': 'FAILED', 'error': str(exc)})
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dev', type=Path, default=Path.home() / 'DEV')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--selection-file', help='DEV-relative selection ZIP/JSON; default is active RAG binding, otherwise the named 20261021 ZIP')
    a = p.parse_args()
    result = export(a.dev, a.output, selection_file=a.selection_file)
    print(result['status'], 'RAW_INPUT.zip', 'PIPELINE_SUPPORT.zip')
