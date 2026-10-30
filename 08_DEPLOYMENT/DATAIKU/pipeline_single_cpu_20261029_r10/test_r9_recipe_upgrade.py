"""Verify the user's exact installed R9 Flow through the real SDK classes."""
import json
from pathlib import Path
from test_compute import env, test_published_sdk_installer_apply_repeat_rollback as check_upgrade


def test_exact_installed_r9_flow_updates_and_rolls_back(env, monkeypatch):
    reference = json.loads((env.dku / 'REFERENCE.json').read_text())
    old_bootstrap = (Path(__file__).parent.parent / 'pipeline_speed_20261028_r9/bootstrap.txt').read_text()
    assert reference['prior_compute_bootstraps'][-1] == old_bootstrap
    check_upgrade(env, monkeypatch, -1)
