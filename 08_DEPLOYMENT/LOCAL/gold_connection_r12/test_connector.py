"""Small boundary contracts for the new adapter only; no Oracle/model calls."""
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT/'08_DEPLOYMENT/RELEASES/accepted-answer-20261029-r1/code/02_BACKEND'))
from gold_connection import GoldConfig, GoldError, identifier, rewrite_reads, unique_json


def test_parameters_produce_exact_r12_shape_and_variants():
    for variant in ('b03', 'b05'):
        config = GoldConfig.load(HERE/('config_'+variant+'.json'), ROOT)
        statements = config.ddl()
        assert sum(s.startswith('CREATE TABLE') for s in statements) == 13
        assert sum(s.startswith('CREATE INDEX') for s in statements) == 11
        assert 'VECTOR(*,FLOAT32)' in '\n'.join(statements)
        assert 'IDD_'+variant.upper()+'_LGL_DOC_VER' in config.table('DOC_VER')


def test_rewriter_preserves_oracle_syntax_literals_comments_and_binds():
    config = GoldConfig.load(HERE/'config_b03.json', ROOT)
    text = ("SELECT 'SIDDA.LEGAL_RAG_QUERY_ROW_A' AS literal,r.ROW_ID FROM SIDDA.LEGAL_RAG_QUERY_ROW_A r "
            "WHERE r.DOCUMENT_ID IN (SELECT j.did FROM JSON_TABLE(:d,'$[*]' "
            "COLUMNS(did VARCHAR2(512) PATH '$' ERROR ON ERROR)) j) -- SIDDA.LEGAL_RAG_QUERY_ROW_A\n")
    result = rewrite_reads(text, config)
    assert "'SIDDA.LEGAL_RAG_QUERY_ROW_A' AS literal" in result
    assert "PATH '$' ERROR ON ERROR" in result
    assert ':d' in result and result.endswith('-- SIDDA.LEGAL_RAG_QUERY_ROW_A\n')
    assert 'FROM '+config.table('SRCH_ROW') in result
    assert rewrite_reads(result, config) == result


@pytest.mark.parametrize('owner', ['X.Y', 'A;DROP USER B', 'lowercase', '', 'A'*31])
def test_identifiers_are_not_sql_parameters(owner):
    with pytest.raises(GoldError, match='IDENTIFIER'):
        identifier(owner)


def test_duplicate_json_and_nonfinite_numbers_rejected():
    for text in ('{"a":1,"a":2}', '{"a":NaN}'):
        with pytest.raises(GoldError):
            unique_json(text)


def test_unknown_agent_or_asset_port_has_no_gold_fallback():
    config = GoldConfig.load(HERE/'config_b03.json', ROOT)
    for key in ('query_state', 'asset_part'):
        with pytest.raises(GoldError, match='UNSUPPORTED_PORT'):
            config.names(key)


def test_model_hash_mismatch_rejected(tmp_path):
    value = json.loads((HERE/'config_b03.json').read_text())
    value['model_sha256'] = '0'*64
    path = tmp_path/'config.json'
    path.write_text(json.dumps(value))
    with pytest.raises(GoldError, match='MODEL_HASH'):
        GoldConfig.load(path, ROOT)


def test_legacy_flag_conversion_preserves_null_and_exposes_invalid_values():
    config = GoldConfig.load(HERE/'config_b03.json', ROOT)
    projection = config.names('block_payload').table
    assert "='Y' THEN 1" in projection and "='N' THEN 0" in projection
    assert 'IS NULL THEN NULL' in projection and 'ELSE 2 END' in projection
