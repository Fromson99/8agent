"""Conservative linking proposals. Names and similar topics never merge facts."""
from .corrected_memory import MemoryError


def propose(repo, principal, *, session, explicit=None):
    if explicit:
        value=repo.investigation(explicit,principal,session)
        if not principal.get('authenticated'):raise MemoryError('cross-session access denied')
        return {'status':'EXPLICIT','investigation_id':value['id'],'reason':'authorized explicit reference'}
    scope=repo.scope(principal,session)
    rows=list(repo.db.execute('SELECT DISTINCT investigation FROM sw_session_link WHERE scope=? AND session=? AND detached IS NULL',(scope,session)))
    accessible=[]
    for row in rows:
        try:accessible.append(repo.investigation(row[0],principal,session)['id'])
        except MemoryError:continue
    return {'status':'CANDIDATES' if accessible else 'NEW','investigation_ids':accessible,'automatic_merge':False}
