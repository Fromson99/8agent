"""Run the exact sealed TXT on real local originals and differing metadata."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_CM_SOURCE_DIAG_20261007_R2'


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(4*1024*1024):
            value.update(chunk)
    return value.hexdigest()


def main():
    reference = json.loads((OUT/'REFERENCE_INVENTORY.json').read_bytes())
    source = ROOT/reference['generation_path']
    source_before = sha(source/'store.sqlite')
    transcripts, checks = [], []
    for synthetic in (False, True):
        with tempfile.TemporaryDirectory(prefix='cm-source-diag-r2-', dir=ROOT/'90_RUNTIME') as directory:
            prefix = Path(directory)
            transfer = prefix/'DEV/TRANSFER'
            artifacts = transfer/'cm-oneclick-r8'
            artifacts.mkdir(parents=True)
            generation = source
            if synthetic:
                generation = prefix/'generation'
                generation.mkdir()
                docs = reference['documents']
                with sqlite3.connect(generation/'store.sqlite') as db:
                    db.execute('CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT)')
                    db.executemany('INSERT INTO document VALUES(?,?,?)',
                                   [(d['document_id'], d['name'], d['source_artifact_sha256']) for d in docs])
                    db.execute('UPDATE document SET name=? WHERE name=?', ('현장 코스닥 표시명', '코스닥시장 상장규정'))
                    db.execute('UPDATE document SET source_artifact_sha256=? WHERE document_id=?', ('f'*64, docs[0]['document_id']))
                    db.execute('DELETE FROM document WHERE document_id=?', (docs[1]['document_id'],))
                    db.execute('INSERT INTO document VALUES(?,?,?)', ('duplicate', '다른 표시명의 중복 원본', docs[2]['source_artifact_sha256']))
                    db.execute('INSERT INTO document VALUES(?,?,?)', ('extra', '현장 추가 모의 문서', 'e'*64))
                (generation/'manifest.json').write_text(json.dumps(
                    {'generation_id': 'SYNTHETIC_FIELD_METADATA', 'store_sha256': sha(generation/'store.sqlite')}))
            config = {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed',
                      'generation': str(generation), 'generation_manifest_sha256': sha(generation/'manifest.json')}
            system = transfer.parent/'00_SYSTEM'
            system.mkdir()
            (system/'GENOS_SERVING_PATHS.json').write_text(json.dumps(config))
            (artifacts/'STATUS.json').write_text(json.dumps(config))
            package = ROOT/'08_DEPLOYMENT/GENOS/handoffs/cm_shortcut_common_20261007_r6/CM51_SOURCE_PACKAGE.json'
            (artifacts/'CM51_SOURCE_PACKAGE.json').write_bytes(package.read_bytes())
            run = transfer/(NAME+'_RUN.txt')
            run.write_bytes((OUT/run.name).read_bytes())
            watched = [system/'GENOS_SERVING_PATHS.json', artifacts/'STATUS.json',
                       artifacts/'CM51_SOURCE_PACKAGE.json', generation/'store.sqlite', generation/'manifest.json']
            before = {str(p): sha(p) for p in watched}
            env = {**os.environ, 'PATH': str(ROOT/'.venv/bin')+':'+os.environ['PATH']}
            for replay in range(1 if synthetic else 2):
                result = subprocess.run(['bash', str(run)], cwd=transfer.parent, env=env,
                                        capture_output=True, text=True, timeout=45)
                transcripts.append(result.stdout+result.stderr)
                assert result.returncode == 0, transcripts[-1]
                report_paths = list((transfer/'cm-source-diag-r2').glob('*/SOURCE_DIAGNOSIS.json'))
                assert len(report_paths) == replay+1
                report = max(report_paths, key=lambda p: p.stat().st_mtime_ns)
                value = json.loads(report.read_bytes())
                whole = value['whole_inventory']
                assert value['model_calls'] == 0 and not value['registration_performed']
                if synthetic:
                    assert whole['reference_documents'] == 159 and whole['selected_documents'] == 160
                    assert not whole['hash_inventory_equal_without_name']
                    assert len(whole['selected_only_hash_documents']) == 2
                    assert len(whole['selected_duplicate_hash_groups']) == 1
                    renamed = next(r for r in whole['documents'] if r['document_name'] == '코스닥시장 상장규정')
                    assert renamed['identity_classification'] == 'HASH_MATCH_DIFFERENT_NAME'
                    assert renamed['classification'] == 'NAME_MISSING'
                else:
                    assert value['counts'] == {'EXACT': 21}
                    assert whole['hash_inventory_equal_without_name'] and whole['name_and_hash_inventory_equal']
                    assert whole['hash_counts_without_name'] == {'HASH_MATCH_SAME_NAME': 159}
                assert before == {str(p): sha(p) for p in watched}
            checks.append({'fixture': 'SYNTHETIC_FIELD_METADATA' if synthetic else 'REAL_LOCAL_PUBLIC_SOURCE',
                           'complete_TXT_runs': 1 if synthetic else 2,
                           'original_records_and_store_unchanged': True,
                           'name_hash_and_bidirectional_comparison': True})
            if synthetic:
                (generation/'manifest.json').write_text('{"generation_id":"changed after R8"}')
                result = subprocess.run(['bash', str(run)], cwd=transfer.parent, env=env,
                                        capture_output=True, text=True, timeout=45)
                transcripts.append(result.stdout+result.stderr)
                assert result.returncode != 0 and 'manifest' in result.stdout
                assert len(list((transfer/'cm-source-diag-r2').glob('*/SOURCE_DIAGNOSIS.json'))) == 1
                checks.append({'changed_binding_final_TXT_rejected': True, 'failed_log_preserved': True})
    assert sha(source/'store.sqlite') == source_before
    validation = {'contract_tests': 11, 'exact_final_TXT': checks, 'reference_documents': 159,
                  'model_calls': 0, 'registration_performed': False, 'GENOS_field_verified': False,
                  'real_remote_push': False, 'email_sent': False}
    (OUT/'VALIDATION.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2)+'\n')
    (OUT/'DELIVERY_TESTS.log.gz').write_bytes(gzip.compress('\n'.join(transcripts).encode(), mtime=0))
    print('VALIDATED 11 contracts, 3 complete TXT runs, 1 changed-binding rejection; model_calls=0')


if __name__ == '__main__':
    main()
