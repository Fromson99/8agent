import importlib.util
import json
from pathlib import Path
import sys
import types
import pytest
import sqlglot
from sqlglot import exp

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('capacity_check', HERE/'capacity_check.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def sample():
    return {'items': [{'kind':'one','asset':'a','table':'t','rows':100,'candidate':True},
                      {'kind':'two','asset':'a','table':'x','rows':900,'candidate':False}],
            'samples': [{'asset':'a','table':'t','status':'OK','sample_rows':32,
                         'prefix_mean_json_bytes':10,'binary_bytes_not_serialized':0}]}


def table(**extra):
    return dict(OWNER='SIDDS',TABLE_NAME='T',VISIBILITY='VISIBLE',PARTITIONED='NO',
                IOT_TYPE=None,CLUSTER_NAME=None,**extra)


def test_partial_reference_never_final_and_candidates_retained():
    r = c.source_reference(sample())
    assert r['planned_rows']==1000 and r['covered_rows']==100
    assert r['partial_source_json_bytes']==1000 and r['final_oracle_bytes'] is None
    assert r['rows'][0]['candidate_only_not_excluded']
    assert r['rows'][1]['source_json_extrapolated_bytes'] is None


@pytest.mark.parametrize('change', [{'status':'SOURCE_CHANGED_SAMPLE_INVALID'},
    {'binary_bytes_not_serialized':5}, {'prefix_mean_json_bytes':float('nan')}, {'sample_rows':0}])
def test_invalid_source_sample_is_missing(change):
    s=sample();s['samples'][0].update(change)
    assert c.source_reference(s)['covered_rows']==0
    assert c.source_reference(s)['partial_source_json_bytes'] is None


def test_duplicate_sample_is_not_cherry_picked():
    s=sample();s['samples'].append(dict(s['samples'][0]))
    assert c.source_reference(s)['covered_rows']==0


def test_unknown_allocation_not_zero_and_no_statistics_extrapolation():
    for segments in (None,[]):
        r=c.table_sizes([table(STATS_ROWS=100,AVG_ROW_LEN=10)],segments)[0]
        assert r['ALLOCATED_BYTES'] is None


def test_special_layout_not_certified():
    t=table();t['PARTITIONED']='YES'
    seg=[dict(OWNER='SIDDS',TABLE_NAME='T',ALLOCATED_BYTES=50)]
    assert c.table_sizes([t],seg)[0]['ALLOCATED_BYTES'] is None


def test_segment_total_includes_lob_index():
    seg=[dict(OWNER='SIDDS',TABLE_NAME='T',ALLOCATED_BYTES=n) for n in (100,20,80)]
    assert c.table_sizes([table()],seg)[0]['ALLOCATED_BYTES']==200


def test_permission_errors_preserved_no_user_owner_substitution(tmp_path):
    called=[]
    def query(sql):
        called.append(sql)
        if sql == c.SQL['identity']:return [{'LOGIN_USER':'PIDD2APP'}]
        if sql == c.SQL['tables']:return [table()]
        if any(v in sql for v in ('DBA_SEGMENTS','DBA_TS_QUOTAS','DBA_DATA_FILES')):
            raise RuntimeError('ORA-00942: table or view does not exist')
        return []
    r=c.run(query,sample(),tmp_path/'report')
    assert r['queries']['segments']['oracle_codes']==['ORA-00942']
    assert r['tables'][0]['ALLOCATED_BYTES'] is None
    assert r['queries']['visible_free']['status']=='OK'
    assert all('USER_SEGMENTS' not in sql and 'USER_TS_QUOTAS' not in sql for sql in called)
    assert json.loads((tmp_path/'report/CAPACITY_REPORT.json').read_text())['final_oracle_bytes'] is None


def test_identity_failure_stops(tmp_path):
    calls=[]
    def query(sql):calls.append(sql);raise RuntimeError('ORA-01017')
    c.run(query,{},tmp_path/'report')
    assert len(calls)==1


def test_interrupted_select_not_retried(tmp_path):
    calls=[]
    def query(sql):calls.append(sql);raise KeyboardInterrupt()
    r=c.run(query,{},tmp_path/'report')
    assert len(calls)==1 and r['interrupted']


def test_no_newest_file_selection_or_observer_mutation():
    class O:REPORT=sample();OUTPUT='past'
    r,origin=c.load_report(O)
    r['samples'].clear()
    assert len(O.REPORT['samples'])==1 and origin=='past'
    assert c.load_report()==({},'NO_R3_REPORT_SELECTED')


def test_all_sql_is_select_and_no_source_payload_or_count():
    for key,sql in c.SQL.items():
        tree=sqlglot.parse_one(sql,read='oracle')
        assert isinstance(tree,exp.Select),key
        assert not list(tree.find_all(exp.Count)),key
        assert not any(t.name.startswith('LGL_') for t in tree.find_all(exp.Table)),key


def test_exact_targets_match_delivered_contract():
    contract=json.loads((HERE.parent/'gold_fresh_1_20261102_r1/package/contract.json').read_text())
    assert c.TARGETS==[(t['owner'],t['name']) for t in contract['tables'].values()]
    assert len(c.TARGETS)==17


def time_module():
    spec=importlib.util.spec_from_file_location('time_analysis',HERE/'time_analysis.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_time_missing_not_zero_and_no_true_eta():
    result=time_module().analyze(sample())
    assert result['trial_covered_plan_rows']==0
    assert result['covered_request_hours_reference'] is None
    assert result['full_completion_eta_hours'] is None


def test_time_matches_kind_largest_requested_and_keeps_unmeasured():
    report=sample()
    base={'table':'SRCH_ROW','kind':'one','status':'ROLLED_BACK_VERIFIED'}
    report['oracle']={'insert_probes':[
        dict(base,rows=100,requested_rows=100,request_seconds=99),
        dict(base,rows=2000,requested_rows=2000,request_seconds=2),
        dict(base,rows=5000,requested_rows=5000,request_seconds=1,status='FAILED_OR_OUTCOME_UNKNOWN')]}
    result=time_module().analyze(report)
    assert result['trial_covered_plan_rows']==100 and result['unmeasured_plan_rows']==900
    assert result['covered_request_hours_reference']==pytest.approx(.1/3600)
    assert result['all_plan_if_missing_at_fastest_trial_hours']==pytest.approx(1/3600)
    assert result['rows'][1]['candidate_only_not_excluded']


def test_time_duplicate_plan_rejected():
    report=sample();report['items'].append(report['items'][0])
    with pytest.raises(ValueError,match='DUPLICATE_PLAN_KIND'):time_module().analyze(report)


def test_photograph_arithmetic():
    actual=[(12712168,2000,2.789),(9470521,2000,2.165),(9470521,2000,1.736),
            (4860821,2000,2.246),(3790031,1370,1.338)]
    hours=sum(n*s/rows/3600 for n,rows,s in actual)
    rest=60971724-sum(n for n,_,_ in actual)
    assert hours==pytest.approx(12.599882277213098)
    assert hours+rest*1.736/2000/3600==pytest.approx(17.583085226101986)
    assert hours+rest*3.196/1684/3600==pytest.approx(23.49554204100302)


def mock_display(monkeypatch):
    rendered=[]
    display=types.ModuleType('IPython.display')
    display.HTML=lambda value:value
    display.display=lambda value:rendered.append(value)
    display.clear_output=lambda **kwargs:None
    monkeypatch.setitem(sys.modules,'IPython.display',display)
    return rendered


def test_paste_ready_capacity_cell_and_every_page(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    rendered=mock_display(monkeypatch)
    calls=[]
    class Frame:
        def __init__(self,rows):self.rows=rows
        def astype(self,*args):return self
        def notna(self):return self
        def where(self,*args):return self
        def to_dict(self,**kwargs):return self.rows
    class Executor:
        def __init__(self,connection):assert connection=='AIDP'
        def query_to_df(self,sql,**kwargs):
            calls.append(sql)
            if 'DB_UNIQUE_NAME' in sql:return Frame([{'LOGIN_USER':'PIDD2APP'}])
            if 'AS VISIBILITY' in sql:return Frame([table()])
            raise RuntimeError('ORA-00942')
    dataiku=types.ModuleType('dataiku');dataiku.SQLExecutor2=Executor
    monkeypatch.setitem(sys.modules,'dataiku',dataiku)
    existing_run=object()
    scope={'run':existing_run}
    text=(HERE/'01_CHECK_CAPACITY_RUN_R1.txt').read_text()
    exec(compile(text,'capacity.txt','exec'),scope)
    count=len(calls)
    for page in ('테이블','한도','여유','자료','요약'):scope['SHOW_CAPACITY_PAGE'](page)
    assert len(calls)==count and scope['run'] is existing_run
    assert rendered and '미산정' in rendered[-1]
    assert len(list(tmp_path.glob('gold-capacity-reports/*/CAPACITY_REPORT.json')))==1


def test_paste_ready_time_cell_no_db_and_original_report_preserved(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);rendered=mock_display(monkeypatch)
    class Observer:REPORT=sample();OUTPUT='prior'
    before=json.dumps(Observer.REPORT,sort_keys=True)
    scope={'_g19_observer':Observer}
    text=(HERE/'03_ANALYZE_SAVED_R3_TIME_R1.txt').read_text()
    exec(compile(text,'time.txt','exec'),scope)
    assert json.dumps(Observer.REPORT,sort_keys=True)==before
    assert rendered and 'SQL/INSERT 실행 없음' in rendered[0]
    assert len(list(tmp_path.glob('gold-time-analysis/*/TIME_ANALYSIS.json')))==1
