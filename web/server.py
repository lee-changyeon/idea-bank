"""아이디어뱅크 온라인 — 사용자 웹 앱 (창안자·사업자). 포트 8090.

실행: python web/server.py   (또는 run_web.bat)
"""
from __future__ import annotations

import base64
import hmac
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ibweb import config, ledger as L, proof, security as S, service as svc  # noqa: E402
from ibweb.db import open_db  # noqa: E402
from ibweb.httpkit import ON_VERCEL, App, HttpError, Response, bad, download, forbidden  # noqa: E402

HERE = Path(__file__).resolve().parent
CFG = config.load()
db = open_db()  # DATABASE_URL 이 있으면 Postgres(Supabase), 없으면 web/data 의 SQLite
# 온라인(Vercel)에는 백그라운드 스레드가 없으므로 요청 끝에서 바로 공인 시각을 받고, 놓친 것은 Cron 이 처리
stamper = L.Stamper(db, CFG["tsa_urls"], inline=ON_VERCEL)
app = App("아이디어뱅크 웹", db, "user", "ib_sess", [HERE / "static"])
throttle = S.Throttle(db=db)


def me(req):
    return {"user": svc.public_user(req.user) if req.user else None, "csrf": req.session["csrf"] if req.session else None,
            "limits": svc.LIMITS}


# ── 계정 ──
@app.route("GET", "/api/me")
def r_me(req):
    return me(req)


@app.route("POST", "/api/signup")
def r_signup(req):
    u = svc.signup(db, req.get("email"), req.get("password"), req.get("name"), req.get("role"), req.get("org"))
    token, csrf = S.new_session(db, "user", u["id"])
    return {"user": svc.public_user(u), "csrf": csrf}, app.set_cookie(token)


@app.route("POST", "/api/login")
def r_login(req):
    email = str(req.get("email")).strip().lower()
    key = f"{req.ip}|{email}"
    if throttle.blocked(key):
        raise HttpError(429, "로그인 실패가 많아 10분 동안 잠겼습니다.")
    u = svc.authenticate(db, "users", "email", email, str(req.get("password")))
    if not u:
        throttle.fail(key)
        raise HttpError(401, "이메일 또는 비밀번호가 맞지 않습니다.")
    if u["status"] != "active":
        raise HttpError(403, "이용이 정지된 계정입니다. 운영팀에 문의해 주세요.")
    throttle.clear(key)
    S.end_session(db, app._cookie(req.h))  # 세션 고정 방지: 로그인 때마다 새 토큰
    token, csrf = S.new_session(db, "user", u["id"])
    return {"user": svc.public_user(u), "csrf": csrf}, app.set_cookie(token)


@app.route("POST", "/api/logout")
def r_logout(req):
    S.end_session(db, app._cookie(req.h))
    return {"ok": True}, app.set_cookie(None)


# ── 공개 (로그인 없이) ──
@app.route("GET", "/api/ledger")
def r_ledger(req):
    return svc.ledger_status(db)


@app.route("GET", "/api/ledger/verify")
def r_ledger_verify(req):
    """원장 무결성 검사 (누구나). 순번·고유 지문·고리값·공인 시각·첨부 해시만 검사하고 내용은 돌려주지 않는다."""
    out = L.verify_chain(db)
    return {k: out[k] for k in ("ok", "count", "head", "pending", "broken", "checked_at")}


@app.route("GET", "/api/cron/tsa")
def r_cron_tsa(req):
    """Vercel Cron(매일 03:00 UTC, vercel.json): 공인 시각을 못 받은 이벤트를 다시 시도. Authorization: Bearer <CRON_SECRET> 일 때만."""
    secret = os.environ.get("CRON_SECRET", "")
    got = req.h.headers.get("Authorization") or ""
    if not secret or not hmac.compare_digest(got, f"Bearer {secret}"):
        raise forbidden()
    return stamper.run_pending(limit=40, deadline=time.monotonic() + 50)


@app.route("GET", "/api/lookup/{h}")
def r_lookup(req):
    return svc.lookup(db, req.params["h"])


@app.route("POST", "/api/verify/bundle")
def r_verify(req):
    try:
        data = base64.b64decode(req.get("zip_b64"), validate=True)
    except Exception:
        raise bad("파일을 읽을 수 없습니다.")
    try:
        return proof.verify(db, data)
    except ValueError as e:  # ideabank.store.UserError
        raise bad(str(e))


# ── 창안자 ──
@app.route("GET", "/api/my/ideas", auth="creator")
def r_my_ideas(req):
    return {"ideas": svc.my_ideas(db, req.user, req.query.get("q", "").strip())}


@app.route("POST", "/api/my/ideas", auth="creator")
def r_create(req):
    j = req.json
    d = svc.create_idea(db, stamper, req.user, title=j.get("title"), body=j.get("body"), tags=j.get("tags") or [],
                        attachments=j.get("attachments") or [], parent_seq=j.get("parent_seq"),
                        disclosure=j.get("disclosure") or "private", summary=j.get("summary") or "",
                        timestamp=j.get("timestamp", True) is not False)
    return svc.strip_bytes(d)


@app.route("GET", "/api/my/ideas/{seq}", auth="creator")
def r_my_idea(req):
    return svc.idea_detail_for_owner(db, req.user, req.params["seq"])


@app.route("POST", "/api/my/ideas/{seq}/disclosure", auth="creator")
def r_disclosure(req):
    return svc.set_disclosure(db, stamper, req.user, req.params["seq"], req.get("level"), req.get("summary"))


@app.route("POST", "/api/my/ideas/{seq}/timestamp", auth="creator")
def r_restamp(req):
    return svc.restamp(db, stamper, req.user, req.params["seq"])


@app.route("GET", "/api/my/ideas/{seq}/bundle", auth="creator")
def r_bundle(req):
    name, data = proof.make(db, svc.own_idea(db, req.user, req.params["seq"]))
    return download(data, name, "application/zip")


@app.route("GET", "/api/my/ideas/{seq}/files/{sha}", auth="creator")
def r_my_file(req):
    svc.own_idea(db, req.user, req.params["seq"])
    a, data = svc.attachment(db, req.params["seq"], req.params["sha"])
    return download(data, a["name"])


@app.route("GET", "/api/my/views", auth="creator")
def r_my_views(req):
    return {"views": svc.my_views(db, req.user)}


@app.route("GET", "/api/my/loans", auth="creator")
def r_my_loans(req):
    return {"loans": svc.creator_loans(db, req.user), "contracts": svc.user_contracts(db, req.user)}


@app.route("POST", "/api/my/loans/{id}/respond", auth="creator")
def r_respond(req):
    return svc.creator_respond(db, stamper, req.user, req.params["id"], bool(req.get("accept")), req.get("note"))


# ── 사업자 ──
@app.route("GET", "/api/market", auth="business")
def r_market(req):
    return {"ideas": svc.market(db, req.user, req.query.get("q", "").strip(), req.query.get("tag", "").strip())}


@app.route("GET", "/api/market/{seq}", auth="business")
def r_market_one(req):
    return svc.market_detail(db, stamper, req.user, req.params["seq"])


@app.route("GET", "/api/market/{seq}/full", auth="business")
def r_market_full(req):
    return svc.market_full(db, stamper, req.user, req.params["seq"])


@app.route("GET", "/api/market/{seq}/files/{sha}", auth="business")
def r_market_file(req):
    a, data = svc.market_file(db, stamper, req.user, req.params["seq"], req.params["sha"])
    return download(data, a["name"])


@app.route("POST", "/api/market/{seq}/nda", auth="business")
def r_nda(req):
    return svc.sign_nda(db, stamper, req.user, req.params["seq"], req.get("signer_name"), bool(req.get("agree")),
                        req.get("template_hash"), req.ip)


@app.route("POST", "/api/market/{seq}/loan", auth="business")
def r_loan(req):
    return svc.request_loan(db, stamper, req.user, req.params["seq"], req.json)


@app.route("GET", "/api/biz/activity", auth="business")
def r_biz(req):
    return {"ndas": svc.my_ndas(db, req.user), "loans": svc.biz_loans(db, req.user),
            "contracts": svc.user_contracts(db, req.user)}


if __name__ == "__main__":
    from ibweb.launcher import prepare
    prepare(sys.argv[1:], db, int(CFG["web_port"]), "사용자 웹")
    stamper.start_worker()
    app.serve(CFG["host"], int(CFG["web_port"]))
