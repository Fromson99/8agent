import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import capacity as c

HERE=Path(__file__).parent
CONTRACT=c.read_json(HERE/'target_contract.json')


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.root=self.base/'generation';self.root.mkdir()
        self.config=dict(generation=str(self.root),scan_root='',source_mode='RESTORED_COPY',output=str(self.base/'output'),
                         descriptor='',full_state='',sample_rows=4,sample_seconds=3,dbstat_seconds=5)

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self):
        p=self.root/'asset.sqlite'
        db=sqlite3.connect(p)
        db.executescript('''CREATE TABLE normal(id INTEGER PRIMARY KEY, text TEXT);
CREATE INDEX ix ON normal(text);
CREATE TABLE wr(k TEXT PRIMARY KEY,v TEXT) WITHOUT ROWID;
CREATE VIEW expanded AS SELECT a.id,a.text,b.k FROM normal a CROSS JOIN wr b;
CREATE VIRTUAL TABLE words USING fts5(body);''')
        db.executemany('INSERT INTO normal VALUES(?,?)',[(i,'가나다 😀'*30) for i in range(30)])
        db.executemany('INSERT INTO wr VALUES(?,?)',[(str(i),'payload'*80) for i in range(100)])
        db.execute("INSERT INTO words VALUES('alpha beta beta')")
        db.commit();db.close()
        return p

    def test_physical_reconciliation_no_view_or_fts_double_count(self):
        p=self.fixture();before=c.file_sha(p)
        r=c.inspect_database(p,'asset.sqlite',self.config,{},CONTRACT)
        tables={x['table']:x for x in r['tables']}
        self.assertEqual(tables['normal']['physical_rows'],30)
        self.assertEqual(tables['wr']['physical_rows'],100)
        self.assertEqual(tables['expanded']['table_and_index_bytes'],0)
        self.assertGreater(tables['words']['table_and_index_bytes'],0)
        self.assertNotIn('words_data',tables)
        self.assertEqual(sum(t['table_and_index_bytes'] for t in tables.values())+r['schema_bytes'],r['btree_bytes'])
        self.assertEqual(r['btree_bytes']+r['freelist_bytes']+r['other_bytes'],p.stat().st_size)
        self.assertEqual(before,c.file_sha(p))

    def test_blob_and_canonical_projection(self):
        value=c.query_value(dict(response=b'\x00\xff',id='one'),'source_request')
        self.assertEqual(value['response'],'AP8=')
        with self.assertRaises(ValueError):c.query_value(dict(data=b'x'),'other')
        row=c.mapped_query(dict(id='한글',document_id='d'),'t','asset_a.t')
        self.assertIn('한글',row['SRCH_DATA_CTNT'])
        cost=c.row_cost(row,CONTRACT['tables']['SRCH_ROW'],c.SCENARIOS['B'])
        self.assertGreater(cost['index'],0)
        self.assertAlmostEqual(cost['total'],cost['heap']+cost['lob']+cost['index'])

    def test_manifest_validation_and_changed_data(self):
        p=self.fixture()
        d=dict(binding={},paths={'asset.sqlite':c.file_sha(p)},tables={'asset_one.normal':dict(asset='asset.sqlite',table='normal',rows=30)})
        descriptor=self.base/'descriptor.json';c.save_json(descriptor,dict(d,checksum=c.digest(d)))
        self.config['descriptor']=str(descriptor)
        before=c.file_sha(p)
        result=c.run(self.config,CONTRACT)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertIsNone(result['nfs_physical_allocated_bytes'])
        self.assertEqual(before,c.file_sha(p))
        items=result['oracle_tables']
        original=next(x for x in items if x['policy']=='ORIGINAL' and x['target'].endswith('SRCH_ROW_S_1'))
        self.assertEqual(original['rows'],30)
        self.assertEqual(original['sampled_plan_rows'],30)
        self.assertGreater(original['C_total_bytes'],original['B_total_bytes'])
        # Resume reuses only measured databases with identical signatures/configuration.
        c.run(self.config,CONTRACT)
        db=sqlite3.connect(p);db.execute("INSERT INTO normal VALUES(40,'new')");db.commit();db.close()
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):c.run(self.config,CONTRACT)

    def test_unknown_kind_is_assumption_not_zero(self):
        p=self.fixture()
        d=dict(binding={},paths={'asset.sqlite':c.file_sha(p)},tables={'native.special':dict(asset='asset.sqlite',rows=125)})
        descriptor=self.base/'descriptor.json';c.save_json(descriptor,dict(d,checksum=c.digest(d)))
        self.config['descriptor']=str(descriptor)
        result=c.run(self.config,CONTRACT)
        r=next(r for r in result['oracle_tables'] if r['policy']=='ORIGINAL' and 'SRCH_ROW' in r['target'])
        self.assertEqual(r['assumed_plan_rows'],125)
        self.assertEqual(r['sampled_plan_rows'],0)
        self.assertGreater(r['B_total_bytes'],0)
        self.assertIsNone(result['oracle_full_database_total_bytes'])

    def test_sources_and_reduced_policy(self):
        p=self.root/'store.sqlite';db=sqlite3.connect(p)
        db.execute('CREATE TABLE document(document_id TEXT,name TEXT,source_artifact_sha256 TEXT,json TEXT)')
        db.execute('INSERT INTO document VALUES(?,?,?,?)',('d','문서','a'*64,'{}'));db.commit();db.close()
        r=c.inspect_database(p,'store.sqlite',self.config,{},CONTRACT)
        self.assertEqual(r['estimates'][0]['target'],'DOC_VER')
        self.assertEqual(r['estimates'][0]['rows'],1)
        self.assertGreater(r['estimates'][0]['B_total_bytes'],0)

    def test_safety_scope_timeout_and_sql_readonly(self):
        p=self.fixture()
        db=c.db_open(p)
        with self.assertRaises(sqlite3.OperationalError):db.execute("DELETE FROM normal")
        with self.assertRaises(sqlite3.OperationalError):
            c.query(db,'WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n',.001)
        db.close()
        self.config['output']=str(self.root/'bad-output')
        with self.assertRaisesRegex(ValueError,'OUTSIDE_SOURCE'):c.run(self.config,CONTRACT)
        with self.assertRaises(ValueError):c.safe_path(self.root,'../')
        import oracle_queries
        self.assertTrue(all(s.lstrip().startswith(('SELECT','WITH')) for s in oracle_queries.SQL.values()))

    def test_hardlinks_and_symlinks(self):
        import os
        p=self.fixture();os.link(p,self.root/'alias.db');(self.root/'link.db').symlink_to(p)
        files,skipped=c.inventory(self.root)
        self.assertEqual(sum(f['unique_bytes'] for f in files),p.stat().st_size)
        self.assertEqual(sum(f['bytes'] for f in files),2*p.stat().st_size)
        self.assertTrue(any(x['reason']=='SYMLINK_FILE' for x in skipped))

    def test_complete_notebook_launcher_and_sql_failure(self):
        import contextlib
        import io
        import os
        import sys
        import types
        from unittest.mock import patch
        self.fixture()
        archive=HERE/'DATAIKU_NFS_TABLE_CAPACITY_20261103_R1.zip'
        class Folder:
            def __init__(self,name):self.name=name
            def list_paths_in_partition(self):return ['/'+archive.name]
            def get_download_stream(self,path):return io.BytesIO(archive.read_bytes())
        dataiku=types.ModuleType('dataiku');dataiku.Folder=Folder;dataiku.get_custom_variables=lambda:{}
        ipython=types.ModuleType('IPython.display');ipython.display=lambda *a:None;ipython.FileLink=lambda p:p
        script=(HERE/'DATAIKU_NFS_TABLE_CAPACITY_RUN_R1.txt').read_text()
        script=script.replace("GENERATION_DIR = ''",'GENERATION_DIR = '+repr(str(self.root)))
        script=script.replace("OUTPUT_DIR = ''",'OUTPUT_DIR = '+repr(str(self.base/'notebook-output')))
        before=c.file_sha(self.root/'asset.sqlite')
        with patch.dict(sys.modules,{'dataiku':dataiku,'IPython.display':ipython}),contextlib.redirect_stdout(io.StringIO()):
            exec(compile(script,'<full-notebook-cell>','exec'),{})
        self.assertEqual(before,c.file_sha(self.root/'asset.sqlite'))
        self.assertTrue((self.base/'notebook-output'/'RESULTS.zip').exists())
        import oracle_queries
        def denied(sql):raise RuntimeError('ORA-00942: table or view does not exist')
        with contextlib.redirect_stdout(io.StringIO()):
            report=oracle_queries.run(denied,self.base/'oracle-denied')
        self.assertEqual(len(report),9)
        self.assertTrue(all(r['status']=='UNAVAILABLE' and r['oracle_codes']==['ORA-00942'] for r in report.values()))

    def test_reduced_three_table_scenario_uses_manifest_paths(self):
        c.save_json(self.root/'manifest.json',dict(navigation={'path':'nav'},glossary={'dictionary':'glossary/dict.sqlite'}))
        kinds={'asset_x.occurrence_keys':dict(asset='nav/navigation.sqlite',table='occurrence_keys',rows=10),
               'asset_x.occurrence':dict(asset='nav/navigation.sqlite',table='occurrence',rows=20),
               'asset_x.entry_corpus_link':dict(asset='glossary/dict.sqlite',table='entry_corpus_link',rows=30)}
        result=dict(databases={},files=[],notes=[],forecast_input_validated=True)
        output=self.base/'policy';output.mkdir()
        c.export_reports(result,output,CONTRACT,kinds,self.root)
        original=next(r for r in result['oracle_tables'] if r['policy']=='ORIGINAL' and 'SRCH_ROW' in r['target'])
        reduced=next(r for r in result['oracle_tables'] if r['policy'].startswith('REDUCED') and 'SRCH_ROW' in r['target'])
        self.assertEqual(original['rows'],60)
        self.assertEqual(reduced['rows'],20)


if __name__=='__main__':unittest.main()
