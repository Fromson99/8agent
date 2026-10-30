from pathlib import Path
exec((Path(__file__).parent/'check.py').read_text().split('class Results:')[0])
raise SystemExit(pytest.main(['--noconftest','-c','/dev/null','--confcutdir='+str(T),'-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(ART/'view-diagnostic'),str(T/'test_native_supervisor.py'),'-k','goal_control']))
