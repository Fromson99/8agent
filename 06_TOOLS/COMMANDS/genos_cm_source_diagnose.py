"""Read-only document identity diagnosis for a failed CM R8 package check.

This reports the selected binding; it never repairs a hash, selects a replacement
document, imports a package, commits code, or invokes a model.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unicodedata

VERSION = 'GENOS_CM_SOURCE_DIAG_20261007_R3'
PACKAGE_SHA256 = 'bcf9705d67270965a937d3c79c6506078d4272d94821fd838141672655f8ef9f'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    fingerprint = hashlib.sha256()
    total = 0
    with path.open('rb') as handle:
        while chunk := handle.read(4*1024*1024):
            fingerprint.update(chunk)
            total += len(chunk)
            if total % (64*1024*1024) == 0:
                print('원문 DB 해시 확인: '+str(total//(1024*1024))+' MiB', flush=True)
    return fingerprint.hexdigest()


def signature(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def normalized_name(name):
    # Suggestions only. Never used as an accepted document identity.
    return ''.join(unicodedata.normalize('NFKC', name).split())


def identities(expected, documents):
    """Independently report names, hashes without names, and their intersection."""
    by_name, by_hash = defaultdict(list), defaultdict(list)
    for doc in documents:
        by_name[doc['name']].append(doc)
        by_hash[doc['source_artifact_sha256']].append(doc)
    results = []
    for item in expected:
        name, fingerprint = item['name'], item['source_artifact_sha256']
        names, hashes = by_name[name], by_hash[fingerprint]
        exact = [d for d in names if d['source_artifact_sha256'] == fingerprint]
        identity = ('HASH_NOT_FOUND' if not hashes else
                    'HASH_AMBIGUOUS' if len(hashes) > 1 else
                    'HASH_MATCH_SAME_NAME' if hashes[0]['name'] == name else 'HASH_MATCH_DIFFERENT_NAME')
        strict = ('EXACT' if len(exact) == 1 else 'EXACT_AMBIGUOUS' if exact else
                  'ARTIFACT_HASH_DIFFERS' if names else 'NAME_MISSING')
        suggestions = []
        if not names:
            key = normalized_name(name)
            suggestions = [d for d in documents if normalized_name(d['name']) == key]
        results.append({'document_name': name, 'expected_source_artifact_sha256': fingerprint,
                        'expected_document_id': item.get('document_id'),
                        'classification': strict, 'identity_classification': identity,
                        'name_matches': names, 'hash_matches_without_name': hashes,
                        'spacing_name_suggestions_only': suggestions})
    return results


def compare(package, db):
    expected = defaultdict(set)
    for case in package['cases']:
        for entry in case['entries']:
            expected[entry['document_name']].add(entry['source_artifact_sha256'])
    documents = [dict(row) for row in db.execute(
        'SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY name,document_id')]
    inputs = [{'name': name, 'source_artifact_sha256': fingerprint}
              for name, fingerprints in sorted(expected.items()) for fingerprint in sorted(fingerprints)]
    results = identities(inputs, documents)
    return {'document_count': len(expected), 'selected_document_count': len(documents),
            'counts': dict(Counter(r['classification'] for r in results)),
            'identity_counts_without_name': dict(Counter(r['identity_classification'] for r in results)),
            'documents': results}


def compare_all(reference, documents):
    expected = reference['documents']
    rows = identities(expected, documents)
    known = {d['source_artifact_sha256'] for d in expected}
    extras = [d for d in documents if d['source_artifact_sha256'] not in known]
    groups = defaultdict(list)
    for doc in documents:
        groups[doc['source_artifact_sha256']].append(doc)
    duplicates = [v for v in groups.values() if len(v) > 1]
    exact_inventory = Counter(d['source_artifact_sha256'] for d in expected) == Counter(
        d['source_artifact_sha256'] for d in documents)
    return {'reference_documents': len(expected), 'selected_documents': len(documents),
            'name_presence_count': sum(bool(r['name_matches']) for r in rows),
            'strict_name_and_hash_counts': dict(Counter(r['classification'] for r in rows)),
            'hash_counts_without_name': dict(Counter(r['identity_classification'] for r in rows)),
            'hash_inventory_equal_without_name': exact_inventory,
            'name_and_hash_inventory_equal': Counter((d['name'], d['source_artifact_sha256']) for d in expected) == Counter(
                (d['name'], d['source_artifact_sha256']) for d in documents),
            'selected_only_hash_documents': extras, 'selected_duplicate_hash_groups': duplicates,
            'documents': rows}


def inspect(transfer, reference=None):
    transfer = Path(transfer).resolve(strict=True)
    if transfer.name != 'TRANSFER':
        raise ValueError('기존 DEV/TRANSFER에서 실행해야 합니다.')
    root = transfer.parent
    config_path = root/'00_SYSTEM/GENOS_SERVING_PATHS.json'
    status_path = transfer/'cm-oneclick-r8/STATUS.json'
    package_path = transfer/'cm-oneclick-r8/CM51_SOURCE_PACKAGE.json'
    watched = [config_path, status_path, package_path]
    before = {str(p): signature(p) for p in watched}
    config_raw = config_path.read_bytes()
    config = json.loads(config_raw)
    status = json.loads(status_path.read_bytes())
    package_raw = package_path.read_bytes()
    if sha(package_raw) != PACKAGE_SHA256:
        raise ValueError('R8 원본 패키지 해시가 다릅니다. 기존 자료를 보존했습니다.')
    if config.get('schema_version') != 'genos-serving-paths-v1' or config.get('selection') != 'operator-fixed':
        raise ValueError('R8의 명시 서빙 경로 설정이 아닙니다.')
    generation = Path(config['generation']).resolve(strict=True)
    if generation != Path(status['generation']).resolve(strict=True):
        raise ValueError('R8 실행 기록과 서빙 설정의 generation 경로가 다릅니다.')
    manifest_path = generation/'manifest.json'
    database_path = generation/'store.sqlite'
    for path in (manifest_path, database_path):
        before[str(path)] = signature(path)
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    manifest_sha = sha(manifest_raw)
    if manifest_sha != config['generation_manifest_sha256'] or manifest_sha != status['generation_manifest_sha256']:
        raise ValueError('R8 실행 후 generation manifest가 달라졌습니다.')
    print('선택 원문 DB 해시 확인 시작: '+str(database_path), flush=True)
    store_sha = file_sha(database_path)
    if store_sha != manifest['store_sha256']:
        raise ValueError('선택 원문 DB가 manifest의 store_sha256와 다릅니다.')
    db = sqlite3.connect(database_path.as_uri()+'?mode=ro', uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        result = compare(json.loads(package_raw), db)
        if reference is not None:
            documents = [dict(r) for r in db.execute(
                'SELECT document_id,name,source_artifact_sha256 FROM document ORDER BY name,document_id')]
            result['whole_inventory'] = compare_all(reference, documents)
            result['reference_binding'] = {k: v for k, v in reference.items() if k != 'documents'}
    finally:
        db.close()
    if any(signature(Path(p)) != sig for p, sig in before.items()):
        raise ValueError('진단 중 선택 자료가 변경됐습니다. 결과를 사용하지 않습니다.')
    return {'revision': VERSION, 'operation': 'READ_ONLY_DOCUMENT_IDENTITY_DIAGNOSIS',
            'code_root': str(root), 'generation': str(generation),
            'generation_id': manifest['generation_id'], 'generation_manifest_sha256': manifest_sha,
            'store_sha256_manifest_pin': manifest['store_sha256'],
            'store_hash_reverified_by_this_diagnosis': True, 'store_actual_sha256': store_sha,
            'serving_config_sha256': sha(config_raw), 'package_sha256': sha(package_raw),
            'python_executable': sys.executable, 'python_version': sys.version.split()[0],
            'package_built_against': json.loads(package_raw)['built_against'],
            'sqlite_query_only': True, 'registration_performed': False, 'model_calls': 0,
            **result}


def summary_lines(report):
    whole = report['whole_inventory']
    all_hash = whole['hash_counts_without_name']
    cm_hash = report['identity_counts_without_name']
    unique = lambda counts: counts.get('HASH_MATCH_SAME_NAME', 0)+counts.get('HASH_MATCH_DIFFERENT_NAME', 0)
    lines = [
        '전체: 기준 '+str(whole['reference_documents'])+'개 / 현장 '+str(whole['selected_documents'])+'개',
        '문서명 일치 '+str(whole['name_presence_count'])+'개 / 원본 SHA 일치 '+str(unique(all_hash))+
        '개 (이름만 다름 '+str(all_hash.get('HASH_MATCH_DIFFERENT_NAME', 0))+'개)',
        '기준 원본 미발견 '+str(all_hash.get('HASH_NOT_FOUND', 0))+'개 / 동일 SHA 중복 '+
        str(all_hash.get('HASH_AMBIGUOUS', 0))+'개 / 현장 추가·다른 원본 '+
        str(len(whole['selected_only_hash_documents']))+'개',
        'CM '+str(report['document_count'])+'문서: 이름+SHA 일치 '+str(report['counts'].get('EXACT', 0))+
        '개 / 이름 무시 SHA 일치 '+str(unique(cm_hash))+'개 / 미발견 '+
        str(cm_hash.get('HASH_NOT_FOUND', 0))+'개',
    ]
    kosdaq = next((r for r in report['documents'] if r['document_name'] == '코스닥시장 상장규정'), None)
    if kosdaq is not None:
        lines.append('코스닥시장 상장규정: 문서명 후보 '+str(len(kosdaq['name_matches']))+
                     '개 / 같은 원본 SHA 후보 '+str(len(kosdaq['hash_matches_without_name']))+'개')
    lines.append('전체 원본 SHA 목록 동일: '+str(whole['hash_inventory_equal_without_name']))
    return lines


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        raise ValueError('TRANSFER와 새 진단 출력 폴더, 고정된 기준 inventory가 필요합니다.')
    transfer, output = map(Path, args[:2])
    reference = json.loads(args[2])
    report = inspect(transfer, reference)
    output = output.resolve(strict=True)
    if output.parent != transfer.resolve(strict=True)/'cm-source-diag-r3':
        raise ValueError('진단 결과는 TRANSFER/cm-source-diag-r3에 저장해야 합니다.')
    target = output/'SOURCE_DIAGNOSIS.json'
    with target.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print('\n'.join(summary_lines(report)), flush=True)
    print('상세 결과='+str(target), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
