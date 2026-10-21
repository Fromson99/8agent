"""Local, rebuildable wiki projection of source-bound investigation experience.

SQLite owns identity, provenance and disconnection. Markdown is a human view;
editing it cannot approve a legal conclusion or reconnect a withdrawn edge.
No model calls, public export, runtime activation or answer injection occur here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import uuid

from lawrag.core.action_memory import Memory, digest, encoded


def key(ident):
    return digest(ident)


def inline(value):
    return str(value).replace('\n', ' ').replace('|', '\\|').replace('[', '\\[').replace(']', '\\]')


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def write(path, text, *, immutable=False):
    private_directory(path.parent)
    if path.exists():
        old = path.read_text(encoding='utf-8')
        if old == text:
            return False
        if immutable:
            raise ValueError('immutable wiki source changed: ' + str(path))
    tmp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with tmp.open('x', encoding='utf-8') as stream:
            tmp.chmod(0o600)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return True


@contextmanager
def locked(memory_directory):
    """Use the nightly builder's lock for DB changes and projection together."""
    private_directory(memory_directory)
    with (memory_directory / 'build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def projection(memory):
    """Take one consistent SQLite snapshot; never trust a stale Markdown page."""
    with memory.transaction():
        episodes = [dict(r) for r in memory.db.execute('SELECT * FROM episode ORDER BY id')]
        concepts = [dict(r) for r in memory.db.execute("SELECT * FROM concept WHERE kind='PURPOSE' ORDER BY id")]
        observations = [dict(r) for r in memory.db.execute('SELECT * FROM observation ORDER BY id')]
        states = [dict(r) for r in memory.db.execute('SELECT * FROM abstraction_state ORDER BY kind,id')]
        events = [dict(r) for r in memory.db.execute('SELECT * FROM event ORDER BY seq')]
    for e in episodes:
        e['payload'] = json.loads(e['payload_json'])
        if digest(e['payload']) != e['revision_hash']:
            raise ValueError('episode revision hash mismatch')
    return {'schema_version': 'legal-llm-wiki-v1', 'episodes': episodes,
            'concepts': concepts, 'observations': observations, 'states': states, 'events': events}


def export_wiki(memory, directory):
    """Compile existing LLM abstractions; preserve verbatim reasons in raw/."""
    directory = Path(directory)
    snapshot = projection(memory)
    snapshot_hash = digest(snapshot)
    private_directory(directory)
    manifest_path = directory / 'manifest.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    # Updated changes only when the snapshot changes, not on every nightly run.
    updated = previous.get('updated_at') if previous.get('snapshot_sha256') == snapshot_hash else datetime.now(timezone.utc).isoformat()
    episodes = {e['id']: e for e in snapshot['episodes']}
    states = {(s['kind'], s['id']): s for s in snapshot['states']}
    raw_names = {}
    files = {}

    def save(relative, text, immutable=False):
        write(directory / relative, text, immutable=immutable)
        files[relative] = digest(text)

    for ident, e in episodes.items():
        name = key(ident) + '-' + e['revision_hash'] + '.md'
        raw_names[ident] = name
        # Original question, rationale, sources, bindings and feedback stay verbatim.
        body = (f"# 조사 경험 {inline(ident)}\n\n> Source: native journal / action-memory episode\n"
                f"> Revision: {e['revision_hash']}\n> Truth: EXPERIENCE_ONLY\n\n"
                '이 기록은 당시 조사 경험이다. 완료 상태와 선택 결과는 법적 정답 인증이 아니다.\n\n'
                '<!-- BEGIN EPISODE JSON -->\n' + json.dumps(e['payload'], ensure_ascii=False, indent=2)
                + '\n<!-- END EPISODE JSON -->\n')
        save('raw/experiences/' + name, body, immutable=True)

    index = ['# legal_llm_wiki', '', '조사 목적·이유·원문 안내를 정리한 경험 위키. 법적 정답 인증과 온라인 재사용은 별도다.', '',
             '| 개념 | 정의 | 상태 | 유효 연결 | Updated |', '|---|---|---|---:|---|']
    active_count = 0
    for c in snapshot['concepts']:
        relations = [o for o in snapshot['observations'] if o['purpose_id'] == c['id']]
        concept_state = states.get(('concept', c['id']))
        status = concept_state['status'] if concept_state else 'EXPERIENCE_ONLY'
        raws = sorted({o['episode_id'] for o in relations})
        headers = [f"# {inline(c['label'])}", '', '> Sources: native investigation episodes',
                   '> Raw: ' + '; '.join(f'[{inline(eid)}](../../raw/experiences/{raw_names[eid]})' for eid in raws),
                   f'> Updated: {updated}', f"> Concept-ID: {c['id']}", f'> Status: {status}', '',
                   '## 추상화한 조사 목적', '', c['definition'], '',
                   '이 정의는 LLM이 조사 경험을 묶은 해석이다. 원문 사실이나 검증된 법적 결론으로 자동 승인하지 않는다.', '',
                   '## 적용 범위와 다시 확인할 것', '',
                   '각 연결의 원문 세대·문서·해시와 현재 권한을 확인해야 한다. 목적·사실관계·예외가 같은지는 새 질문에서 다시 판단한다. '
                   'GUIDES_TO는 탐색 안내이며 검색 범위를 제외하지 않는다. EXCLUDES의 PROPOSED도 제외하지 않는다.', '']
        if concept_state:
            headers += ['## 개념 연결 중단', '', f"{concept_state['status']}: {concept_state['reason']}",
                        f"처리자: {concept_state['reviewer']} / 시각: {concept_state['updated_at']}", '']
        valid_count = 0
        for o in relations:
            e = episodes[o['episode_id']]
            proof = json.loads(o['proof_json'])
            if digest(proof) != o['proof_hash']:
                raise ValueError('observation proof hash mismatch')
            withdrawal = states.get(('observation', o['id']))
            effective = withdrawal['status'] if withdrawal else o['status']
            if concept_state:
                effective = concept_state['status']
            elif e['state'] == 'NEGATIVE':
                effective = 'NEGATIVE'
            elif proof.get('episode_revision') != e['revision_hash']:
                effective = 'STALE'
            if effective == 'ACTIVE':
                valid_count += 1
            headers += [f"## 경험 연결 {o['id']}", '',
                        f"- 상태: {effective} / 관계: {o['predicate']}",
                        f"- 질문: {inline(e['payload']['question'])}",
                        f"- 기존 조사 이유: {inline(e['payload'].get('purpose_reason', ''))}",
                        f"- 원문 선택 이유: {inline(proof.get('selection_reason', proof.get('reason', '')))}",
                        f"- 이 개념으로 묶은 이유: {inline(proof.get('concept_reason', '미기록'))}",
                        f"- 세대 결속: {o['data_key']}",
                        f"- 문서 / 원문: {o['document_id']} / {o['source_id']}",
                        f"- 원문 해시: {o['origin_hash']}",
                        f"- [원자료](../../raw/experiences/{raw_names[o['episode_id']]})", '']
            if withdrawal:
                headers += [f"연결을 끊은 이유: {withdrawal['reason']}",
                            f"처리자: {withdrawal['reviewer']} / 시각: {withdrawal['updated_at']}", '']
        active_count += valid_count
        name = 'wiki/investigation/' + key(c['id']) + '.md'
        save(name, '\n'.join(headers) + '\n')
        index.append(f"| [{inline(c['label'])}](investigation/{key(c['id'])}.md) | {inline(c['definition'])} | {status} | {valid_count} | {updated} |")
    save('wiki/index.md', '\n'.join(index) + '\n')
    # Each export's underlying state is immutable, including observations that
    # an episode revision may later remove from the current SQLite projection.
    save('raw/snapshots/' + snapshot_hash + '.json', encoded(snapshot) + '\n', immutable=True)
    log = directory / 'wiki/log.md'
    if previous.get('snapshot_sha256') != snapshot_hash:
        private_directory(log.parent)
        with log.open('a', encoding='utf-8') as stream:
            log.chmod(0o600)
            if stream.tell() == 0:
                stream.write('# Wiki Log\n')
            stream.write(f'\n## {updated} compile\n- Snapshot: {snapshot_hash}\n'
                         f'- 원자료: ../raw/snapshots/{snapshot_hash}.json\n')
            stream.flush()
            os.fsync(stream.fileno())
    manifest = {'schema_version': 'legal-llm-wiki-v1', 'snapshot_sha256': snapshot_hash,
                'updated_at': updated, 'episodes': len(episodes), 'concepts': len(snapshot['concepts']),
                'active_relations': active_count, 'disconnections': len(states),
                'online_wired': False, 'legal_truth_certified': False, 'files': files}
    write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return {k: v for k, v in manifest.items() if k != 'files'}


def check_wiki(directory):
    """Mechanical integrity, never semantic certification."""
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    errors = []
    for relative, expected in manifest['files'].items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            errors.append(relative + ': missing or escaped file')
        elif digest(path.read_text(encoding='utf-8')) != expected:
            errors.append(relative + ': hash mismatch')
    return {'schema_version': 'legal-llm-wiki-check-v1', 'ok': not errors, 'errors': errors,
            'legal_truth_certified': False}


def operate(memory_directory, command, *, observation_id=None, concept_id=None,
            episode_id=None, reason='', reviewer='', status='RETRACTED'):
    memory_directory = Path(memory_directory)
    directory = memory_directory / 'legal_llm_wiki'
    if command == 'wiki-check':
        return check_wiki(directory)
    if command == 'wiki-status':
        manifest = directory / 'manifest.json'
        if not manifest.exists():
            return {'state': 'NOT_BUILT'}
        value = json.loads(manifest.read_text())
        value.pop('files', None)
        return value
    if not (memory_directory / 'memory.sqlite').is_file():
        raise ValueError('action-memory database is not built')
    with locked(memory_directory):
        memory = Memory(memory_directory / 'memory.sqlite')
        try:
            # Save evidence before changing the interpretation graph.
            export_wiki(memory, directory)
            if command == 'wiki-unlink':
                if observation_id:
                    ids = [observation_id]
                elif concept_id and episode_id:
                    ids = [r[0] for r in memory.db.execute(
                        'SELECT id FROM observation WHERE purpose_id=? AND episode_id=?', (concept_id, episode_id))]
                    if not ids:
                        raise ValueError('no experience links for this concept and episode')
                else:
                    raise ValueError('observation-id or concept-id + episode-id required')
                memory.disconnect_many('observation', ids, reason=reason, reviewer=reviewer, status=status)
            elif command == 'wiki-retire':
                memory.disconnect('concept', concept_id, reason=reason, reviewer=reviewer, status=status)
            elif command != 'wiki-export':
                raise ValueError('unknown wiki operation')
            return export_wiki(memory, directory)
        finally:
            memory.close()
