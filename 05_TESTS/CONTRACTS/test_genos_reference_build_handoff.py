"""Exercise the shipped TXT on known v6 R4 and compact R2 predecessor bytes."""
from pathlib import Path
import zipfile
import pytest
import test_genos_compact_handoff as cases
import package_genos_reference_build as package


@pytest.mark.parametrize('predecessor',['v6-r4','compact-r2'])
def test_shipped_patch_apply_resume_gate_and_rollback(tmp_path,monkeypatch,predecessor):
    if predecessor=='compact-r2':
        with zipfile.ZipFile(package.BASE.parent/'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.zip') as z:
            files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
        with zipfile.ZipFile(package.previous.OUT/(package.previous.STEM+'.zip')) as z:
            files.update({n:z.read(n) for n in z.namelist() if not n.endswith('/')})
        folder=tmp_path/'predecessor';folder.mkdir()
        with zipfile.ZipFile(folder/'GENOS_UNIFIED_V6_CUMULATIVE_20261002_R4.zip','w') as z:
            for name,data in files.items():z.writestr(name,data)
        monkeypatch.setattr(package,'BASE',folder/'CODE_MANIFEST.json')
    monkeypatch.setattr(cases,'package',package)
    cases.test_field_patch_script_apply_idempotence_dependencies_and_rollback(tmp_path)
