"""Sample notebook needs only its code-folder ID. The DSS connection owns all SQL."""
import os
from pathlib import Path

def setup_table(params):
    import dataiku
    from agent_setup import identity,rows,block,verify,DDL,FQN
    db=dataiku.SQLExecutor2(connection=params['AGENT_CONNECTION'])
    dbname,pdb,login=identity(db)
    if login!=params['EXPECTED_DB_USER']:
        raise ValueError('AIDP 연결이 이전 개발계 계정 PIDD2APP과 다릅니다: '+str(login))
    if not rows(db,"SELECT 1 FROM ALL_TABLES WHERE OWNER='SIDDA' AND TABLE_NAME='LGL_PIPE_RESULT_A'"):
        block(db,"BEGIN EXECUTE IMMEDIATE '"+DDL+"'; EXCEPTION WHEN OTHERS THEN "
              "IF SQLCODE != -955 THEN RAISE; END IF; END;")
    verify(db)
    rows(db,'SELECT JOB_ID FROM '+FQN+' WHERE 1=0')
    block(db,'BEGIN IF FALSE THEN INSERT INTO '+FQN+
          '(JOB_ID,SEQ_NO,BIND_HASH,DATA_HASH,BYTE_CNT,PART_CNT) VALUES (NULL,0,NULL,NULL,1,1); END IF; END;')
    print('AGENT_LAYER_READY',params['AGENT_CONNECTION'],login,FQN,dbname,pdb)


def install_sample(folder_id, bootstrap):
    import dataiku
    import hashlib
    from sample_input import INDEX
    from flow_install import validate,install
    if not isinstance(folder_id,str) or not folder_id.strip():
        raise ValueError('세 ZIP을 올린 폴더의 ID를 CODE_FOLDER_ID에 입력하세요.')
    variables=dataiku.get_custom_variables()
    shared=variables.get('AGENT_FLOW_WORK_DIR') or str(Path.home()/'.dataiku-agent-work')
    cfg=dict(CODE_FOLDER_ID=folder_id,INPUT_FOLDER_ID=folder_id,SUPPORT_FOLDER_ID=folder_id,
             DOCUMENT_PREFIX='',GOLD_OWNER='',ENVIRONMENT='DEV',INPUT_MODE='SAMPLE_ZIP',
             WORK_DIR=shared,AGENT_CONNECTION='AIDP',TARGET_CONNECTION='AIDP',EXPECTED_DB_USER='PIDD2APP',
             EMBED_MODEL='openai:genos-embedding:embedding-kure-v1',EMBED_DIMENSIONS=1024)
    validate(cfg)
    source=dataiku.Folder(folder_id,ignore_flow=True)
    for item in (INDEX['raw'],INDEX['support']):
        with source.get_download_stream(item['file']) as f:
            raw=f.read(item['bytes']+1)
        if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('UPLOAD_ORIGINAL_ZIP:'+item['file'])
    setup_table(cfg)
    return install(cfg,bootstrap)
