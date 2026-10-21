"""One declared metadata correction; immutable parent and shared read-only indexes."""
from pathlib import Path
import copy, hashlib, json, os, shutil, sqlite3, sys
from contextlib import closing

R = Path(__file__).resolve().parents[3]
A = R/'04_EXPERIMENTS/ADR/ADR-0792-risk-committee-team-metadata'
D = A/'artifacts/design'
sys.dont_write_bytecode = True
sys.path.insert(0, str(R/'02_BACKEND'))
from lawrag.platform.workspace import load_layout
from semantic_runtime.contracts import digest
from lawrag.pipeline.naming_definition_append import input_pins, shared_copy

def read(p): return json.loads(p.read_text())
def sha(p):
    with Path(p).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def put(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')

def main():
    layout = load_layout(R)
    criteria = read(D/'criteria.json')
    base = R/criteria['parent_generation']
    output = layout.path('data')/'TERM_RELEASES/risk-committee-team-metadata-20261015-r1'
    assert sha(base/'manifest.json') == criteria['parent_manifest_sha256']
    pins = input_pins(base)
    identity = {'parent_generation':str(base.relative_to(R)), 'parent_pins':pins,
                'criteria_sha256':sha(D/'criteria.json'), 'builder_sha256':sha(Path(__file__))}
    if output.exists():
        receipt = read(output/'result.json')
        assert receipt['identity'] == identity
        assert all(sha(output/n) == h for n,h in receipt['files'].items())
        print('Existing exact correction verified'); return
    attempt = output.with_name('.'+output.name+'.attempt')
    attempt.mkdir(exist_ok=False)
    try:
        generation = attempt/'generation'
        shutil.copytree(base, generation, copy_function=shared_copy)
        # Detach each mutable hardlink before writing.
        dbfile = generation/'store.sqlite'
        dbfile.unlink(); shutil.copyfile(base/'store.sqlite', dbfile)
        did = criteria['document_id']
        with closing(sqlite3.connect(dbfile)) as db:
            row = db.execute('SELECT json FROM document WHERE document_id=?',(did,)).fetchone()
            assert row is not None
            old = json.loads(row[0]); new = copy.deepcopy(old)
            metadata = new['document_metadata']
            assert metadata.get('team') is None
            assert metadata['source_metadata']['team'] == 'risk_team'
            assert metadata['source_metadata']['team_id'] == 'risk_team'
            metadata['team'] = 'risk_team'
            with db:
                assert db.execute('UPDATE document SET json=? WHERE document_id=?',
                    (json.dumps(new,ensure_ascii=False,separators=(',',':')),did)).rowcount == 1
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        correction = {'schema_version':'document-metadata-correction-v1', 'identity':identity,
                      'document_id':did, 'field':'document_metadata.team', 'before':None,
                      'after':'risk_team', 'basis':'Existing explicit source_metadata.team/team_id; user requested position correction',
                      'old_document_sha256':digest(old), 'new_document_sha256':digest(new),
                      'source_text_changed':False, 'acl_or_export_changed':False}
        put(attempt/'audit/correction.json',correction)
        sm = read(base/'manifest.json'); sm.pop('navigation'); sm.pop('fulltext',None)
        sm.update(generation_id='term-metadata-'+digest(identity)[:20],store_sha256=sha(dbfile),
                  metadata_correction={'receipt_sha256':sha(attempt/'audit/correction.json'),
                                       'parent_manifest_sha256':pins['manifest.json']})
        nm = read(base/'navigation/manifest.json')
        nm.update(generation_id=sm['generation_id'],source_store_sha256=sm['store_sha256'],source_manifest_sha256=digest(sm))
        (generation/'navigation/manifest.json').unlink();put(generation/'navigation/manifest.json',nm)
        sm['navigation']={'path':'navigation','manifest_sha256':sha(generation/'navigation/manifest.json')}
        put(attempt/'source-stage.json',sm)
        fm=read(base/'fulltext/manifest.json')
        fm.update(generation_id=sm['generation_id'],source_store_sha256=sm['store_sha256'],
                  source_manifest_sha256=sha(attempt/'source-stage.json'),navigation_manifest_sha256=sm['navigation']['manifest_sha256'])
        (generation/'fulltext/manifest.json').unlink();put(generation/'fulltext/manifest.json',fm)
        sm['fulltext']={'path':'fulltext','manifest_sha256':sha(generation/'fulltext/manifest.json'),
                        'navigation_index_sha256':nm['index_sha256']}
        (generation/'manifest.json').unlink();put(generation/'manifest.json',sm)
        assert input_pins(base)==pins
        files={str(p.relative_to(attempt)):sha(p) for p in [attempt/'audit/correction.json',attempt/'source-stage.json',
            generation/'manifest.json',dbfile,generation/'navigation/manifest.json',generation/'fulltext/manifest.json']}
        put(attempt/'result.json',{'identity':identity,'files':files,'generation_id':sm['generation_id'],
            'reparsed_documents':0,'retokenized_documents':0,'model_calls':0,'activated':False})
        os.rename(attempt,output)
        put(D/'data-binding.json',{'path':str((output/'generation').relative_to(R)),
            'manifest_sha256':sha(output/'generation/manifest.json'),'generation_id':sm['generation_id'],
            'store_sha256':sm['store_sha256'],'correction_receipt':str((output/'audit/correction.json').relative_to(R))})
        print(json.dumps({'generation':str(output.relative_to(R)),'corrected_documents':1,'model_calls':0}))
    except BaseException as error:
        put(attempt/'failure.json',{'error_type':type(error).__name__,'error':str(error),'identity':identity,'published':False})
        raise

if __name__=='__main__': main()
