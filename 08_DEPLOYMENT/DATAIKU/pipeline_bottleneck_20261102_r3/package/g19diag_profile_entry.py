"""Run exactly one original stage with timing; never auto-retry or auto-advance."""
import os
from pathlib import Path
import sys
from g19diag_common import context, error, read, write
from g19diag_profiler import Recorder, install


def main(config):
    action = config['action']
    if action not in ('load', 'verify_publish', 'vector'): raise ValueError('PROFILE_ACTION_REQUIRED')
    ctx = context(config['old_job'], config['state_dir'], config['package_dir'])
    path = Path(config['output'])
    recorder = Recorder(path/'profile.json')
    sys.path.insert(0, ctx['package'])
    import run as loader
    if loader.verify_code() != ctx['state']['binding']['code']: raise ValueError('PROFILE_CODE_BINDING')
    # The original entrypoint enforces existing job lock, pending writes, deadline,
    # full input hashes and database identity. No reset or retry_missing override.
    os.environ['G19_OLD_JOB_DIR'] = ctx['job']
    os.environ['G19_DIAGNOSTIC_FILE'] = str(path/'original-errors.jsonl')
    os.environ.pop('G19_RETRY_MISSING', None)
    if action == 'vector':
        import dataiku
        import mesh_embedding
        settings = mesh_embedding.resolve_settings(os.environ, dataiku.get_custom_variables())
        os.environ['LEGAL_EMBED_LLM_ID'] = settings['model']
        os.environ['LEGAL_EMBED_DIMENSIONS'] = str(settings['dimensions'])
    install(loader, recorder)
    recorder.mode = action; recorder.table = 'VCTR_ITEM' if action == 'vector' else 'setup'
    write(path/'profile-binding.json', {'loader_code':ctx['state']['binding']['code'],
          'source_release':ctx['state']['binding']['source_release'], 'query_release':ctx['state']['binding']['query_release'],
          'stage':action, 'observer_only_code':True, 'original_files_modified':False})
    sys.argv = [str(Path(ctx['package'])/'pipeline_entry.py'), action]
    recorder.save()
    try:
        import pipeline_entry
        code = pipeline_entry.main()
        recorder.status = 'COMPLETE' if code == 0 else 'STOPPED'
        return code
    except BaseException as exc:
        recorder.status = 'STOPPED'; recorder.failure = error(exc); raise
    finally: recorder.save()


if __name__ == '__main__':
    raise SystemExit(main(read(sys.argv[1])))
