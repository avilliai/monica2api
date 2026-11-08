"""Cookie/account administration endpoints and the local dashboard."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from app.core.dependencies import get_auth_token, get_cookie_manager
from app.services.cookie_manager import CookieManager
from app.services.monica_auth import MonicaAuthClient, MonicaAuthError

router = APIRouter()

class CookieAddRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)

class AccountsAddRequest(BaseModel):
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    email: str | None = None
    password: str | None = None
    cookie: str | None = None
    cookie_header: str | None = None
    disabled: bool = False
    probe: bool = False

class AccountLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)

class IdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


def _account_items(body: AccountsAddRequest) -> list[dict[str, Any]]:
    items = list(body.accounts)
    if body.email:
        items.append({"email": body.email, "password": body.password or "",
                      "cookie": body.cookie or body.cookie_header or "",
                      "disabled": body.disabled})
    return items


def _payload_cookie(data: Any) -> str:
    """Extract an explicitly named cookie header from an auth payload."""
    if isinstance(data, dict):
        for key in ("cookie_header", "cookie", "session_cookie"):
            value = data.get(key)
            if isinstance(value, str) and "=" in value:
                return value.strip()
            if isinstance(value, dict):
                return "; ".join(f"{k}={v}" for k, v in value.items())
        for key in ("data", "result", "user"):
            found = _payload_cookie(data.get(key))
            if found:
                return found
    return ""

def _safe_user(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    value = data.get("data") or data.get("user") or data.get("result") or data
    if not isinstance(value, dict):
        return {}
    allowed = ("id", "uid", "user_id", "email", "name", "nickname", "avatar")
    return {key: value[key] for key in allowed if value.get(key) is not None}


DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monica2API Dashboard</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#121a2e;--panel2:#18233c;--line:#2b3b60;--text:#e8eefc;--muted:#9eacc9;--accent:#6ea8fe;--ok:#55d187;--bad:#ff7d8d}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#1d3158 0,#0b1020 46%);color:var(--text);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:1220px;margin:auto;padding:28px 18px 60px}h1{margin:0 0 4px;font-size:28px}h2{font-size:17px;margin:0 0 14px}.sub,.hint,.footer{color:var(--muted)}.sub{margin:0 0 22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 12px 30px #0003}.wide{grid-column:1/-1}.topline{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}label{display:block;color:var(--muted);font-size:12px;margin:10px 0 5px}input{width:100%;border:1px solid var(--line);border-radius:8px;background:#0b1327;color:var(--text);padding:10px 11px;outline:0}input:focus{border-color:var(--accent)}button{border:0;border-radius:8px;background:var(--accent);color:#07101f;padding:9px 13px;font-weight:650;cursor:pointer;margin:10px 6px 0 0}button.secondary{background:#2a3a5e;color:var(--text)}button.danger{background:#7e3042;color:#fff}button.small{padding:5px 8px;font-size:12px;margin:2px}.message{min-height:22px;margin-top:10px;color:var(--muted)}.message.ok{color:var(--ok)}.message.error{color:var(--bad)}.api-row{display:flex;gap:8px;align-items:end}.api-row label{flex:1;margin:0}.api-row button{margin:0}.stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}.stat{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:9px 13px;min-width:120px}.stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:12px}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;min-width:790px}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid #263453;vertical-align:middle}th{color:var(--muted);font-size:12px;background:#101a31}tr:last-child td{border:0}.badge{display:inline-block;border-radius:999px;padding:3px 8px;font-size:12px}.alive{background:#174b36;color:#8bf0b1}.dead{background:#54293a;color:#ffadb7}.off{background:#41495c;color:#c4ccdc}.footer{margin-top:18px;font-size:12px}
</style></head><body><main>
<div class="topline"><div><h1>Monica2API</h1><p class="sub">本地账号池 · HTTP 对话 · 每个账号每天 40 次 · Asia/Shanghai 零点刷新</p></div><button class="secondary" onclick="loadAccounts()">刷新状态</button></div>
<section class="panel wide"><h2>服务密钥</h2><div class="api-row"><label>API Key<input id="apiKey" type="password" autocomplete="off" placeholder="输入 .env 中的 API_KEY"></label><button onclick="saveKey()">保存</button><button class="secondary" onclick="clearKey()">清除</button></div><div class="hint">密钥只保存在当前浏览器 localStorage。</div><div id="globalMsg" class="message"></div></section>
<div class="grid" style="margin-top:16px"><section class="panel"><h2>登录 Monica 账号</h2><form onsubmit="loginAccount(event)"><label>邮箱<input id="loginEmail" type="email" required autocomplete="username"></label><label>密码<input id="loginPassword" type="password" required autocomplete="current-password"></label><button type="submit">登录并加入账号池</button></form><div class="hint">登录、对话和保活均使用普通 HTTP，不启动浏览器。</div><div id="loginMsg" class="message"></div></section>
<section class="panel"><h2>手动添加 Cookie</h2><form onsubmit="addCookie(event)"><label>邮箱（可选）<input id="cookieEmail" type="email"></label><label>密码（可选）<input id="cookiePassword" type="password"></label><label>Cookie Header<input id="cookieValue" required placeholder="name=value; other=value"></label><button type="submit">添加 Cookie</button></form><div id="cookieMsg" class="message"></div></section></div>
<section class="panel wide" style="margin-top:16px"><div class="topline"><h2>账号池</h2><div><button class="secondary" onclick="refreshAll()">刷新全部</button><button class="secondary" onclick="resetQuotas()">重置本地额度</button></div></div><div id="stats" class="stats"></div><div class="table-wrap"><table><thead><tr><th>邮箱</th><th>状态</th><th>今日调用</th><th>额度日期</th><th>最近检查</th><th>操作</th></tr></thead><tbody id="accounts"><tr><td colspan="6" class="hint">正在加载…</td></tr></tbody></table></div><div id="tableMsg" class="message"></div></section>
<p class="footer">每日额度是本地轮询限制；上游 HTTP 失败会归还预占次数。Cookie 仅以脱敏信息显示。</p></main>
<script>
const KEY_NAME='monica2api_api_key',$=id=>document.getElementById(id);function key(){return $('apiKey').value.trim()||localStorage.getItem(KEY_NAME)||''}function saveKey(){const v=$('apiKey').value.trim();v?localStorage.setItem(KEY_NAME,v):localStorage.removeItem(KEY_NAME);msg('globalMsg',v?'密钥已保存':'已清除密钥','ok')}function clearKey(){$('apiKey').value='';localStorage.removeItem(KEY_NAME);msg('globalMsg','已清除密钥','ok')}function msg(id,t,k=''){const e=$(id);e.textContent=t;e.className='message '+k}function headers(json=true){const h={};const k=key();if(k)h.Authorization=/^Bearer\s/i.test(k)?k:'Bearer '+k;if(json)h['content-type']='application/json';return h}
async function call(url,opt={}){opt.headers=Object.assign(headers(opt.body!==undefined),opt.headers||{});const r=await fetch(url,opt);let d;try{d=await r.json()}catch(_){d={detail:await r.text()}}if(!r.ok)throw Error(d?.detail||d?.error?.message||('HTTP '+r.status));return d}function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function render(d){const s=d.summary||{};$('stats').innerHTML=[['账号',s.total||0],['在线',s.alive||0],['停用',s.disabled||0],['失效',s.dead||0]].map(x=>`<div class="stat"><b>${x[1]}</b><span>${x[0]}</span></div>`).join('');const rows=d.accounts||[];$('accounts').innerHTML=rows.length?rows.map(a=>{const st=a.disabled?'<span class="badge off">停用</span>':a.is_alive?'<span class="badge alive">在线</span>':'<span class="badge dead">失效</span>';return `<tr><td>${esc(a.email)}<br><span class="hint">${esc(a.cookie_hint||'')}</span></td><td>${st}</td><td><b>${a.daily_used||0}</b> / ${a.daily_limit||40}<br><span class="hint">剩余 ${a.daily_remaining??0}</span></td><td>${esc(a.quota_date||'')}</td><td>${a.last_checked_at?new Date(a.last_checked_at*1000).toLocaleString():'—'}</td><td><button class="small secondary" onclick="refreshOne(${a.id})">刷新</button>${a.disabled?`<button class="small" onclick="setEnabled(${a.id},true)">启用</button>`:`<button class="small secondary" onclick="setEnabled(${a.id},false)">停用</button>`}<button class="small danger" onclick="removeAccount(${a.id})">删除</button></td></tr>`}).join(''):'<tr><td colspan="6" class="hint">暂无账号，请先登录或添加 Cookie。</td></tr>'}
async function loadAccounts(){try{render(await call('/admin/accounts/detail'));msg('tableMsg','状态已更新','ok')}catch(e){msg('tableMsg',e.message,'error')}}async function loginAccount(ev){ev.preventDefault();msg('loginMsg','登录中…');try{const d=await call('/admin/accounts/login',{method:'POST',body:JSON.stringify({email:$('loginEmail').value.trim(),password:$('loginPassword').value})});msg('loginMsg','已加入：'+(d.account?.email||''),'ok');$('loginPassword').value='';await loadAccounts()}catch(e){msg('loginMsg',e.message,'error')}}async function addCookie(ev){ev.preventDefault();msg('cookieMsg','保存中…');try{await call('/admin/accounts/add',{method:'POST',body:JSON.stringify({accounts:[{email:$('cookieEmail').value.trim(),password:$('cookiePassword').value,cookie:$('cookieValue').value.trim()}]})});msg('cookieMsg','Cookie 已加入','ok');$('cookieValue').value='';await loadAccounts()}catch(e){msg('cookieMsg',e.message,'error')}}async function refreshAll(){msg('tableMsg','刷新中…');try{await call('/admin/accounts/refresh',{method:'POST'});await loadAccounts()}catch(e){msg('tableMsg',e.message,'error')}}async function refreshOne(id){try{await call('/admin/cookies/'+id+'/refresh',{method:'POST'});await loadAccounts()}catch(e){msg('tableMsg',e.message,'error')}}async function setEnabled(id,on){try{await call('/admin/accounts/'+(on?'enable':'disable'),{method:'POST',body:JSON.stringify({ids:[id]})});await loadAccounts()}catch(e){msg('tableMsg',e.message,'error')}}async function removeAccount(id){if(!confirm('确定删除这个账号？'))return;try{await call('/admin/accounts/'+id,{method:'DELETE'});await loadAccounts()}catch(e){msg('tableMsg',e.message,'error')}}async function resetQuotas(){try{const d=await call('/admin/accounts/reset-quotas',{method:'POST',body:JSON.stringify({force:true})});msg('tableMsg','已重置 '+(d.changed||0)+' 个账号','ok');await loadAccounts()}catch(e){msg('tableMsg',e.message,'error')}}(function(){const v=localStorage.getItem(KEY_NAME);if(v)$('apiKey').value=v;loadAccounts()})();
</script></body></html>"""


TEMPLATE_PATH = Path(__file__).resolve().parents[2] / 'templates' / 'dashboard.html'


@router.get('/dashboard', response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    if TEMPLATE_PATH.is_file():
        return HTMLResponse(TEMPLATE_PATH.read_text(encoding='utf-8'))
    return HTMLResponse(DASHBOARD_HTML)

@router.get("", include_in_schema=False)
async def admin_root():
    return RedirectResponse(url="/admin/dashboard")

@router.get("/cookies")
async def get_cookies_summary(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    reset = getattr(manager, "reset_daily_quotas", None)
    if reset:
        await reset(force=False)
    return {"summary": manager.summary(), "cookies": manager.detail()}

@router.post("/cookies/reload")
async def reload_cookies(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    await manager.load(probe=False)
    return {"message": "Cookie file reloaded", "summary": manager.summary()}

@router.post("/cookies/refresh")
async def refresh_cookies(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    result = await manager.refresh_all()
    return {"message": "Cookie refresh completed", "result": result, "summary": manager.summary()}

@router.post("/cookies/add")
async def add_cookies(body: CookieAddRequest, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    result = await manager.add(body.items)
    return {"message": "Cookie entries saved", "result": result, "summary": manager.summary()}

@router.post("/cookies/{cookie_id}/refresh")
async def refresh_one_cookie(cookie_id: int, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    entry = await manager.refresh_one(cookie_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie not found")
    return {"message": "Cookie refreshed", "cookie": manager.public_info(entry)}

@router.get("/cookies/{cookie_id}/connection-token")
async def connection_token(cookie_id: int, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    entry = await manager.get_by_id(cookie_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie not found")
    return await MonicaAuthClient().get_connection_token(entry["cookie"])

@router.get("/cookies/{cookie_id}/quota")
async def cookie_quota(cookie_id: int, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    data = await manager.fetch_quota(cookie_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Cookie not found")
    return data

@router.get("/accounts")
async def account_summary(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    return manager.summary()

@router.get("/accounts/detail")
async def account_detail(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    reset = getattr(manager, "reset_daily_quotas", None)
    if reset:
        await reset(force=False)
    return {"summary": manager.summary(), "accounts": manager.detail(),
            "daily_limit": getattr(manager, "daily_limit", 40), "quota_timezone": getattr(manager, "quota_timezone", "Asia/Shanghai")}

@router.get("/accounts/export")
async def account_export(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    return {"accounts": manager.detail(include_secrets=True)}

@router.post("/accounts/login")
@router.post("/cookies/login")
async def account_login(body: AccountLoginRequest, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    client = MonicaAuthClient()
    try:
        result = await client.login_by_email(email=body.email.strip(), password=body.password)
        session_cookie = result.cookie_header or _payload_cookie(result.payload)
        if not session_cookie:
            raise MonicaAuthError("Monica login did not return a session cookie", 502)
        # A second ordinary HTTP call confirms that the cookie is usable before
        # it enters the pool.  It does not invoke Camoufox or reCAPTCHA.
        user = await client.me(session_cookie)
        await manager.add([{
            "email": body.email.strip(),
            "password": body.password,
            "cookie": session_cookie,
            "metadata": {
                "client_id": getattr(client, "client_id", ""),
                "user_agent": (getattr(client, "headers", {}) or {}).get("user-agent", ""),
            },
        }], probe=False)
        entry = await manager.get_by_email(body.email.strip())
        return {"status": "ok", "account": manager.public_info(entry or {}), "user": _safe_user(user)}
    except MonicaAuthError as exc:
        detail = str(exc)
        lowered = detail.lower()
        if exc.status_code in (401, 403) or any(word in lowered for word in ("password", "credential", "authentication", "login failed")):
            status = 401
        elif exc.status_code and 400 <= exc.status_code < 600:
            status = exc.status_code
        else:
            status = 502
        raise HTTPException(status_code=status, detail=detail) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Monica login request failed: {exc}") from exc

@router.post("/accounts/add")
async def accounts_add(body: AccountsAddRequest, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    items = _account_items(body)
    result = await manager.add(items, probe=body.probe)
    return {"status": "ok", **result, **manager.summary()}

@router.post("/accounts/refresh")
async def accounts_refresh(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    result = await manager.refresh_all()
    return {"status": "ok", **result}

@router.post("/accounts/reset-quotas")
@router.post("/cookies/reset-quotas")
async def accounts_reset_quotas(manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    changed = await manager.reset_daily_quotas(force=True)
    return {"status": "ok", "changed": changed, "quota_date": manager._today()}

@router.post("/accounts/disable")
async def accounts_disable(body: IdsRequest, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    changed = await manager.set_disabled(body.ids, True)
    return {"status": "ok", "changed": changed, **manager.summary()}

@router.post("/accounts/enable")
async def accounts_enable(body: IdsRequest, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    changed = await manager.set_disabled(body.ids, False)
    return {"status": "ok", "changed": changed, **manager.summary()}

@router.delete("/accounts/{account_id}")
async def accounts_delete(account_id: int, manager: CookieManager = Depends(get_cookie_manager), _: str = Depends(get_auth_token)):
    if not await manager.remove(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "ok", **manager.summary()}













