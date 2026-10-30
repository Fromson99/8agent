"""Actual local Git repositories; no GENOS network or live credentials."""
from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, sys, zipfile
import pytest
ROOT=Path(__file__).resolve().parents[2]
FILE=ROOT/'06_TOOLS/COMMANDS/genos_rag_git_publish.py'
spec=importlib.util.spec_from_file_location('rag_git_publish_test_target',FILE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
OUT=ROOT/'08_DEPLOYMENT/GENOS/handoffs/main123_auto_git_20261030_r4'
NAME='GENOS_MAIN123_RAG_AUTO_GIT_20261030_R4'
REAL_GIT=shutil.which('git')


def git(root,*args,check=True):
    return subprocess.run([REAL_GIT,'-C',str(root),*args],check=check,capture_output=True,text=True)


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    dev=tmp_path/'workspace';dev.mkdir()
    git(dev,'init','-q','-b','main');git(dev,'config','user.name','Local test');git(dev,'config','user.email','test@example.invalid')
    (dev/'.gitignore').write_text('/TRANSFER/\n.env\n01_DATA/\n')
    (dev/'base.txt').write_text('tracked unrelated file\n')
    (dev/'service.py').write_text('print("before")\n')
    git(dev,'add','.');git(dev,'commit','-qm','baseline')
    remotes={}
    for key in m.REMOTES:
        path=tmp_path/(key+'.git');git(tmp_path,'init','-q','--bare',str(path))
        git(dev,'push',str(path),'HEAD:refs/heads/main');git(dev,'remote','add',key,m.REMOTES[key]);remotes[key]=str(path)
    wrapper=tmp_path/'bin';wrapper.mkdir()
    # Only network Git subcommands are translated to local bare repositories.
    (wrapper/'git').write_text('''#!/usr/bin/env python3
import json,os,subprocess,sys
args=sys.argv[1:];mapping=json.loads(os.environ['TEST_GIT_DESTINATIONS'])
network=any(x in args for x in ('ls-remote','fetch','push')) and '--get-url' not in args
if network:
    original=list(args)
    if 'push' in args and os.environ.get('TEST_FAIL_FINANCIAL')=='1' and ('financial_team' in args):
        raise SystemExit(1)
    args=[mapping.get(x,x) for x in args]
raise SystemExit(subprocess.call([os.environ['TEST_REAL_GIT'],*args]))
''')
    (wrapper/'git').chmod(0o755)
    mapping={**remotes,**{m.REMOTES[k]:v for k,v in remotes.items()}}
    monkeypatch.setenv('TEST_GIT_DESTINATIONS',json.dumps(mapping));monkeypatch.setenv('TEST_REAL_GIT',REAL_GIT)
    monkeypatch.setenv('PATH',str(wrapper)+os.pathsep+os.environ['PATH'])
    package=dev/'TRANSFER/package';package.mkdir(parents=True)
    raw=b'print("after")\n';code={'service.py':m.digest(raw)}
    (package/'payload').mkdir();(package/'payload/service.py').write_bytes(raw)
    manifest={'format':'8agent-code/1','files':[{'path':'service.py','sha256':m.digest(raw),'bytes':len(raw)}]}
    (package/'CODE_MANIFEST.json').write_text(json.dumps(manifest))
    with zipfile.ZipFile(package/'code.zip','w') as z:
        z.writestr('CODE_MANIFEST.json',json.dumps(manifest));z.writestr('service.py',raw)
    shutil.copyfile(ROOT/'06_TOOLS/COMMANDS/genos_release_gate.py',package/'genos_release_gate.py')
    spec={'version':'fixture-rag','code':code,'patch':list(code),'git_publish':{'scope':'rag-code-serving','branch':'main','remotes':m.REMOTES},
          'payload':{p.relative_to(package).as_posix():m.digest(p.read_bytes()) for p in package.rglob('*') if p.is_file()}}
    (package/'PACKAGE.json').write_text(json.dumps(spec))
    return dev,package,remotes,raw


def publisher(fixture):return m.Publisher(fixture[0],fixture[1])


def install(f): (f[0]/'service.py').write_bytes(f[3])


def test_real_commit_push_and_idempotent_repeat(fixture):
    f=fixture;p=publisher(f);p.preflight();install(f);p.publish()
    commit=p.state['commit'];count=git(f[0],'rev-list','--count','HEAD').stdout.strip()
    assert count=='2' and p.state['status']=='complete'
    assert git(f[0],'diff-tree','--no-commit-id','--name-only','-r','HEAD').stdout.strip()=='service.py'
    for path in f[2].values():assert git(Path(path),'rev-parse','refs/heads/main').stdout.strip()==commit
    p=publisher(f);p.preflight();p.publish()
    assert git(f[0],'rev-list','--count','HEAD').stdout.strip()==count


def test_partial_push_failure_resumes_without_second_commit(fixture,monkeypatch):
    f=fixture;install(f);monkeypatch.setenv('TEST_FAIL_FINANCIAL','1');p=publisher(f)
    with pytest.raises(m.PublishError,match='not confirmed'):p.publish()
    assert p.state['remotes']['risk_team']['status']=='confirmed'
    assert p.state['remotes']['financial_team']['status']=='unconfirmed'
    commit=p.state['commit'];monkeypatch.delenv('TEST_FAIL_FINANCIAL')
    p=publisher(f);p.preflight();p.publish();assert p.state['commit']==commit and p.state['status']=='complete'
    assert git(f[0],'rev-list','--count','HEAD').stdout.strip()=='2'


def test_lost_push_acknowledgement_is_read_back_without_retry(fixture,monkeypatch):
    f=fixture;install(f);p=publisher(f);original=p.git;pushes=[]
    def lost(*args,**kwargs):
        result=original(*args,**kwargs)
        if 'push' in args:
            pushes.append(args)
            raise m.PublishError('simulated lost acknowledgement')
        return result
    monkeypatch.setattr(p,'git',lost)
    p.publish()
    assert p.state['status']=='complete' and len(pushes)==2
    assert all(r['push_exit'] is None for r in p.state['remotes'].values())


@pytest.mark.parametrize('kind',['unrelated','staged_unrelated','wrong_branch','wrong_url','multiple_push_urls','url_rewrite','merge','tampered_package','pipeline_scope'])
def test_preflight_refuses_unsafe_context(fixture,kind):
    f=fixture;dev,package=f[:2]
    if kind in ('unrelated','staged_unrelated'):
        (dev/'base.txt').write_text('preserve this change')
        if kind=='staged_unrelated':git(dev,'add','base.txt')
    if kind=='wrong_branch':git(dev,'checkout','-qb','pipeline')
    if kind=='wrong_url':git(dev,'remote','set-url','risk_team','http://wrong.invalid/pipeline.git')
    if kind=='multiple_push_urls':
        git(dev,'remote','set-url','--add','--push','risk_team',m.REMOTES['risk_team'])
        git(dev,'remote','set-url','--add','--push','risk_team','http://wrong.invalid/other.git')
    if kind=='url_rewrite':git(dev,'config','url.http://wrong.invalid/.insteadOf','http://llmops-gitea-service:3000/')
    if kind=='merge':(dev/'.git/MERGE_HEAD').write_text(git(dev,'rev-parse','HEAD').stdout)
    if kind=='tampered_package':(package/'payload/service.py').write_text('changed')
    if kind=='pipeline_scope':
        data=json.loads((package/'PACKAGE.json').read_text());data['git_publish']['scope']='pipeline';(package/'PACKAGE.json').write_text(json.dumps(data))
    head=git(dev,'rev-parse','HEAD').stdout
    with pytest.raises(m.PublishError):publisher(f).preflight()
    assert git(dev,'rev-parse','HEAD').stdout==head


def test_remote_divergence_never_forces_or_merges(fixture,tmp_path):
    f=fixture;other=tmp_path/'other';git(tmp_path,'clone','-q','-b','main',f[2]['financial_team'],str(other))
    (other/'other.txt').write_text('remote work');git(other,'add','.')
    git(other,'-c','user.name=Other','-c','user.email=other@example.invalid','commit','-qm','remote change')
    git(other,'push','origin','main');remote=git(other,'rev-parse','HEAD').stdout.strip()
    with pytest.raises(m.PublishError,match='diverged'):publisher(f).preflight()
    assert git(Path(f[2]['financial_team']),'rev-parse','main').stdout.strip()==remote
    assert git(f[0],'rev-list','--count','HEAD').stdout.strip()=='1'


def test_crash_after_commit_recovers_same_commit(fixture):
    f=fixture;install(f);p=publisher(f);commit=p.commit()
    state=p.state;state.update(commit=None,status='committing');m.write(p.state_path,state)
    p=publisher(f);assert p.commit()==commit
    assert git(f[0],'rev-list','--count','HEAD').stdout.strip()=='2'


def test_new_commit_after_checkpoint_is_not_adopted(fixture):
    f=fixture;install(f);p=publisher(f);p.commit()
    git(f[0],'commit','--allow-empty','-qm','unrelated later commit')
    with pytest.raises(m.PublishError,match='HEAD changed'):publisher(f).publish()


def test_gate_failure_keeps_commit_and_does_not_push(fixture,monkeypatch):
    f=fixture;install(f);p=publisher(f)
    def bad_gate(commit):raise m.PublishError('gate failure')
    monkeypatch.setattr(p,'gate',bad_gate)
    with pytest.raises(m.PublishError,match='gate failure'):p.publish()
    assert p.state['commit'] and p.state['remotes']=={}
    assert all(git(Path(r),'rev-list','--count','main').stdout.strip()=='1' for r in f[2].values())


def test_index_conversion_blocks_commit(fixture):
    f=fixture;install(f)
    git(f[0],'config','filter.change.clean',"sed s/after/changed/")
    (f[0]/'.git/info/attributes').write_text('service.py filter=change\n')
    with pytest.raises(m.PublishError,match='Git bytes differ'):publisher(f).commit()
    assert git(f[0],'rev-list','--count','HEAD').stdout.strip()=='1'


def test_commit_hook_cannot_add_unrelated_files_to_push(fixture):
    f=fixture;install(f)
    hook=f[0]/'.git/hooks/pre-commit'
    hook.write_text('#!/bin/sh\nprintf unrelated > unrelated.txt\ngit add unrelated.txt\n')
    hook.chmod(0o755)
    with pytest.raises(m.PublishError,match='authorized commit scope'):publisher(f).publish()
    assert all(git(Path(r),'rev-list','--count','main').stdout.strip()=='1' for r in f[2].values())


def test_auth_helper_scopes_host_and_keeps_password_out_of_files(fixture,monkeypatch):
    secret='synthetic-test-only-credential';monkeypatch.setenv(m.PASSWORD_ENV,secret);p=publisher(fixture)
    with m.Authentication(p):
        helper=Path(p.env['GIT_ASKPASS']);assert secret not in helper.read_text()
        for prompt,expected in [("Username for 'http://llmops-gitea-service:3000':",m.USERNAME),
                                ("Password for 'http://TD8461@llmops-gitea-service:3000':",secret)]:
            result=subprocess.run([sys.executable,str(helper),prompt],env=p.env,capture_output=True,text=True)
            assert result.returncode==0 and result.stdout.strip()==expected
        for wrong in ('http://wrong.invalid', 'http://llmops-gitea-service:3000.evil.invalid',
                      'http://llmops-gitea-service:3000@evil.invalid'):
            assert subprocess.run([sys.executable,str(helper),"Password for '"+wrong+"':"],env=p.env,capture_output=True).returncode
        assert secret not in ' '.join(p.auth_args)
    assert not helper.exists() and m.PASSWORD_ENV not in p.env
    for f in (fixture[0]/'.git/genos-rag-auth').rglob('*'):
        if f.is_file():assert secret.encode() not in f.read_bytes()


def test_full_delivered_txt_applies_commits_and_pushes(fixture,tmp_path):
    f=fixture;dev=f[0];transfer=dev/'TRANSFER';name=NAME+'.zip'
    shutil.copyfile(OUT/name,transfer/name);shutil.copyfile(OUT/(NAME+'_RUN.txt'),transfer/(NAME+'_RUN.txt'))
    (dev/'01_DATA').mkdir();(dev/'01_DATA/preserve.txt').write_text('local original')
    (dev/'.env').write_text('UNRELATED=preserve')
    before=git(dev,'rev-parse','HEAD').stdout.strip()
    command=['bash','./'+NAME+'_RUN.txt','--root',str(dev)]
    run=subprocess.run(command,cwd=transfer,capture_output=True,text=True,timeout=180)
    assert run.returncode==0,run.stdout+run.stderr
    assert 'RAG_GIT_COMPLETE' in run.stdout and 'MAIN123_AUTO_GIT_EXIT=0' in run.stdout
    package=transfer/NAME;spec=json.loads((package/'PACKAGE.json').read_text())
    state=json.loads((package/'PUBLISH_STATE.json').read_text());commit=state['commit']
    assert state['status']=='complete' and state['generation_verified'] is False
    for p,h in spec['code'].items():assert m.digest((dev/p).read_bytes())==h
    changed=set(git(dev,'diff','--name-only',before,commit).stdout.splitlines())
    assert changed<=set(spec['code']) and len(changed)==492
    assert (dev/'.env').read_text()=='UNRELATED=preserve' and (dev/'01_DATA/preserve.txt').read_text()=='local original'
    assert '.env' not in git(dev,'ls-files').stdout.splitlines()
    for remote in f[2].values():assert git(Path(remote),'rev-parse','main').stdout.strip()==commit
    repeat=subprocess.run(command,cwd=transfer,capture_output=True,text=True,timeout=180)
    assert repeat.returncode==0,repeat.stdout+repeat.stderr
    assert git(dev,'rev-parse','HEAD').stdout.strip()==commit
    rollback=subprocess.run(command[:2]+['rollback',*command[2:]],cwd=transfer,capture_output=True,text=True,timeout=180)
    assert rollback.returncode!=0 and 'Git revert' in rollback.stdout
    with zipfile.ZipFile(OUT/name) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        assert all(Path(p).suffix.lower() not in {'.zip','.js','.jsx','.mjs','.cjs'} for p in z.namelist())
