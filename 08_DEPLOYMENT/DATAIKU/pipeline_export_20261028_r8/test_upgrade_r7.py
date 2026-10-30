import time
from pathlib import Path
import pytest
from test_compute import env,module


@pytest.mark.parametrize('case',['missing_audit','budget','deadline','result','running','unknown_code','different_input'])
def test_r7_no_model_code_upgrade_preserves_history_without_fake_audit(env,case):
    helper=module('r7_upgrade_fixture',Path(__file__).parent.parent/'pipeline_pod_20261028_r4/test_pod.py')
    helper.OLD='1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
    folder,store,new=helper.old_state(env)
    if case=='budget':store.value['attempt_count']=3
    elif case=='deadline':store.value['deadline']=time.time()-1
    elif case=='result':store.value['result_blob']={'path':'do-not-discard'}
    elif case=='running':store.value['last_observed']['state']='RUNNING'
    elif case=='unknown_code':store.value['compute']['code_sha256']='f'*64
    elif case=='different_input':new['input']={'changed':True}
    store.save();before=dict(folder.files);deadline=store.value['deadline']
    if case!='missing_audit':
        with pytest.raises(ValueError):env.c.open_store(folder,'same',new)
        assert folder.files==before
    else:
        result=env.c.open_store(folder,'same',new)
        assert result.value['deadline']==deadline and result.value['attempt_count']==2
        assert result.value['reserved_sql_calls']==192 and result.value['reserved_http_calls']==512
        proof=result.value['upgrade_history'][-1]['zero_review_proof']
        assert proof['basis']=='SEALED_R7_FIXED_SKIP_NO_MODEL_PATH' and not proof['field_calls_measured']
        assert not result.value.get('audit_blob') and not result.value.get('result_blob')
        assert all(folder.files[k]==v for k,v in before.items())


@pytest.mark.parametrize('case',['zero','nonzero','tampered','count_mismatch'])
def test_r7_existing_audit_must_still_validate(env,tmp_path,case):
    helper=module('r7_audit_fixture',Path(__file__).parent.parent/'pipeline_pod_20261028_r4/test_pod.py')
    helper.OLD='1982ddf7ab401b01ab4a59b37b4006a395adfaead7c7231a4520e2d965c35e5c'
    helper.test_r3_migration_budget_proof(env,tmp_path,case)
