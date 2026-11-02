from pathlib import Path
import sys
import csv
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import inventory as inv


def item(name):return {'owner':'SIDDS','table':name,'group':'old','reference':'fixture','current_target':False}


def test_actual_zero_stale_statistics_and_missing(tmp_path):
    calls=[]
    def query(sql):
        calls.append(sql)
        if sql==inv.METADATA_SQL:return [{'OWNER':'SIDDS','TABLE_NAME':'LGL_DOC_VER_S','STATS_ROWS':999,'PARTITIONED':'NO'}]
        return [{'EXACT_ROWS':0}]
    rows,path=inv.inventory(query,[item('LGL_DOC_VER_S'),item('LGL_DOC_BLK_S')],tmp_path,include_size=False,notify=lambda x:None)
    known={r['TABLE_NAME']:r for r in rows}
    assert known['LGL_DOC_VER_S']['EXACT_ROWS']==0
    assert known['LGL_DOC_VER_S']['STATS_ROWS']==999
    assert 'EXACT_ROWS' not in known['LGL_DOC_BLK_S']
    assert known['LGL_DOC_BLK_S']['COUNT_STATE']=='NOT_VISIBLE_OR_ABSENT'
    assert len(calls)==2
    assert len(list(csv.DictReader(path.open(encoding='utf-8-sig'))))==2


def test_size_permission_failure_and_count_failure_continue(tmp_path):
    def query(sql):
        if sql==inv.METADATA_SQL:return [{'OWNER':'SIDDS','TABLE_NAME':x,'PARTITIONED':'NO'} for x in ['LGL_A_S','LGL_B_S']]
        if sql==inv.ALLOCATION_SQL:raise RuntimeError('ORA-00942: table or view does not exist')
        if 'SIDDS.LGL_A_S' in sql:raise RuntimeError('ORA-01031: insufficient privileges')
        return [{'EXACT_ROWS':17}]
    rows,_=inv.inventory(query,[item('LGL_A_S'),item('LGL_B_S')],tmp_path,notify=lambda x:None)
    assert rows[0]['COUNT_STATE']=='ERROR'
    assert rows[1]['EXACT_ROWS']==17
    assert all(r['SIZE_STATE']=='QUERY_FAILED_OR_NO_PRIVILEGE' for r in rows)
    assert all('ALLOCATED_BYTES' not in r for r in rows)


def test_discovered_tables_not_counted_by_default(tmp_path):
    calls=[]
    def query(sql):
        calls.append(sql)
        return [{'OWNER':'SIDDS','TABLE_NAME':'LGL_SOMEONE_ELSE_S'}]
    rows,_=inv.inventory(query,[],tmp_path,include_size=False,notify=lambda x:None)
    assert len(calls)==1
    assert rows[0]['COUNT_STATE']=='SKIPPED_NOT_EXACT'


def test_partitioned_size_not_presented_as_full(tmp_path):
    def query(sql):
        if sql==inv.METADATA_SQL:return [{'OWNER':'SIDDS','TABLE_NAME':'LGL_A_S','PARTITIONED':'YES'}]
        if sql==inv.ALLOCATION_SQL:return [{'OWNER':'SIDDS','TABLE_NAME':'LGL_A_S','ALLOCATED_BYTES':999}]
        return [{'EXACT_ROWS':7}]
    rows,_=inv.inventory(query,[item('LGL_A_S')],tmp_path,notify=lambda x:None)
    assert rows[0]['SIZE_STATE']=='PARTITIONED_NOT_FULLY_MAPPED'
    assert 'ALLOCATED_BYTES' not in rows[0]


@pytest.mark.parametrize('owner,name',[('OTHER','LGL_A_S'),('SIDDS','LGL_A_S; DROP TABLE X'),('SIDDS','OTHER_TABLE')])
def test_identifier_rejected(owner,name):
    with pytest.raises(ValueError):inv.exact_sql(owner,name)


def test_interrupt_preserves_completed_csv(tmp_path):
    def query(sql):
        if sql==inv.METADATA_SQL:return [{'OWNER':'SIDDS','TABLE_NAME':x} for x in ['LGL_A_S','LGL_B_S']]
        if 'SIDDS.LGL_A_S' in sql:return [{'EXACT_ROWS':12}]
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):inv.inventory(query,[item('LGL_A_S'),item('LGL_B_S')],tmp_path,include_size=False,notify=lambda x:None)
    rows=list(csv.DictReader(next(tmp_path.glob('*.csv')).open(encoding='utf-8-sig')))
    assert rows[0]['EXACT_ROWS']=='12'
    assert rows[1]['COUNT_STATE']=='INTERRUPTED_UNKNOWN'
