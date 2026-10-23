"""Convert the reviewed design into the explicitly enabled development execution map."""
import json
from pathlib import Path
import sys
import yaml
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
sys.path.insert(0,str(REPO/'02_BACKEND'))
from semantic_runtime.physical_mapping import SchemaMap,ROLES

def build():
    source=REPO/'07_DOCS/REFERENCE/REPORTS/DATAIKU_GOLD_NAME_MAPPING_20261023/physical_mapping.draft.yaml'
    draft=yaml.safe_load(source.read_text())
    out={'schema_version':'legal-oracle-map-v1','revision':'20261023-dev-silver-r1',
         'profiles':{'dev_silver':{'enabled':True,'owner_by_role':dict.fromkeys(sorted(ROLES),'SIDDA')},
                     'prod_gold':{'enabled':False,'owner_by_role':dict.fromkeys(sorted(ROLES),None)}},'tables':{}}
    for key,t in draft['tables'].items():
        col=lambda k:t['columns'][k]['application_key']
        result={'name':t['candidate_name'],'role':t['storage_role'],
                'description':t['metadata']['description_plain_text']+'\n개발 실버 검증용: AIDP/SIDDA. 골드 표준 승인 미완료.',
                'columns':{},'pk':[col(c) for c in t['primary_key']],'pk_name':t['pk_name_candidate'],
                'indexes':[],'checks':[],'foreign_keys':[]}
        for k,c in t['columns'].items():
            result['columns'][col(k)]={'name':c['candidate_name'],'type':c['candidate_type'],
              'nullable':c['nullable'],'default':c['default'],
              'description':c['metadata']['description_plain_text']}
        result['indexes']=[{'name':i['name_candidate'],'columns':[col(c) for c in i['columns']]} for i in t['indexes']]
        result['checks']=[{'name':c['name_candidate'],'kind':{'is_json':'is_json','ge':'revision','asset_part_bounds':'part_bounds'}[c['operator']],
                          'columns':[col(v) for v in c['columns']]} for c in t['checks']]
        result['foreign_keys']=[{'name':f['name_candidate'],'columns':[col(c) for c in f['columns']],
               'target':f['target_table'],'target_columns':[draft['tables'][f['target_table']]['columns'][c]['application_key'] for c in f['target_columns']]} for f in t['foreign_keys']]
        out['tables'][key]=result
    path=HERE/'physical_mapping.yaml'
    # Seed once from the reviewed design; subsequent builds use the runtime YAML.
    # An approved edit must not be silently replaced by an older design draft.
    if not path.exists():path.write_text(yaml.safe_dump(out,allow_unicode=True,sort_keys=False))
    mapping=SchemaMap.load(path)
    header='-- AIDP 연결 / SIDDA / 개발 실버 검증용. 기존 LEGAL_* 객체 보존. 운영 골드 승인 아님.\n-- SQL 노트북에서 각 문장을 별도 Query로 실행. 존재하는 객체는 건너뛰고 check 단계로 구조 대조.\n-- 기존 객체를 DROP/ALTER/TRUNCATE 하지 않음. DDL은 Oracle 자동 커밋.\n-- 실행 후 Python ACTION="check"의 READY 확인 후 ACTION="run".\n-- 실행 매핑 SHA256: '+mapping.execution_sha256+'\n\n'
    objects=[o for _,_,o,_ in mapping.ddl()]
    pre="SELECT OWNER,OBJECT_NAME,OBJECT_TYPE FROM ALL_OBJECTS WHERE OWNER='SIDDA' AND OBJECT_NAME IN ("+','.join("'"+n+"'" for n in objects)+") ORDER BY OBJECT_TYPE,OBJECT_NAME;\n\n"
    ddl=header+'-- 00. 기존 객체 확인\n'+pre
    for number,(_,key,_,sql) in enumerate(mapping.ddl(),1):ddl+=f'-- {number:02d}. {mapping.tables[key]["description"].splitlines()[0]}\n{sql};\n\n'
    (HERE/'01_CREATE_TABLES.sql').write_text(ddl)
    comments=header
    literal=lambda s:"'"+s.replace("'","''")+"'"
    for k,t in mapping.tables.items():
        assert len(t['description'].encode())<=4000
        comments+='COMMENT ON TABLE '+mapping.names(k).table+' IS '+literal(t['description'])+';\n'
        for c in t['columns'].values():
            assert len(c['description'].encode())<=4000
            comments+='COMMENT ON COLUMN '+mapping.names(k).table+'.'+c['name']+' IS '+literal(c['description'])+';\n'
    (HERE/'02_COMMENTS.sql').write_text(comments)
    (HERE/'MAPPING_BINDING.json').write_text(json.dumps({'yaml_sha256':mapping.file_sha256,'execution_sha256':mapping.execution_sha256,'target_sha256':mapping.target_sha256,'profile':'dev_silver','connection':'AIDP','owner':'SIDDA','tables':9,'columns':46,'production_approved':False},indent=2)+'\n')

if __name__=='__main__':build()
