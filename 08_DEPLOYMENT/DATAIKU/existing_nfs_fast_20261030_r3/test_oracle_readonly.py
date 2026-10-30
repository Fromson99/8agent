"""Read-only Oracle syntax/Unicode contracts, using synthetic inline CLOBs only."""
import importlib.util
import csv
import io as streams
import json
from pathlib import Path
import subprocess

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('packaged_batch_contract', HERE/'test_batch_read.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
io, DataikuClient, render = package.io, package.DataikuClient, package.render


@pytest.mark.parametrize('value,count', [(('가'*999+'😀'+"'\r\n ")*5, 1),
    (('가'*999+'😀'+"'\r\n ")*5, 20), ('', 1), (None, 1)], ids=['unicode', '32-pieces', 'empty', 'null'])
def test_real_oracle_batched_sql_and_utf16(tmp_path, value, count):
    import pandas as pd
    # Inspect only identity/ports; no credentials or container environment in output.
    meta = json.loads(subprocess.check_output(['docker', 'inspect', 'a8-legal-mapped-20261023']))[0]
    assert meta['Config']['Labels']['a8.task'] == 'legal-mapped-20261023'
    assert meta['NetworkSettings']['Ports']['1521/tcp'] == [{'HostIp':'127.0.0.1','HostPort':'11524'}]
    row = package.expected_rows(1)[0]
    row.update(TEXT=value, SOURCE_JSON=value)
    from lawrag.pipeline.oracle_query_dataiku import literal
    def expression(col):
        value = row[col]
        if value is None: return 'TO_CLOB(CAST(NULL AS VARCHAR2(1)))' if col in io.CLOBS else 'NULL'
        if col not in io.CLOBS: return literal(value)
        if value == '': return 'EMPTY_CLOB()'
        return ' || '.join('TO_CLOB('+literal(value[n:n+900]).replace('\r', "' || CHR(13) || '").replace('\n', "' || CHR(10) || '")+')' for n in range(0,len(value),900))
    inline = 'SELECT '+','.join(("LPAD(TO_CHAR(LEVEL-1),4,'0')" if c == 'BLOCK_ID' else expression(c))+' AS '+c for c in io.COLUMNS['block_payload'])+' FROM DUAL CONNECT BY LEVEL<='+str(count)
    executed = []
    class Executor:
        def query_to_df(self, text, *, infer_from_schema, parse_dates):
            assert infer_from_schema and not parse_dates
            assert text.startswith('SELECT ') and not any(x in text for x in ['INSERT ', 'UPDATE ', 'DELETE ', 'COMMIT'])
            text = 'WITH synthetic_rows AS ('+inline+') '+text.replace('SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A', 'synthetic_rows')
            executed.append(text)
            # SQL*Plus has an input-line limit; split only fixture SQL operators.
            text = text.replace(' || ', ' ||\n').replace(' UNION ALL ', '\nUNION ALL\n').replace(' WHERE ', '\nWHERE ').replace(' OR ', '\nOR ')
            script = ('whenever sqlerror exit failure\nset define off\nset sqlblanklines on\n'
                      'set feedback off\nset pagesize 50000\nset linesize 32767\n'
                      'set markup csv on quote on\n'+text+';\nexit\n')
            result = subprocess.run(['docker','exec','-i','-u','oracle','-e','NLS_LANG=.AL32UTF8',
                'a8-legal-mapped-20261023','sqlplus','-s','/ as sysdba'], input=script.encode(),
                capture_output=True, timeout=30)
            output = result.stdout.decode()
            if result.returncode:
                (tmp_path/'oracle-error.txt').write_bytes(result.stdout + result.stderr)
                print('\n'.join(line for line in output.splitlines() if line.startswith(('ORA-', 'PLS-'))))
            assert result.returncode == 0, output + result.stderr.decode()
            records = list(csv.DictReader(streams.StringIO(output.strip())))
            for record in records:
                for key, item in record.items():
                    record[key] = None if item == '' else int(item) if key.endswith('__TOTAL') or key in ('TOTAL','CLOB_SLOT','JSON_TEXT_ELIDED') else item
            return pd.DataFrame(records)
    client = DataikuClient(Executor(), 'LOCAL_SYNTHETIC', 'LOCAL_TEST')
    client.source_clob_batch_size = 32
    sql = io.SQL(client, journal=tmp_path/'calls.jsonl', binding='read-only-synthetic')
    expected = [dict(row, BLOCK_ID=f'{i:04}') for i in range(count)]
    observed = io.read_batch(sql, 'block_payload', expected)
    io.compare_batch('block_payload', expected, observed)
    if value:
        assert any(' UNION ALL ' in text for text in executed)
    if count == 20:
        assert any(text.count(' AS CLOB_SLOT') == 32 for text in executed)
    assert all('FROM DUAL' in text for text in executed)
