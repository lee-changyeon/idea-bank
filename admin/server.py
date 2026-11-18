"""아이디어뱅크 온라인 — 관리자 사이트. 포트 8091.

사용자 앱과 같은 DB·원장을 쓰지만 로그인(admins 테이블, ib_admin 쿠키)은 완전히 분리되어 있다.
실행: python admin/server.py   (또는 run_admin.bat)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "web"))

from ibweb import config, ledger as L, security as S, service as svc  # noqa: E402
from ibweb.db import DB  # noqa: E402
from ibweb.httpkit import App, HttpError, notfound  # noqa: E402

CFG = config.load()
db = DB()
stamper = L.Stamper(db, CFG["tsa_urls"])
# 관리자 정적 파일 먼저, 공용 CSS·로고는 web/static 에서
app = App("아이디어뱅크 관리자", db, "admin", "ib_admin", [HERE / "static", HERE.parent / "web" / "static"])
throttle = S.Throttle()


def admin_public(a):
    return {"id": a["id"], "username": a["username"], "name": a["name"]}


@app.route("GET", "/api/me")
def r_me(req):
    return {"admin": admin_public(req.user) if req.user else None, "csrf": req.session["csrf"] if req.session else None}


@app.route("POST", "/api/login")
def r_login(req):
    username = str(req.get("username")).strip()
    key = f"{req.ip}|{username}"
    if throttle.blocked(key):
        raise HttpError(429, "로그인 실패가 많아 10분 동안 잠겼습니다.")
    a = svc.authenticate(db, "admins", "username", username, str(req.get("password")))
    if not a:
        throttle.fail(key)
        svc.audit(db, None, "관리자 로그인 실패", username, {}, req.ip)
        raise HttpError(401, "아이디 또는 비밀번호가 맞지 않습니다.")
    throttle.clear(key)
    S.end_session(db, app._cookie(req.h))
    token, csrf = S.new_session(db, "admin", a["id"])
    svc.audit(db, a, "로그인", "", {}, req.ip)
    return {"admin": admin_public(a), "csrf": csrf}, app.set_cookie(token)


@app.route("POST", "/api/logout")
def r_logout(req):
    if req.user:
        svc.audit(db, req.user, "로그아웃", "", {}, req.ip)
    S.end_session(db, app._cookie(req.h))
    return {"ok": True}, app.set_cookie(None)


@app.route("POST", "/api/password", auth="admin")
def r_password(req):
    """로그인한 관리자가 자기 비밀번호를 바꾼다. 현재 비밀번호 확인 필수, 다른 기기의 세션은 끊는다."""
    a = req.user
    key = f"{req.ip}|pw|{a['id']}"
    if throttle.blocked(key):
        raise HttpError(429, "비밀번호 확인 실패가 많아 10분 동안 잠겼습니다.")
    current, new = str(req.get("current_password") or ""), str(req.get("new_password") or "")
    if not S.check_password(current, a["pw"]):
        throttle.fail(key)
        svc.audit(db, a, "비밀번호 변경 실패", a["username"], {"reason": "현재 비밀번호 불일치"}, req.ip)
        raise HttpError(400, "현재 비밀번호가 맞지 않습니다.")
    throttle.clear(key)
    if len(new) < 8:
        raise HttpError(400, "새 비밀번호는 8자 이상으로 정해 주세요.")
    if new == current:
        raise HttpError(400, "새 비밀번호가 지금 비밀번호와 같습니다.")
    db.exec("UPDATE admins SET pw=? WHERE id=?", (S.hash_password(new), a["id"]))
    db.exec("DELETE FROM sessions WHERE kind='admin' AND subject_id=? AND token_hash!=?", (a["id"], req.session["token_hash"]))
    svc.audit(db, a, "비밀번호 변경", a["username"], {}, req.ip)
    return {"ok": True}


# ── 대시보드·원장 ──
@app.route("GET", "/api/dashboard", auth="admin")
def r_dash(req):
    c = lambda sql, a=(): db.val(sql, a)  # noqa: E731
    return {
        "users": {"creator": c("SELECT COUNT(*) FROM users WHERE role='creator'"),
                  "business": c("SELECT COUNT(*) FROM users WHERE role='business'"),
                  "suspended": c("SELECT COUNT(*) FROM users WHERE status!='active'")},
        "ideas": {"total": c("SELECT COUNT(*) FROM ideas"),
                  "listed": c("SELECT COUNT(*) FROM ideas WHERE disclosure!='private' AND hidden=0"),
                  "hidden": c("SELECT COUNT(*) FROM ideas WHERE hidden=1")},
        "ndas": c("SELECT COUNT(*) FROM ndas"),
        "views": c("SELECT COUNT(*) FROM views"),
        "loans": {"submitted": c("SELECT COUNT(*) FROM loans WHERE status='submitted'"),
                  "approved": c("SELECT COUNT(*) FROM loans WHERE status='approved'"),
                  "rejected": c("SELECT COUNT(*) FROM loans WHERE status='rejected'")},
        "contracts": c("SELECT COUNT(*) FROM contracts"),
        "settled_total": c("SELECT COALESCE(SUM(amount),0) FROM settlements"),
        "ledger": svc.ledger_status(db),
        "pending_events": [L.event_public(e) for e in db.q(
            "SELECT * FROM events WHERE tsa_token IS NULL ORDER BY seq LIMIT 20")],
        "recent_audit": [dict(r) for r in db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 8")],
    }


@app.route("POST", "/api/ledger/verify", auth="admin")
def r_verify(req):
    out = L.verify_chain(db)
    out["audit"] = svc.verify_audit(db)
    svc.audit(db, req.user, "원장 무결성 검사", "", {"ok": out["ok"], "count": out["count"], "broken": len(out["broken"]),
                                                  "audit_ok": out["audit"]["ok"]}, req.ip)
    return out


@app.route("POST", "/api/ledger/stamp", auth="admin")
def r_stamp(req):
    out = stamper.run_pending(max_tries=10_000)  # 관리자가 누르면 실패 횟수와 관계없이 다시 시도
    svc.audit(db, req.user, "공인 시각 재요청", "", out, req.ip)
    return out


@app.route("GET", "/api/events", auth="admin")
def r_events(req):
    kind = req.query.get("kind", "")
    sql, args = "SELECT * FROM events", []
    if kind:
        sql += " WHERE kind=?"
        args.append(kind)
    rows = db.q(sql + " ORDER BY seq DESC LIMIT 300", args)
    return {"events": [{**L.event_public(r), "actor": r["actor"], "idea_seq": r["idea_seq"]} for r in rows],
            "kinds": L.KIND_LABEL}


# ── 회원 ──
@app.route("GET", "/api/users", auth="admin")
def r_users(req):
    out = []
    for u in db.q("SELECT * FROM users ORDER BY id"):
        d = {k: u[k] for k in ("id", "email", "name", "role", "org", "status", "created_at")}
        d["ideas"] = db.val("SELECT COUNT(*) FROM ideas WHERE owner_id=?", (u["id"],))
        d["ndas"] = db.val("SELECT COUNT(*) FROM ndas WHERE user_id=?", (u["id"],))
        d["loans"] = db.val("SELECT COUNT(*) FROM loans WHERE business_id=?", (u["id"],))
        out.append(d)
    return {"users": out}


@app.route("POST", "/api/users/{id}/status", auth="admin")
def r_user_status(req):
    u = db.one("SELECT * FROM users WHERE id=?", (int(req.params["id"]),))
    if not u:
        raise notfound()
    status = req.get("status")
    reason = str(req.get("reason")).strip()
    if status not in ("active", "suspended"):
        raise HttpError(400, "상태 값을 확인해 주세요.")
    if not reason:
        raise HttpError(400, "사유를 적어 주세요. 감사 로그에 남습니다.")
    db.exec("UPDATE users SET status=? WHERE id=?", (status, u["id"]))
    if status == "suspended":
        db.exec("DELETE FROM sessions WHERE kind='user' AND subject_id=?", (u["id"],))
    svc.audit(db, req.user, "회원 이용 정지" if status == "suspended" else "회원 이용 재개", u["email"], {"reason": reason}, req.ip)
    return {"ok": True}


# ── 아이디어 (읽기 전용, 숨김만) ──
@app.route("GET", "/api/ideas", auth="admin")
def r_ideas(req):
    return {"ideas": [svc.admin_idea_view(db, r) for r in db.q("SELECT * FROM ideas ORDER BY seq DESC")]}


@app.route("GET", "/api/ideas/{seq}", auth="admin")
def r_idea(req):
    r = db.one("SELECT * FROM ideas WHERE seq=?", (int(req.params["seq"]),))
    if not r:
        raise notfound()
    d = svc.admin_idea_view(db, r)
    d["history"] = [L.event_public(e) for e in db.q("SELECT * FROM events WHERE idea_seq=? ORDER BY seq", (r["seq"],))]
    return d


@app.route("POST", "/api/ideas/{seq}/hidden", auth="admin")
def r_hide(req):
    return svc.set_hidden(db, stamper, req.user, req.params["seq"], bool(req.get("hidden")), req.get("reason"), req.ip)


# ── 열람·NDA ──
@app.route("GET", "/api/access", auth="admin")
def r_access(req):
    views = svc.views_for_ideas(db, [r[0] for r in db.q("SELECT seq FROM ideas")])
    ndas = [svc.nda_public(db, n) for n in db.q("SELECT * FROM ndas ORDER BY id DESC")]
    return {"views": views[:500], "ndas": ndas}


# ── 대출 심사 ──
@app.route("GET", "/api/loans", auth="admin")
def r_loans(req):
    return {"loans": [svc.loan_public(db, x) for x in db.q("SELECT * FROM loans ORDER BY (status='submitted') DESC, id DESC")]}


@app.route("POST", "/api/loans/{id}/review", auth="admin")
def r_review(req):
    return svc.review_loan(db, stamper, req.user, req.params["id"], req.get("decision"), req.get("note"), req.ip)


# ── 계약·정산 ──
@app.route("GET", "/api/contracts", auth="admin")
def r_contracts(req):
    svc.audit(db, req.user, "계약·정산 기록 조회", "", {}, req.ip)  # 금액·지분 정보 접근은 기록 (TRD §10)
    return {"contracts": [svc.contract_public(db, c) for c in db.q("SELECT * FROM contracts ORDER BY id DESC")],
            "approved_loans": [svc.loan_public(db, x) for x in db.q(
                "SELECT * FROM loans WHERE status='approved' AND id NOT IN (SELECT loan_id FROM contracts) ORDER BY id")]}


@app.route("POST", "/api/contracts", auth="admin")
def r_contract_new(req):
    return svc.create_contract(db, stamper, req.user, req.json, req.ip)


@app.route("POST", "/api/contracts/{id}/settlements", auth="admin")
def r_settle(req):
    return svc.add_settlement(db, stamper, req.user, req.params["id"], req.json, req.ip)


# ── 감사 로그 ──
@app.route("GET", "/api/audit", auth="admin")
def r_audit(req):
    rows = [dict(r) for r in db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 500")]
    for r in rows:
        r["detail"] = json.loads(r["detail"] or "{}")
    return {"audit": rows, "integrity": svc.verify_audit(db)}


if __name__ == "__main__":
    from ibweb.launcher import prepare
    prepare(sys.argv[1:], db, int(CFG["admin_port"]), "관리자 사이트")
    stamper.start_worker()
    app.serve(CFG["host"], int(CFG["admin_port"]))
