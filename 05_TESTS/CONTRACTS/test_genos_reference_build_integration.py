"""Prepared reuse integration for the explicitly selected compact-v2 profile."""
import pytest
from test_genos_meaning_variants import prepared
from test_genos_prepared_serving_reuse import test_prepared_full_serving_reuse_preserves_inputs_and_resume as reuse_case


@pytest.mark.parametrize('granularity',['article','unit'])
def test_compact_v2_prepared_reuse_and_publish(prepared,tmp_path,monkeypatch,granularity):
    reuse_case(prepared,tmp_path,monkeypatch,granularity,'compact-v2')
