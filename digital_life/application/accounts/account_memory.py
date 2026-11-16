"""Memory-domain administration, retaining source ACL intersections."""
from digital_life.application.accounts import account_scope as scope
from digital_life.application.accounts.accounts import AccountError
from digital_life.domain.contracts import Forbidden,Conflict


def listing(store,query):
    try:limit=int(query.get('limit',50));before=int(query.get('before',2**63-1))
    except (ValueError,TypeError):raise AccountError(422,'INVALID_PAGE','分页参数无效。')
    if not 1<=limit<=100 or before<1:raise AccountError(422,'INVALID_PAGE','分页参数无效。')
    rows=store.db.execute('SELECT m.rowid AS cursor,m.id,m.state,r.content,r.recorded_at FROM memory_items m JOIN memory_revisions r ON r.id=m.current_revision_id AND r.instance_id=m.instance_id WHERE m.instance_id=? AND m.rowid<? ORDER BY m.rowid DESC',(store.instance_id,before))
    items=[];cursor=None
    for row in rows:
        cursor=row['cursor']
        if row['state']=='active' and scope.can_recall(store,row['id']):items.append(dict(row,domain=scope.memory_domain(store,row['id'])))
        if len(items)==limit:break
    return {'items':items,'next_before':cursor,'policy_revision':store.db.execute('SELECT revision FROM acct_policy_state WHERE id=1').fetchone()[0]}


def change(store,principal,body):
    if principal['role'] not in ('root','admin'):raise Forbidden('only managers share memories')
    memory=body.get('memory_id');domain=body.get('domain')
    if domain not in ('private','shared'):raise AccountError(422,'INVALID_DOMAIN','只支持private或shared。')
    store.row('memory_items',memory)
    with store.tx():
        revision=store.db.execute('SELECT revision FROM acct_policy_state WHERE id=1').fetchone()[0]
        if body.get('expected_revision')!=revision:raise Conflict('memory domains changed')
        old=scope.memory_domain(store,memory)
        store.db.execute('INSERT OR REPLACE INTO acct_memory_domains VALUES(?,?,?,?)',(memory,domain,old['owner_account_id'],old['scope_tier']))
        store.db.execute('UPDATE acct_policy_state SET revision=revision+1 WHERE id=1')
        store.event('account.memory_domain_changed',payload={'memory':memory,'domain':domain,'actor':principal['id'],'revision':revision+1},lane='control')
    return {'memory_id':memory,'domain':domain,'policy_revision':revision+1}
