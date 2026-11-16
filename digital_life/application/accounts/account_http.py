"""Authenticated account routes; None delegates only for root."""
import re
from digital_life.application.accounts import account_scope as scope
from digital_life.application.chat.chat import Chat
from digital_life.application.monitoring.thought_inspection import ThoughtInspection
from digital_life.domain.contracts import Forbidden


def dispatch(store,auth,principal,method,route,body,query,bearer):
    manager=principal['role'] in ('root','admin')
    if route=='/v1/auth/logout' and method=='POST':return 200,auth.logout(bearer)
    if route=='/v1/account/password' and method=='POST':return 200,auth.change_password(principal,principal['id'],body.get('new_password'),body.get('current_password'))
    if route=='/v1/accounts':
        if method=='GET':return 200,auth.list(principal)
        if method=='POST':return 201,auth.provision(store,principal,body)
    match=re.fullmatch(r'/v1/accounts/([a-f0-9]{32})(/password)?',route)
    if match and method=='POST':
        return 200,auth.change_password(principal,match[1],body.get('new_password')) if match[2] else auth.update(principal,match[1],body)
    from digital_life.application.accounts import account_memory as account_memory
    if route=='/v1/account/memories' and method=='GET':return 200,account_memory.listing(store,query)
    if route=='/v1/account/memories/domain' and method=='POST':return 200,account_memory.change(store,principal,body)
    if route=='/v1/chats' and method=='GET':return 200,Chat(store).list()
    if route=='/v1/conversation':
        if method=='GET':return 200,Chat(store).detail(principal['thread_id'])
        if method=='POST':return 202,Chat(store).send(principal['thread_id'],body)
    match=re.fullmatch(r'/v1/chats/([A-Za-z0-9_-]{1,64})(/messages)?',route)
    if match:
        if method=='GET' and not match[2]:return 200,Chat(store).detail(match[1])
        if method=='POST' and match[2]:return 202,Chat(store).send(match[1],body)
        raise Forbidden('unsupported conversation operation')
    thought=re.fullmatch(r'/v1/thoughts/([A-Za-z0-9_-]{1,128})',route)
    thoughts=re.fullmatch(r'/v1/activities/([A-Za-z0-9_-]{1,128})/thoughts',route)
    if method=='GET' and (thought or thoughts):
        activity=store.row('thought_requests',thought[1])['activity_id'] if thought else thoughts[1]
        if not scope.visible_activity(store,activity):raise Forbidden('thought is private')
        return 200,ThoughtInspection(store).detail(thought[1]) if thought else ThoughtInspection(store).list(activity)
    if principal['role']!='root':raise Forbidden('root required for system interfaces')
    return None
