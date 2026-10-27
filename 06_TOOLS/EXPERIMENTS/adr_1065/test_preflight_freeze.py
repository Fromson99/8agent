"""Small file/hash proof contracts; never opens SQLite or runtime/model code."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import freeze_run as freeze
from common import canonical_digest as digest, sha


class FrozenPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.art=self.root/'art';self.art.mkdir();self.cand=self.root/'candidate'
        self.code=self.cand/'revisions/rev-001/snapshot'
        self.files={}
        for name in ('02_BACKEND/example.py','00_SYSTEM/example.json','05_TESTS/test_example.py'):
            p=self.code/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
            self.files[name]=sha(p)
        self.order=[{'ordinal':i+1,'case_id':c,'arm':a} for i,(c,a) in enumerate([
            (c,a) for c,arms in [('fsc-hard-005',('A0','A1','A2')),('cm-023',('A1','A2','A0')),('fsc-hard-008',('A2','A0','A1'))] for a in arms])]
        tool_names=['06_TOOLS/EXPERIMENTS/adr_1065/preflight_replay.py',
                    '06_TOOLS/EXPERIMENTS/adr_1065/common.py','06_TOOLS/EXPERIMENTS/adr_1063/replay_catalogue.py']
        tool_files={}
        for name in tool_names:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic proof tool')
            tool_files[name]=sha(p)
        self.proof={'schema_version':'task-local-saved-failure-preview-v1','code_root':str(self.code.relative_to(self.root)),
                    'files':{p:h for p,h in self.files.items() if not p.startswith('05_TESTS/')},
                    'calls':0,'source_database_loads':0,'original_wire_reconstruction_claimed':False,
                    'all_within_mode_budget':True,'tool_files':tool_files,
                    'helper_path':tool_names[-1],'helper_sha256':tool_files[tool_names[-1]],'cells':[]}
        for c in self.order:
            name=f"{c['ordinal']:03d}-{c['case_id']}-{c['arm']}"
            cell=self.root/'04_EXPERIMENTS/ADR/ADR-1063-ontology-mvp-catalogue-projection/artifacts/matrix'/name
            input_names=['runtime/legal-agent/runs/x/y/journal.sqlite','runtime/case-memory/cases-v4.sqlite',
                         'effective-profile.json','model/call-001-service/request.json']
            sources={}
            for file in input_names:
                p=cell/file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic historical input')
                sources[str(p.relative_to(self.root))]=sha(p)
            payload={'messages':[{'role':'user','content':'synthetic candidate'}]}
            raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            out=self.art/(freeze.PREFLIGHT_STEM+'-requests')/(name+'.json.gz');out.parent.mkdir(exist_ok=True)
            out.write_bytes(gzip.compress(raw,mtime=0))
            self.proof['cells'].append({'cell':name,'current_originals_exact':True,
                'original_request_reconstructed':False,'calls':0,'source_database_loads':0,
                'source_inputs':sources,'source_journal_sha256':sources[str((cell/input_names[0]).relative_to(self.root))],
                'candidate_request_sha256':hashlib.sha256(raw).hexdigest(),
                'candidate_prepared':{'contract':'execution-review-input-modes-v1','input_mode':'CATALOGUE',
                    'status':'WITHIN_BUDGET','measured_chars':len(raw.decode()),'mode_limit_chars':24000,
                    'outer_limit_chars':100000,'max_context_chars':24000,'physical_attempt_reserved':False,
                    'model_delivery_claimed':False,'request_sha256':digest(payload)}})
        self.path=self.art/(freeze.PREFLIGHT_STEM+'.json')
    def tearDown(self):self.tmp.cleanup()
    def verify(self):
        self.path.write_text(json.dumps(self.proof))
        with patch.multiple(freeze,ROOT=self.root,ART=self.art,CAND=self.cand):
            return freeze.verify_preflight(self.code,self.files,self.order)
    def test_exact_frozen_nine_cell_proof_binds_all_inputs_and_requests(self):
        result=self.verify()
        self.assertEqual(len(result['cells']),9)
        self.assertEqual(len(result['dependencies']),49)
        self.assertEqual(result['calls'],0)
    def test_snapshot_preview_cannot_stand_in_for_frozen_root(self):
        self.proof['code_root']='candidate/snapshot'
        with self.assertRaisesRegex(ValueError,'frozen root'):self.verify()
    def test_changed_runtime_file_map_is_rejected(self):
        self.proof['files']['02_BACKEND/example.py']='0'*64
        with self.assertRaisesRegex(ValueError,'file map'):self.verify()
    def test_changed_replay_tool_is_rejected(self):
        self.proof['tool_files']['06_TOOLS/EXPERIMENTS/adr_1065/preflight_replay.py']='0'*64
        with self.assertRaisesRegex(ValueError,'tool map'):self.verify()
    def test_duplicate_or_missing_cell_is_rejected(self):
        self.proof['cells'][-1]=self.proof['cells'][0]
        with self.assertRaisesRegex(ValueError,'cells/order'):self.verify()
    def test_original_or_budget_unknown_never_passes(self):
        for field,value in [('current_originals_exact',False),('calls',False),('source_database_loads',1)]:
            previous=self.proof['cells'][0][field];self.proof['cells'][0][field]=value
            with self.assertRaises(ValueError):self.verify()
            self.proof['cells'][0][field]=previous
        self.proof['cells'][0]['candidate_prepared']['status']='EXCEEDED'
        with self.assertRaisesRegex(ValueError,'budget'):self.verify()
    def test_source_checkpoint_change_is_rejected(self):
        name=next(p for p in self.proof['cells'][0]['source_inputs'] if p.endswith('cases-v4.sqlite'))
        (self.root/name).write_text('changed checkpoint')
        with self.assertRaisesRegex(ValueError,'source inputs'):self.verify()
    def add_wal(self, content=b'completed historical WAL', *, registered=True):
        row=self.proof['cells'][0]
        journal=next(p for p in row['source_inputs'] if p.endswith('/journal.sqlite'))
        wal=self.root/(journal+'-wal');wal.write_bytes(content)
        if registered: row['source_inputs'][str(wal.relative_to(self.root))]=sha(wal)
        return wal
    def test_hash_bound_nonempty_historical_wal_is_preserved(self):
        wal=self.add_wal();before=wal.read_bytes()
        result=self.verify()
        self.assertEqual(result['dependencies'][str(wal.relative_to(self.root))],sha(wal))
        self.assertEqual(len(result['dependencies']),50)
        self.assertEqual(wal.read_bytes(),before)
    def test_unregistered_nonempty_wal_is_rejected(self):
        self.add_wal(registered=False)
        with self.assertRaisesRegex(ValueError,'source inputs'):self.verify()
    def test_changed_historical_wal_is_rejected(self):
        wal=self.add_wal();wal.write_bytes(b'changed WAL')
        with self.assertRaisesRegex(ValueError,'source inputs'):self.verify()
    def test_existing_empty_wal_is_also_hash_bound(self):
        wal=self.add_wal(b'')
        result=self.verify()
        self.assertEqual(result['dependencies'][str(wal.relative_to(self.root))],sha(wal))
    def test_saved_candidate_request_change_is_rejected(self):
        name=self.proof['cells'][0]['cell'];p=self.art/(freeze.PREFLIGHT_STEM+'-requests')/(name+'.json.gz')
        p.write_bytes(gzip.compress(b'{}'))
        with self.assertRaisesRegex(ValueError,'request hash'):self.verify()
    def test_size_only_claim_without_matching_request_hash_is_rejected(self):
        self.proof['cells'][0]['candidate_prepared']['request_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'measured candidate request'):self.verify()

if __name__=='__main__':unittest.main()
