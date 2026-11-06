"""Reproduce the photographed check and exercise the exact no-argument replacement."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
R2=HERE.parent/'agent_layer_async_20261105_r2'
OLD=next((HERE.parent/'existing_nfs_transfer_20261029_r1').glob('GENOS_*.zip'))
COLLISION='02_BACKEND/lawrag/pipeline/oracle_full_package.py'
ZIP='GENOS_AGENT_RETURN_R4.zip'
RUN='GENOS_DEPLOY_R4.txt'

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.PIPE).strip()

def h(data):return hashlib.sha256(data).hexdigest()

def check():
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp)
        workspace=base/'workspace';workspace.mkdir()
        (base/'DEV').symlink_to(workspace,target_is_directory=True)
        transfer=workspace/'TRANSFER';transfer.mkdir()
        for f in [HERE/RUN,HERE/ZIP,R2/'GENOS_DEPLOY_R2.txt']:shutil.copy(f,transfer/f.name)
        subprocess.run(['git','init','-qb','main',str(workspace)],check=True)
        def g(*a):return git(workspace,*a)
        g('config','user.name','Pipeline installer test')
        g('config','user.email','pipeline@localhost')
        remotes=base/'llmops';remotes.mkdir()
        for id,name in [('623','origin'),('761','pipeline')]:
            repo=remotes/(id+'.git')
            subprocess.run(['git','init','--bare','-qb','main',str(repo)],check=True)
            g('remote','add',name,str(repo))
        env=dict(os.environ,HOME=str(base),GIT_CONFIG_NOSYSTEM='1')
        def shell(script,*args):
            return subprocess.run(['bash','./'+script,*args],cwd=transfer,env=env,capture_output=True,text=True)
        with ZipFile(transfer/ZIP) as z:
            assert z.testzip() is None
            z.extractall(workspace)
            pins=dict(json.loads(z.read('CODE_PINS.json'))['files'],**{'CODE_PINS.json':h(z.read('CODE_PINS.json'))})
        with ZipFile(OLD) as z:
            raw=z.read(next(n for n in z.namelist() if n.endswith('/'+COLLISION)))
        target=workspace/COLLISION
        target.write_bytes(raw)
        assert h(raw)!=pins[COLLISION]
        (workspace/'user.txt').write_text('shared-before')
        g('add','--',COLLISION,'user.txt','service.py')
        g('commit','-qm','Prior pipeline')
        g('push','pipeline','main')
        g('push','origin','main')
        baseline=g('rev-parse','HEAD')
        shutil.copy(R2/'GENOS_AGENT_ASYNC_R2.zip',transfer/'GENOS_AGENT_ASYNC_R2.zip')
        old=shell('GENOS_DEPLOY_R2.txt')
        assert old.returncode and 'OCCUPIED_NEW_CHECKOUT:'+COLLISION in old.stderr
        assert target.read_bytes()==raw and baseline==g('rev-parse','HEAD')
        # Active checkout contains valuable local work, and does not track the pipeline remote.
        g('branch','--set-upstream-to','origin/main','main')
        (workspace/'local-only.txt').write_text('private');g('add','local-only.txt');g('commit','-qm','Private local commit')
        local_head=g('rev-parse','HEAD')
        user=workspace/'user.txt'
        user.write_text('staged text');g('add','user.txt');user.write_text('unstaged text')
        (workspace/'agent_stage.py').unlink()  # absent package member
        (workspace/'worker.py').write_text('untracked old worker')
        local_index=g('write-tree')
        rag_before=git(remotes/'623.git','rev-parse','main')
        first=shell(RUN)
        assert first.returncode==0,(first.stderr,first.stdout)
        commit=git(remotes/'761.git','rev-parse','main')
        assert commit.decode() in first.stdout and 'GENOS_CODE_PUSHED pipeline refs/heads/main' in first.stdout
        assert git(remotes/'761.git','rev-parse','main^')==baseline
        def localsafe():
            assert local_head==g('rev-parse','HEAD') and local_index==g('write-tree')
            assert g('show',':user.txt')==b'staged text' and user.read_text()=='unstaged text'
            assert rag_before==git(remotes/'623.git','rev-parse','main')
        localsafe()
        backup=workspace/'.git/genos-agent-return-r4'
        assert (backup/'original'/COLLISION).read_bytes()==raw
        assert (backup/'original/worker.py').read_text()=='untracked old worker'
        assert all(h((workspace/n).read_bytes())==v for n,v in pins.items())
        names=git(remotes/'761.git','ls-tree','-r','--name-only','main').decode().splitlines()
        assert set(names)==set(pins)|{'user.txt'}
        assert git(remotes/'761.git','show','main:user.txt')==b'shared-before'
        # Independent committed ZIP/blob verification (not just the script's success line).
        exported=subprocess.check_output(['git','--git-dir',str(remotes/'761.git'),'archive','--format=zip','main'])
        import io
        with ZipFile(io.BytesIO(exported)) as z:
            assert all(h(z.read(n))==v for n,v in pins.items())
        assert shell(RUN).returncode==0 and git(remotes/'761.git','rev-parse','main')==commit
        assert shell(RUN,'--remote','origin').returncode!=0
        target.write_text('new local edit')
        assert shell(RUN).returncode!=0 and target.read_text()=='new local edit'
        with ZipFile(transfer/ZIP) as z:target.write_bytes(z.read(COLLISION))
        reset=shell(RUN,'--restore-local')
        assert reset.returncode==0,reset.stderr
        assert target.read_bytes()==raw and (workspace/'worker.py').read_text()=='untracked old worker' and not (workspace/'agent_stage.py').exists()
        assert git(remotes/'761.git','rev-parse','main')==commit
        localsafe()
        assert shell(RUN).returncode==0
        return dict(reproduced='OCCUPIED_NEW_CHECKOUT:'+COLLISION,previous_fixture=str(OLD.name),
            archive_sha256=h((HERE/ZIP).read_bytes()),installer_sha256=h((HERE/RUN).read_bytes()),
            verified_files=len(pins),local_remote_commit=commit.decode(),field_deployment=False,
            cases=['same TRANSFER command and HOME/DEV symlink','old version and untracked collision backed up',
                   'missing package member installed','all committed blobs equal ZIP','only pipeline remote advanced',
                   'user index, private commit and other work preserved','idempotent retry','RAG origin rejected',
                   'post-backup edit preserved','working-file rollback and reapply'])


if __name__=='__main__':
    print(json.dumps(check(),ensure_ascii=False,indent=2))
