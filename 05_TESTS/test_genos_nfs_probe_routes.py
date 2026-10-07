"""NFS gateway bypasses RAG/AD initialization; all paths use a local fixture."""
import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '02_BACKEND'))


class RouteContracts(unittest.TestCase):
    def entry(self, path, name):
        spec = importlib.util.spec_from_file_location(name, path)
        entry = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'AD_WORKER_ENABLED': '0', 'GENOS_AUTO_WARMUP': '0'}):
            spec.loader.exec_module(entry)
        return entry

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        target = self.root / '02_BACKEND/semantic_runtime/nfs_data_probe.py'
        target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / '02_BACKEND/semantic_runtime/nfs_data_probe.py', target)

    def test_root_gateway_avoids_ad_and_application_even_when_config_missing(self):
        entry = self.entry(ROOT / 'service.py', '_test_nfs_root_route')
        with patch.object(entry, '_ROOT', self.root), patch.object(entry, '_ad_control', side_effect=AssertionError('AD must not start')):
            out = asyncio.run(entry.service({}, {'API_TYPE': 'NFS_DATA_PROBE'}))
        self.assertEqual(out['status'], 503)
        self.assertEqual(out['body']['response_schema'], 'nfs-data-probe-20261006-r1')
        self.assertIsNone(entry._APP)
        self.assertFalse((self.root / '90_RUNTIME').exists())

    def test_stream_json_entry_avoids_backend_bootstrap(self):
        entry = self.entry(ROOT / '08_DEPLOYMENT/GENOS/stream_app.py', '_test_nfs_stream_route')
        with patch.object(entry, 'ROOT', self.root), patch.object(entry.importlib, 'import_module', side_effect=AssertionError('RAG backend must not import')):
            out = asyncio.run(entry.service({}, {'API_TYPE': 'NFS_DATA_PROBE'}))
        self.assertEqual(out['status'], 503)
        self.assertEqual(out['body']['stage'], 'code-serving')
        self.assertFalse((self.root / '90_RUNTIME').exists())


if __name__ == '__main__':
    unittest.main()
