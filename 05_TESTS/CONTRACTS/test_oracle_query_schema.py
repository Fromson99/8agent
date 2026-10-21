"""Query DDL compatibility/recovery at the existing ORDS boundary (no live DB)."""
import copy
import re

import pytest

from semantic_runtime.oracle_dp_io import DPError, SQL
from semantic_runtime.oracle_query_catalog import DDL
from lawrag.pipeline.oracle_query_publish import schema


class SchemaOracle:
    SQL_PATH = '/sql'

    def __init__(self):
        self.created, self.writes = set(), []
        self.lose_reply = False
        self.columns = {
            'LEGAL_RAG_QUERY_RELEASE_A': [('RELEASE_ID','VARCHAR2',64,'N'),('MANIFEST_JSON','CLOB',None,'N')],
            'LEGAL_RAG_QUERY_ROW_A': [(n,'VARCHAR2',w,nullable) for n,w,nullable in [
                ('RELEASE_ID',64,'N'),('KIND',64,'N'),('ROW_ID',64,'N'),('DOCUMENT_ID',512,'Y'),
                ('LOOKUP_ID',512,'Y'),('OWNER_ID',512,'Y'),('TARGET_ID',512,'Y'),('ROW_SHA256',64,'N')]]+
                [('VALUE_JSON','CLOB',None,'N')],
            'LEGAL_RAG_QUERY_ACTIVE_A': [('CHANNEL','VARCHAR2',64,'N'),('RELEASE_ID','VARCHAR2',64,'N'),('REVISION','NUMBER',18,'N')],
            'LEGAL_RAG_QUERY_STATE_A': [('SCOPE_HASH','VARCHAR2',64,'N'),('STATE_KEY','VARCHAR2',128,'N'),
                ('REVISION','NUMBER',18,'N'),('VALUE_SHA256','VARCHAR2',64,'N'),('VALUE_JSON','CLOB',None,'N')],
        }
        self.primary = {'LEGAL_RAG_QUERY_RELEASE_A':['RELEASE_ID'],
                        'LEGAL_RAG_QUERY_ROW_A':['RELEASE_ID','KIND','ROW_ID'],
                        'LEGAL_RAG_QUERY_ACTIVE_A':['CHANNEL'],
                        'LEGAL_RAG_QUERY_STATE_A':['SCOPE_HASH','STATE_KEY']}
        self.checks = {'LEGAL_RAG_QUERY_RELEASE_A':['MANIFEST_JSON IS JSON'],
                       'LEGAL_RAG_QUERY_ROW_A':['VALUE_JSON IS JSON'],
                       'LEGAL_RAG_QUERY_ACTIVE_A':['"REVISION">=1'],
                       'LEGAL_RAG_QUERY_STATE_A':['VALUE_JSON IS JSON','REVISION>=1']}
        self.references = [{'DELETE_RULE':'NO ACTION','COLUMN_NAME':'RELEASE_ID','TARGET_OWNER':'SIDDA',
                            'TARGET_TABLE':'LEGAL_RAG_QUERY_RELEASE_A','TARGET_COLUMN':'RELEASE_ID'}]

    def request(self, method, path, json):
        assert (method,path) == ('POST',self.SQL_PATH)
        text = json['statementText']
        binds = {r['name']:r['value'] for r in json.get('binds',[])}
        if text.startswith('CREATE '):
            assert text in DDL
            name = text.split()[2].split('.')[1]
            assert name not in self.created
            self.created.add(name)
            self.writes.append(text)
            if self.lose_reply:
                self.lose_reply = False
                raise TimeoutError('DDL committed but response was lost')
            return {'items':[{'result':0}]}
        assert text.startswith('SELECT ')
        assert binds['owner'] == 'SIDDA'
        name = binds['name']
        rows = []
        if name in self.created:
            if 'FROM ALL_TAB_COLUMNS' in text:
                rows = [{'COLUMN_NAME':n,'DATA_TYPE':t,'DATA_LENGTH':w if t=='VARCHAR2' else 22,
                         'DATA_PRECISION':w if t=='NUMBER' else None,'DATA_SCALE':0 if t=='NUMBER' else None,
                         'NULLABLE':nullable,'CHAR_USED':'B' if t=='VARCHAR2' else None}
                        for n,t,w,nullable in self.columns[name]]
            elif 'FROM ALL_IND_COLUMNS' in text:
                field = name.removeprefix('LEGAL_Q_ROW_')+'_ID'
                rows = [{'TABLE_NAME':'LEGAL_RAG_QUERY_ROW_A','COLUMN_NAME':c,'COLUMN_POSITION':i}
                        for i,c in enumerate(['RELEASE_ID','KIND',field],1)]
            elif 'SELECT CONSTRAINT_TYPE' in text:
                rows = [{'CONSTRAINT_TYPE':'P','STATUS':'ENABLED','VALIDATED':'VALIDATED','SEARCH_CONDITION_VC':None}]
                rows += [{'CONSTRAINT_TYPE':'C','STATUS':'ENABLED','VALIDATED':'VALIDATED','SEARCH_CONDITION_VC':c}
                         for c in self.checks[name]]
            elif 'SELECT fk.DELETE_RULE' in text:
                rows = self.references
            else:
                assert "p.CONSTRAINT_TYPE='P'" in text
                rows = [{'COLUMN_NAME':c,'POSITION':i} for i,c in enumerate(self.primary[name],1)]
        return {'items':[{'resultSet':{'items':copy.deepcopy(rows),'offset':0,'hasMore':False}}]}


def test_schema_is_read_only_until_create_and_never_overwrites(tmp_path):
    remote = SchemaOracle()
    sql = SQL(remote,journal=tmp_path/'calls.jsonl',binding='schema')
    result = schema(sql)
    assert result['status']=='MISSING' and len(result['missing'])==8 and not remote.writes
    assert schema(sql,create=True)['status']=='READY'
    assert len(remote.writes)==8
    assert schema(sql,create=True)['status']=='READY' and len(remote.writes)==8


@pytest.mark.parametrize('change,expected', [
    ('nullable','QUERY_DDL_TYPE'),('precision','QUERY_DDL_TYPE'),
    ('primary','QUERY_DDL_PRIMARY_KEY'),('foreign','QUERY_DDL_CONSTRAINT'),('json','QUERY_DDL_CONSTRAINT'),
])
def test_incompatible_existing_objects_fail_without_repair(tmp_path,change,expected):
    remote = SchemaOracle()
    sql = SQL(remote,journal=tmp_path/'calls.jsonl',binding='schema')
    schema(sql,create=True)
    if change=='nullable': remote.columns['LEGAL_RAG_QUERY_RELEASE_A'][1]=('MANIFEST_JSON','CLOB',None,'Y')
    if change=='precision': remote.columns['LEGAL_RAG_QUERY_ACTIVE_A'][2]=('REVISION','NUMBER',10,'N')
    if change=='primary': remote.primary['LEGAL_RAG_QUERY_ROW_A']=['ROW_ID']
    if change=='foreign': remote.references[0]['TARGET_TABLE']='UNRELATED_TABLE'
    if change=='json': remote.checks['LEGAL_RAG_QUERY_STATE_A'].remove('VALUE_JSON IS JSON')
    with pytest.raises(DPError,match=expected): schema(sql,create=True)
    assert len(remote.writes)==8


def test_lost_ddl_response_is_not_retried_and_explicit_resume_inspects_committed_object(tmp_path):
    remote = SchemaOracle(); remote.lose_reply=True
    sql = SQL(remote,journal=tmp_path/'calls.jsonl',binding='schema')
    with pytest.raises(DPError,match='WRITE_UNCONFIRMED'): schema(sql,create=True)
    assert len(remote.writes)==1
    assert schema(sql,create=True)['status']=='READY'
    assert len(remote.writes)==8


def test_pipeline_ddl_entry_has_no_connection_or_schema_side_effect(monkeypatch,capsys):
    from lawrag.pipeline.oracle_query_publish import main
    from semantic_runtime import oracle_dp
    monkeypatch.setattr(oracle_dp,'client_from_environment',lambda:pytest.fail('DDL preview contacted Oracle'))
    assert main(['ddl'])==0
    text = capsys.readouterr().out
    assert text.count('CREATE TABLE')==4 and text.count('CREATE INDEX')==4
    assert not re.search(r'\b(DROP|TRUNCATE|ALTER)\b',text)
