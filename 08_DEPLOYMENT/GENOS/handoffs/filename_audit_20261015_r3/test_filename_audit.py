import copy
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

    def test_output_inside_checkout_transfer_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); code = root / 'workspace'; cwd = code / 'TRANSFER'
            audit.validate_output(cwd / 'FILENAME_AUDIT_RESULTS/run1', root / 'generation', code, cwd)

    def test_output_external_transfer_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            audit.validate_output(root / 'TRANSFER/results', root / 'generation', root / 'DEV', root / 'TRANSFER')

    def test_output_inside_code_other_location_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); code = root / 'workspace'; cwd = code / 'TRANSFER'
            with self.assertRaisesRegex(ValueError, 'inside DEV'):
                audit.validate_output(code / '02_BACKEND/output', root / 'generation', code, cwd)

    def test_output_generation_still_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); generation = root / 'workspace/TRANSFER/FILENAME_AUDIT_RESULTS/generation'
            with self.assertRaisesRegex(ValueError, 'outside input'):
                audit.validate_output(generation / 'output', generation, root / 'workspace', root / 'workspace/TRANSFER')

    def test_output_report_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); code = root / 'workspace'; cwd = code / 'TRANSFER'; cwd.mkdir(parents=True)
            (cwd / 'FILENAME_AUDIT_RESULTS').symlink_to(code / '02_BACKEND', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                audit.validate_output(cwd / 'FILENAME_AUDIT_RESULTS/run1', root / 'generation', code, cwd)

    def test_output_nested_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); code = root / 'workspace'; cwd = code / 'TRANSFER'
            reports = cwd / 'FILENAME_AUDIT_RESULTS'; reports.mkdir(parents=True)
            (reports / 'escape').symlink_to(code / '02_BACKEND', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'inside DEV'):
                audit.validate_output(reports / 'escape/run1', root / 'generation', code, cwd)

    def test_output_symlink_dev_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); code = root / 'workspace'; code.mkdir()
            alias = root / 'DEV'; alias.symlink_to(code, target_is_directory=True)
            cwd = code / 'TRANSFER'
            audit.validate_output(cwd / 'FILENAME_AUDIT_RESULTS/run1', root / 'generation', alias, cwd)

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


class ExceptionTests(unittest.TestCase):
    def config(self):
        path = globals().get('EXCEPTIONS_PATH', HERE / 'FILENAME_EXCEPTIONS.json')
        return audit.load_exceptions(path)[0]

    def choose(self, names, config=None):
        events = []
        rows = [row(n, path='internal/family/' + n) for n in names]
        selected = audit.select(rows, config or self.config(), events)
        return {r['filename']: r for r in selected}, {e['rule_id']: e for e in events}

    def test_explicit_lending_date_overrides_ambiguous_family(self):
        names = ['대차업무준칙.docx', '대차업무준칙_2025.01.01.docx', '대차업무준칙_2026.05.04.docx']
        rows, events = self.choose(names)
        self.assertEqual([rows[n]['status'] for n in names], ['EXCLUDED', 'EXCLUDED', 'LATEST'])
        self.assertEqual(rows[names[2]]['date'], '2026-05-04')
        self.assertEqual(rows[names[2]]['before_exception_status'], 'REVIEW')
        self.assertEqual(events['stock-lending-20260504']['status'], 'APPLIED')

    def test_golden_month_exact_filename_no_invented_day(self):
        names = ['삼성POP골든랩 관리준칙_20250101.docx', '삼성POP골든랩 관리준칙_2023년 5월 개정(최종).gul.docx']
        rows, _ = self.choose(names)
        self.assertEqual(rows[names[0]]['status'], 'EXCLUDED')
        self.assertEqual((rows[names[1]]['status'], rows[names[1]]['date'], rows[names[1]]['date_precision']), ('LATEST', '2023-05', 'month'))

    def test_golden_wrong_final_not_silently_selected(self):
        name = '삼성POP골든랩 관리준칙_2023년 5월 개정(초안).docx'
        rows, events = self.choose([name])
        self.assertEqual(rows[name]['status'], 'REVIEW')
        self.assertEqual(events['samsung-pop-golden-wrap-202305']['status'], 'TARGET_NOT_FOUND')

    def test_attachment_numbers_independent_versions(self):
        base = '선물옵션 리스크관리 관리준칙'
        names = [base + '_20260101.docx', base + '_[별첨1]_20200101.docx', base + '_[별첨1]_20220101.docx', base + '_[별첨2]_20210101.docx']
        rows, events = self.choose(names)
        self.assertEqual([rows[n]['status'] for n in names], ['LATEST', 'OLDER', 'LATEST', 'LATEST'])
        self.assertEqual(len({r['title_key'] for r in rows.values()}), 3)
        self.assertEqual(rows[names[2]]['title'], base + ' [별첨1]')
        self.assertEqual(events['futures-options-attachments']['separate_document_keys'], 3)

    def test_attachment_folder_title_without_filename_title(self):
        names = ['[별첨1]_계좌별 한도_20200101.docx', '[별첨2]_계좌별 한도_20210101.docx']
        rows = audit.select([row(n, path='internal/07 선물옵션 리스크관리준칙/' + n) for n in names], self.config())
        self.assertEqual(len({r['title_key'] for r in rows}), 2)
        self.assertTrue(all(r['status'] == 'LATEST' for r in rows))

    def test_unnumbered_attachment_not_merged_with_body(self):
        names = ['선물옵션 리스크관리준칙_20260101', '선물옵션 리스크관리준칙_[별첨]_20250101']
        rows, events = self.choose(names)
        self.assertEqual(rows[names[1]]['status'], 'REVIEW')
        self.assertNotEqual(rows[names[0]]['title_key'], rows[names[1]]['title_key'])
        self.assertEqual(events['futures-options-attachments']['status'], 'ATTACHMENT_NUMBER_UNRESOLVED')

    def test_keep_both(self):
        names = ['위탁증거금 징수지침_20100101.doc', '위탁증거금 징수지침_20260101.doc']
        rows, events = self.choose(names)
        self.assertTrue(all(r['status'] == 'KEEP' and not r['physical_exclusion_candidate'] for r in rows.values()))
        self.assertEqual(events['margin-collection-keep-both']['status'], 'APPLIED')

    def test_keep_all_count_diff_reported(self):
        names = ['위탁증거금 징수지침_20100101', '위탁증거금 징수지침_20200101', '위탁증거금 징수지침_20260101']
        rows, events = self.choose(names)
        self.assertEqual(events['margin-collection-keep-both']['status'], 'APPLIED_COUNT_DIFFERS')
        self.assertTrue(all(r['status'] == 'KEEP' for r in rows.values()))

    def test_three_pinned_dates(self):
        for title, stamp in [('인덱스북', '20260529'), ('주식운용준칙', '20210723'), ('투자리스크관리준칙', '20160111')]:
            with self.subTest(title=title):
                names = [title + '_' + stamp, title + '_20270101']
                rows, _ = self.choose(names)
                self.assertEqual([rows[n]['status'] for n in names], ['LATEST', 'EXCLUDED'])

    def test_group_risk_existing_latest_unchanged(self):
        names = ['그룹위험관리 세칙_20200101', '그룹위험관리 세칙_20260101']
        rows, events = self.choose(names)
        self.assertEqual([rows[n]['status'] for n in names], ['OLDER', 'LATEST'])
        self.assertEqual(events['group-risk-confirm']['status'], 'CONFIRMED')

    def test_missing_target_preserves_family(self):
        rows, events = self.choose(['인덱스북_20260101', '인덱스북_20250101'])
        self.assertTrue(all(r['status'] == 'REVIEW' for r in rows.values()))
        self.assertEqual(events['index-book-20260529']['status'], 'TARGET_NOT_FOUND')

    def test_missing_document_explicitly_reported(self):
        _, events = self.choose(['모의규정_20260101'])
        self.assertEqual(events['index-book-20260529']['status'], 'DOCUMENT_NOT_FOUND')

    def test_single_file_folder_undated_latest(self):
        r = audit.select([row('무날짜규정.doc', path='internal/one/무날짜규정.doc')], self.config())[0]
        self.assertEqual((r['status'], r['date']), ('LATEST', ''))
        self.assertEqual(r['reason'], 'single_file_in_folder_user_rule')

    def test_one_per_folder_remains_latest_even_same_title(self):
        rows = [row('모의규정_20200101', path='internal/a/모의규정_20200101'), row('모의규정_20260101', path='internal/b/모의규정_20260101')]
        self.assertTrue(all(r['status'] == 'LATEST' for r in audit.select(rows, self.config())))

    def test_singleton_does_not_override_explicit_missing_target(self):
        r = audit.select([row('인덱스북_20200101', path='internal/one/인덱스북_20200101')], self.config())[0]
        self.assertEqual(r['status'], 'REVIEW')

    def test_singleton_no_folder_evidence_stays_review(self):
        r = audit.select([row('무날짜규정', filename_source='document_name')], self.config())[0]
        self.assertEqual(r['status'], 'REVIEW')

    def test_singleton_ignores_temporary_file(self):
        rows = [row('무날짜규정.doc', path='internal/a/무날짜규정.doc'), row('~$무날짜규정.doc', path='internal/a/~$무날짜규정.doc')]
        result = audit.select(rows, self.config())
        self.assertEqual({r['filename']: r['status'] for r in result}, {'무날짜규정.doc': 'LATEST', '~$무날짜규정.doc': 'TEMP'})

    def test_missing_original_cannot_be_overridden(self):
        rows = [row('주식운용준칙_20210723', path='internal/a/주식운용준칙_20210723', has_original=False)]
        events = []; selected = audit.select(rows, self.config(), events)
        self.assertEqual(selected[0]['status'], 'REVIEW')
        self.assertEqual(next(e for e in events if e['rule_id'] == 'equity-management-20210723')['status'], 'TARGET_HAS_NO_ORIGINAL')

    def test_rules_do_not_match_substring_other_title(self):
        rows, events = self.choose(['해외주식운용준칙_20210723', '해외주식운용준칙_20260101'])
        self.assertEqual(events['equity-management-20210723']['status'], 'DOCUMENT_NOT_FOUND')
        self.assertEqual(rows['해외주식운용준칙_20260101']['status'], 'LATEST')

    def test_disabling_exceptions_restores_normal_policy(self):
        rows = [row('인덱스북_20260529'), row('인덱스북_20270101')]
        with_exceptions = audit.select(rows, self.config())
        without = audit.select(rows)
        self.assertEqual(next(r for r in with_exceptions if r['date'] == '2026-05-29')['status'], 'LATEST')
        self.assertEqual(next(r for r in without if r['date'] == '2026-05-29')['status'], 'OLDER')

    def test_schema_unknown_action_rejected(self):
        config = self.config(); config['rules'][0]['action'] = 'guess'
        with self.assertRaisesRegex(ValueError, 'unknown exception action'): audit.validate_exceptions(config)

    def test_schema_duplicate_title_rejected(self):
        config = self.config(); r = copy.deepcopy(config['rules'][0]); r['id'] += '-duplicate'; config['rules'].append(r)
        with self.assertRaisesRegex(ValueError, 'conflicting exception titles'): audit.validate_exceptions(config)

    def test_invalid_user_date_rejected(self):
        config = self.config(); config['rules'][1]['date'] = '2026-02-30'
        with self.assertRaises(ValueError): audit.validate_exceptions(config)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.json'; p.write_text('{"revision":"a","revision":"b"}')
            with self.assertRaisesRegex(ValueError, 'duplicate'): audit.load_exceptions(p)

    def test_exception_report_and_month_in_csv(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); events = []
            rows = audit.select([row('삼성POP골든랩 관리준칙_2023년 5월 개정(최종).docx')], self.config(), events)
            result = audit.report(out, rows, {}, events)
            self.assertEqual(result['exception_changed_locations'], 1)
            self.assertIn('2023-05', (out / 'LATEST_ONLY.csv').read_text('utf-8-sig'))
            self.assertNotIn('2023-05-01', (out / 'LATEST_ONLY.csv').read_text('utf-8-sig'))
            self.assertIn('예외 적용 결과', (out / 'COMPARE.html').read_text())
            self.assertTrue((out / 'EXCEPTION_CHANGES.csv').exists())

    def test_missing_config_is_failure_not_silent_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / 'raw'; raw.mkdir(); (raw / '모의규정').touch()
            out = root / 'out'
            rc = audit.main(['compare', '--raw-root', str(raw), '--output', str(out)], default_exceptions_path=root / 'missing.json')
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads((out / 'RUN_STATUS.json').read_text())['status'], 'FAILED')
            self.assertFalse((out / 'COMPARE.html').exists())

    def test_no_exceptions_ignores_missing_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / 'raw'; raw.mkdir(); (raw / '모의규정').touch()
            out = root / 'out'
            self.assertEqual(audit.main(['compare', '--no-exceptions', '--raw-root', str(raw), '--output', str(out)], default_exceptions_path=root / 'missing.json'), 0)
            result = json.loads((out / 'SUMMARY.json').read_text())
            self.assertFalse(result['binding']['exceptions']['enabled'])

    def test_exceptions_preserve_shared_physical_document(self):
        rows = [row('인덱스북_20200101', did='shared', path='internal/a/인덱스북_20200101'),
                row('인덱스북_20260529', did='new', path='internal/a/인덱스북_20260529'),
                row('별도규정_20200101', did='shared', path='internal/b/별도규정_20200101')]
        selected = audit.select(rows, self.config())
        self.assertFalse(any(r['physical_exclusion_candidate'] for r in selected if r['document_id'] == 'shared'))

    def test_changed_config_during_inventory_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); raw = root / 'raw'; raw.mkdir(); (raw / '모의규정').touch()
            config = root / 'config.json'; config.write_text(json.dumps(self.config()))
            real_scan = audit.inventory_raw
            def changed(path):
                result = real_scan(path)
                config.write_text('{}')
                return result
            out = root / 'out'
            with patch.object(audit, 'inventory_raw', changed):
                self.assertEqual(audit.main(['compare', '--raw-root', str(raw), '--output', str(out), '--exceptions', str(config)]), 1)
            self.assertFalse((out / 'COMPARE.html').exists())
            self.assertEqual(json.loads((out / 'RUN_STATUS.json').read_text())['status'], 'FAILED')


if __name__ == '__main__': unittest.main()
