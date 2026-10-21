import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'genos_filename_audit.py'
if not SOURCE.exists(): SOURCE = HERE.parents[3] / '06_TOOLS/OFFLINE/genos_filename_audit.py'
spec = importlib.util.spec_from_file_location('filename_audit', SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def row(name, did=None, path=None, **kwargs):
    return {'filename': name, 'document_id': did or name, 'path': path or name, **kwargs}


def fixture(root, records=None):
    g = root / 'generation'
    g.mkdir()
    db = sqlite3.connect(g / 'store.sqlite')
    db.executescript('CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT,json TEXT); CREATE TABLE source_block(document_id TEXT);')
    if records is None:
        records = [('old', '모의규정(20200101).docx', 'internal'), ('new', '20260101_모의규정.docx', 'internal'), ('ext', '외부규정(20200101).xml', 'external')]
    for did, name, source in records:
        meta = {'source_category': source, 'relative_path': source + '/' + name}
        db.execute('INSERT INTO document VALUES(?,?,?,?)', (did, name, 'a' * 64, json.dumps({'document_metadata': meta})))
        db.execute('INSERT INTO source_block VALUES(?)', (did,))
    db.commit(); db.close()
    audit.write_json(g / 'manifest.json', {'schema_version': 'term-source-generation-v2', 'generation_id': 'fixture', 'store_sha256': audit.sha(g / 'store.sqlite')})
    return g


class FilenameTests(unittest.TestCase):
    def test_photo_risk_dates(self):
        for name, day in [('위험관리기준시행세칙(20240109)_clean.docx', '2024-01-09'), ('위험관리기준시행세칙(20240426)_전산반영.doc', '2024-04-26'), ('위험관리기준시행세칙(20260319).docx', '2026-03-19')]:
            with self.subTest(name=name):
                p = audit.parse_filename(name)
                self.assertEqual((p['title'], p['date'], p['parse_issues']), ('위험관리기준시행세칙', day, []))

    def test_photo_committee_annotations(self):
        for name in ['상품위원회운영지침(20140612).gul.doc', '상품위원회운영지침(20210423_고난도금융투자상품)', '상품위원회운영지침(20251205)_조직개편', '상품위원회운영지침(20250625)_CCO거부권']:
            with self.subTest(name=name): self.assertEqual(audit.parse_filename(name)['title'], '상품위원회운영지침')

    def test_photo_english_subtitle(self):
        a = audit.parse_filename('위기대응준칙(Contingency Plan)_20231121(직위수정).docx')
        self.assertEqual((a['title'], a['date']), ('위기대응준칙', '2023-11-21'))

    def test_photo_date_before_name(self):
        a = audit.parse_filename('20160823_위험관리시스템 운영준칙.gul.docx')
        b = audit.parse_filename('위험관리시스템운영준칙(20200117).docx')
        self.assertEqual(a['title_key'], b['title_key'])
        self.assertEqual(a['date'], '2016-08-23')

    def test_photo_voting(self):
        a = audit.parse_filename('20250401_보유주식의 의결권행사에 관한 지침.docx')
        self.assertEqual((a['title'], a['date']), ('보유주식의 의결권행사에 관한 지침', '2025-04-01'))

    def test_photo_attachment_family(self):
        names = ['업무위탁 운영지침_[별첨6] 중점관리 위탁계약 선정 기준_260320.docx', '업무위탁 운영지침_[별첨7] 수탁사 실사 체크리스트_260320.docx', '업무위탁 운영지침_[별첨8] 업무위탁 계약서 작성 체크리스트_260320.docx', '업무위탁 운영지침_260320.docx', '업무위탁 운영지침_업무위탁 운영기준_260320.docx']
        selected = audit.select([row(n) for n in names])
        self.assertEqual({r['title_key'] for r in selected}, {'업무위탁운영지침'})
        self.assertEqual({r['date'] for r in selected}, {'2026-03-20'})
        self.assertEqual([r['status'] for r in selected], ['LATEST'] * 5)

    def test_date_formats(self):
        for token in ['20260320', '260320', '2026.3.20', '2026-03-20', '2026_03_20', '2026년 3월 20일', '26.03.20', '2026/03/20']:
            for name in [token + '_모의규정.docx', '모의규정_' + token + '.docx']:
                with self.subTest(name=name): self.assertEqual(audit.parse_filename(name)['date'], '2026-03-20')

    def test_fixed_century(self):
        self.assertEqual(audit.parse_filename('모의규정_700101')['date'], '1970-01-01')
        self.assertEqual(audit.parse_filename('모의규정_690101')['date'], '2069-01-01')

    def test_leap_year(self):
        self.assertEqual(audit.parse_filename('모의규정_20240229')['date'], '2024-02-29')
        self.assertIn('invalid_date', audit.parse_filename('모의규정_20250229')['parse_issues'])

    def test_invalid_date_no_partial_match(self):
        for t in ['20261301', '20260010', '20260431', '202603201']:
            with self.subTest(t=t): self.assertEqual(audit.parse_filename('모의규정_' + t)['date'], '')

    def test_multiple_dates_review(self):
        a = audit.parse_filename('모의규정_20200101_20260101.docx')
        self.assertEqual(a['date_candidates'], ['2020-01-01', '2026-01-01'])
        self.assertIn('multiple_dates', a['parse_issues'])

    def test_repeated_date_is_one_date(self):
        self.assertEqual(audit.parse_filename('20260101_모의규정(20260101)')['date'], '2026-01-01')

    def test_temporary_does_not_win(self):
        r = audit.select([row('모의규정_20200101.doc'), row('~$모의규정_20260101.doc')])
        self.assertEqual({x['filename']: x['status'] for x in r}, {'모의규정_20200101.doc': 'LATEST', '~$모의규정_20260101.doc': 'TEMP'})

    def test_cross_folder_and_space(self):
        r = audit.select([row('모의 규정_20200101.doc', path='team1/a.doc'), row('20260101_모의규정.doc', path='team2/b.doc')])
        self.assertEqual([x['status'] for x in r], ['OLDER', 'LATEST'])
        self.assertTrue(all(x['cross_folder_family'] for x in r))

    def test_same_date_keeps_all_formats(self):
        r = audit.select([row('모의규정_20260101.doc'), row('모의규정_20260101.gul.doc'), row('모의규정_20260101.pdf')])
        self.assertTrue(all(x['status'] == 'LATEST' for x in r))

    def test_missing_date_blocks_family(self):
        r = audit.select([row('모의규정_20200101'), row('모의규정_20260101'), row('모의규정')])
        self.assertTrue(all(x['status'] == 'REVIEW' for x in r))

    def test_invalid_date_blocks_family(self):
        r = audit.select([row('모의규정_20200101'), row('모의규정_20261301')])
        self.assertTrue(all(x['status'] == 'REVIEW' for x in r))

    def test_rename_not_inferred(self):
        r = audit.select([row('리스크관리위원회운영준칙_20120227'), row('위험관리위원회운영준칙_20160823')])
        self.assertTrue(all(x['status'] == 'LATEST' for x in r))

    def test_shared_current_alias_protected(self):
        r = audit.select([row('모의규정_20200101', 'shared'), row('별도규정_20200101', 'shared'), row('모의규정_20260101', 'new')])
        self.assertTrue(all(not x['physical_exclusion_candidate'] for x in r if x['document_id'] == 'shared'))

    def test_external_alias_protected(self):
        r = audit.select([row('모의규정_20200101', protected_alias=True), row('모의규정_20260101')])
        self.assertFalse(r[0]['physical_exclusion_candidate'])

    def test_latest_without_source_protected(self):
        r = audit.select([row('모의규정_20200101', has_original=True), row('모의규정_20260101', has_original=False)])
        self.assertTrue(all(x['status'] == 'REVIEW' for x in r))

    def test_unicode_and_copy(self):
        self.assertEqual(audit.parse_filename('모의규정（２０２６０３２０）(1).DOCX')['date'], '2026-03-20')

    def test_known_prefix_annotation(self):
        self.assertEqual(audit.parse_filename('clean_20260101_모의규정.gul')['title'], '모의규정')

    def test_multiword_legal_suffix_preserved(self):
        self.assertEqual(audit.parse_filename('금융투자업규정 시행세칙_20260101.docx')['title'], '금융투자업규정 시행세칙')

    def test_whitespace_attachment_marker(self):
        self.assertEqual(audit.parse_filename('모의 운영지침 별첨6 선정 기준_20260101')['title'], '모의 운영지침')

    def test_no_empty_title(self):
        self.assertIn('missing_title', audit.parse_filename('20260101.docx')['parse_issues'])

    def test_csv_formula(self):
        self.assertEqual(audit.safe_cell('=HYPERLINK("bad")'), '\'=HYPERLINK("bad")')

    def test_generation_metadata_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); g = fixture(root)
            before = {p.name: audit.sha(p) for p in g.iterdir()}
            rows, binding = audit.inventory_generation(g)
            self.assertEqual(len(rows), 2)
            self.assertEqual(binding['external_locations_skipped'], 1)
            self.assertEqual([r['status'] for r in audit.select(rows)], ['OLDER', 'LATEST'])
            self.assertEqual(before, {p.name: audit.sha(p) for p in g.iterdir()})

    def test_wal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            g = fixture(Path(d)); (g / 'store.sqlite-wal').write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'WAL'): audit.inventory_generation(g)

    def test_malformed_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            g = fixture(Path(d)); db = sqlite3.connect(g / 'store.sqlite')
            db.execute("UPDATE document SET json='bad'"); db.commit(); db.close()
            with self.assertRaises(sqlite3.OperationalError): audit.inventory_generation(g)

    def test_unknown_classification_counted(self):
        with tempfile.TemporaryDirectory() as d:
            g = fixture(Path(d), [('a', '모의규정_20200101', 'internal'), ('b', '분류불명_20200101', '')])
            _, binding = audit.inventory_generation(g)
            self.assertEqual(binding['unknown_locations_skipped'], 1)

    def test_raw_no_body_read_and_empty_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaisesRegex(ValueError, 'no files'): audit.inventory_raw(root)
            (root / '모의규정_20200101.doc').write_bytes(b'invalid document bytes')
            self.assertEqual(len(audit.inventory_raw(root)[0]), 1)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'link').symlink_to('/tmp', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'): audit.inventory_raw(root)

    def test_html_escaped_and_two_column_csv(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rows = audit.select([row('<script>alert(1)</script>모의규정_20260101.docx')])
            audit.report(root, rows, {})
            text = (root / 'COMPARE.html').read_text()
            self.assertNotIn('<script>', text)
            self.assertIn('&lt;script&gt;', text)
            self.assertEqual((root / 'ALL_INTERNAL.csv').read_text('utf-8-sig').splitlines()[0], '문서명,날짜')

    def test_cli_raw_and_repeat_preserves_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / 'raw'; raw.mkdir()
            (raw / '모의규정_20200101.docx').touch(); (raw / '모의규정_20260101.docx').touch()
            out = root / 'out'
            self.assertEqual(audit.main(['compare', '--raw-root', str(raw), '--output', str(out)]), 0)
            self.assertEqual(json.loads((out / 'SUMMARY.json').read_text())['counts_by_location'], {'OLDER': 1, 'LATEST': 1})
            with self.assertRaises(FileExistsError): audit.main(['compare', '--raw-root', str(raw), '--output', str(out)])

    def test_cli_input_write_refused(self):
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d)
            self.assertEqual(audit.main(['compare', '--raw-root', str(raw), '--output', str(raw / 'out')]), 1)
            self.assertFalse((raw / 'out').exists())

    def test_fixed_binding_overrides_stale_env(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); g = fixture(root)
            code = root / 'DEV'; (code / '00_SYSTEM').mkdir(parents=True)
            audit.write_json(code / '00_SYSTEM/GENOS_SERVING_PATHS.json', {'schema_version': 'genos-serving-paths-v1', 'selection': 'operator-fixed', 'generation': str(g), 'runtime': str(root / 'runtime'), 'generation_manifest_sha256': audit.sha(g / 'manifest.json')})
            # During repository tests use the actual existing service/gate helpers.
            if not (SOURCE.parent / 'deployment_paths.py').exists():
                repo = SOURCE.parents[2]
                import shutil
                for rel in ('02_BACKEND/semantic_runtime/deployment_paths.py', '06_TOOLS/COMMANDS/genos_generation_e2e.py'):
                    target = code / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(repo / rel, target)
            with patch.dict(os.environ, {'GENOS_DATA_ROOT': '/missing/legacy/root', 'GENOS_GENERATION': '/missing/stale'}):
                selected, _ = audit.resolve_generation(code)
                self.assertEqual(selected, g)
                (g / 'manifest.json').write_text('{}')
                with self.assertRaises(ValueError): audit.resolve_generation(code)


if __name__ == '__main__': unittest.main()
