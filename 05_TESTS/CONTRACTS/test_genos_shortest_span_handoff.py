"""Patch backup/idempotence/rollback checks in a synthetic checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TXT = ROOT / '08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_SPAN_FIX_SHORTEST_R1_UTF8.txt'


def test_install_repeat_and_rollback(tmp_path):
    installer = TXT.read_text().split("<<'GENOS_SPAN_PATCH_PY'\n", 1)[1].split('\nGENOS_SPAN_PATCH_PY', 1)[0]
    originals = {
        '02_BACKEND/lawrag/core/ingest.py': 'def ingest(parsed):\n    blocks = Block.from_elements(parsed.elements)\n    return blocks\n',
        '02_BACKEND/lawrag/core/structure/model.py': 'class Block:\n    heading_level: Optional[int] = None\n    def dump(self):\n        d = {}\n        if self.heading_level is not None:\n            d["heading_level"] = self.heading_level\n        return d\n',
    }
    for relative, text in originals.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    data = tmp_path / 'data'
    data.mkdir()
    env = {**os.environ, 'GENOS_DATA_ROOT': str(data)}
    def run(*args):
        return subprocess.run([sys.executable, '-c', installer, *args], cwd=tmp_path,
                              env=env, check=True, capture_output=True, text=True).stdout
    assert 'SPAN_PATCH_APPLIED' in run()
    assert 'SPAN_PATCH_ALREADY_APPLIED' in run()
    receipt = next((tmp_path / 'TRANSFER/BACKUPS').glob('source-lines-r1/*/receipt.json'))
    assert len(json.loads(receipt.read_text())['files']) == 3
    module = tmp_path / '02_BACKEND/lawrag/core/structure/source_lines.py'
    assert module.read_bytes() == (ROOT / '02_BACKEND/lawrag/core/structure/source_lines.py').read_bytes()
    assert 'SPAN_PATCH_ROLLBACK_PASS' in run('--rollback', str(receipt))
    for relative, text in originals.items():
        assert (tmp_path / relative).read_text() == text
    assert not module.exists()
