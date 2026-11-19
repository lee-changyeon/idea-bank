"""아이디어뱅크 온라인 — 관리자 사이트. 포트 8091.

사용자 앱과 같은 DB·원장을 쓰지만 로그인(admins 테이블, ib_admin 쿠키)은 완전히 분리되어 있다.
실행: python admin/server.py   (또는 run_admin.bat)
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "web"))

from ibweb import config, ledger as L, security as S, service as svc  # noqa: E402
from ibweb.db import open_db  # noqa: E402
from ibweb.httpkit import ON_VERCEL, App, HttpError, bad, forbidden, notfound  # noqa: E402
from ideabank import canonical as C  # noqa: E402

CFG = config.load()
db = open_db()  # DATABASE_URL 이 있으면 Postgres(Supabase), 없으면 web/data 의 SQLite
stamper = L.Stamper(db, CFG["tsa_urls"], inline=ON_VERCEL)
# 관리자 정적 파일 먼저, 공용 CSS·로고는 web/static 에서
app = App("아이디어뱅크 관리자", db, "admin", "ib_admin", [HERE / "static", HERE.parent / "web" / "static"])
throttle = S.Throttle(db=db)
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def admin_public(a):
    return {"id": a["id"], "username": a["username"], "name": a["name"], "pw_weak": bool(a["pw_weak"])}


def _must_change(a) -> bool:
    return S.launched() and bool(a["pw_weak"])


def _guard(req, path):
    """정식 서비스 중 약한 비밀번호 관리자는 비밀번호를 바꾸기 전에는 다른 기능을 쓸 수 없다."""
    if req.user and _must_change(req.user) and path not in ("/api/password", "/api/me", "/api/logout"):
        raise forbidden("정식 서비스가 시작되어 비밀번호를 먼저 바꿔야 합니다. [비밀번호 변경] 화면에서 바꿔 주세요.")


app.guard = _guard


def _set_pw(admin_id, pw: str):
    db.exec("UPDATE admins SET pw=?, pw_weak=? WHERE id=?",
            (S.hash_password(pw), 0 if S.admin_pw_strong(pw) else 1, admin_id))


@app.route("GET", "/api/me")
def r_me(req):
    return {"admin": admin_public(req.user) if req.user else None, "csrf": req.session["csrf"] if req.session else None,
            "policy": S.admin_policy(), "must_change": bool(req.user and _must_change(req.user))}


# ── 첫 관리자 만들기 · 비밀번호 잊었을 때 재설정 (온라인 전용) ──
# 둘 다 Vercel 환경 변수 ADMIN_SETUP_TOKEN 을 아는 사람만 쓸 수 있다 (= Vercel 프로젝트에 접근할 수 있는 사람).
# - 첫 관리자 만들기: 관리자 계정이 하나도 없을 때만. 한 명이 만들어지면 닫힌다.
# - 비밀번호 재설정: 토큰 + 관리자 아이디 + 새 비밀번호. 그 관리자의 모든 로그인을 끊고 감사 로그에 남긴다.
# 토큰을 지우면 두 기능 모두 꺼진다. 로컬에서는 python web/manage_admins.py passwd <아이디> 를 쓴다.
def _setup_token() -> str:
    return os.environ.get("ADMIN_SETUP_TOKEN", "").strip()


@app.route("GET", "/api/setup")
def r_setup_state(req):
    on = bool(_setup_token())
    return {"needed": on and not db.val("SELECT COUNT(*) FROM admins"), "recovery": on, "policy": S.admin_policy()}


def _check_token(req, key: str):
    token = _setup_token()
    if throttle.blocked(key):
        raise HttpError(429, "시도가 많아 10분 동안 잠겼습니다.")
    if not token:
        raise forbidden("이 기능은 꺼져 있습니다. 운영자가 Vercel 에 ADMIN_SETUP_TOKEN 을 넣어야 합니다.")
    if not hmac.compare_digest(str(req.get("token")), token):
        throttle.fail(key)
        raise forbidden("설정 토큰이 맞지 않습니다.")
    throttle.clear(key)


@app.route("POST", "/api/recover")
def r_recover(req):
    """비밀번호를 잊은 관리자: 설정 토큰으로 새 비밀번호를 정한다."""
    username = str(req.get("username")).strip().lower()
    _check_token(req, f"{req.ip}|recover")
    pw = str(req.get("password"))
    problem = S.admin_pw_problem(pw)
    if problem:
        raise bad(problem)
    a = db.one("SELECT * FROM admins WHERE username=?", (username,))
    if not a:
        raise bad("그런 관리자 아이디가 없습니다.")
    _set_pw(a["id"], pw)
    db.exec("DELETE FROM sessions WHERE kind='admin' AND subject_id=?", (a["id"],))  # 모든 기기에서 로그아웃
    throttle.clear(f"{req.ip}|{username}")
    svc.audit(db, a, "비밀번호 재설정 (설정 토큰)", username, {"via": "recover"}, req.ip)
    return {"ok": True}


@app.route("POST", "/api/setup")
def r_setup(req):
    _check_token(req, f"{req.ip}|setup")
    username = str(req.get("username")).strip().lower()
    name = C.text(str(req.get("name"))).strip()
    pw = str(req.get("password"))
    if not USERNAME_RE.match(username):
        raise bad("아이디는 영문 소문자로 시작하는 2~32자(a-z, 0-9, _)입니다.")
    if not name:
        raise bad("이름을 적어 주세요.")
    problem = S.admin_pw_problem(pw)
    if problem:
        raise bad(problem)
    with db.tx() as conn:  # 동시에 두 명이 만들지 못하도록 쓰기 잠금 안에서 다시 확인
        if conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]:
            raise forbidden("이미 관리자 계정이 있습니다. 로그인해 주세요.")
        conn.execute("INSERT INTO admins (username, name, pw, created_at, pw_weak) VALUES (?,?,?,?,?)",
                     (username, name, S.hash_password(pw), C.now_iso(), 0 if S.admin_pw_strong(pw) else 1))
    a = db.one("SELECT * FROM admins WHERE username=?", (username,))
    svc.audit(db, a, "첫 관리자 계정 만들기", username, {"via": "setup"}, req.ip)
    return {"ok": True}


@app.route("POST", "/api/login")
def r_login(req):
    username = str(req.get("username")).strip()
    key = f"{req.ip}|{username}"
    if throttle.blocked(key):
        raise HttpError(429, "로그인 실패가 많아 10분 동안 잠겼습니다.")
    pw = str(req.get("password"))
    a = svc.authenticate(db, "admins", "username", username, pw)
    if not a:
        throttle.fail(key)
        svc.audit(db, None, "관리자 로그인 실패", username, {}, req.ip)
        raise HttpError(401, "아이디 또는 비밀번호가 맞지 않습니다.")
    throttle.clear(key)
    weak = 0 if S.admin_pw_strong(pw) else 1  # 원문은 로그인할 때만 알 수 있으므로 여기서 강도를 다시 기록
    if weak != a["pw_weak"]:
        db.exec("UPDATE admins SET pw_weak=? WHERE id=?", (weak, a["id"]))
        a = db.one("SELECT * FROM admins WHERE id=?", (a["id"],))
    S.end_session(db, app._cookie(req.h))
    token, csrf = S.new_session(db, "admin", a["id"])
    svc.audit(db, a, "로그인", "", {"weak_password": bool(weak)}, req.ip)
    out = {"admin": admin_public(a), "csrf": csrf, "policy": S.admin_policy(), "must_change": _must_change(a)}
    return out, app.set_cookie(token)


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
    problem = S.admin_pw_problem(new)
    if problem:
        raise HttpError(400, problem)
    if new == current:
        raise HttpError(400, "새 비밀번호가 지금 비밀번호와 같습니다.")
    _set_pw(a["id"], new)
    db.exec("DELETE FROM sessions WHERE kind='admin' AND subject_id=? AND token_hash!=?", (a["id"], req.session["token_hash"]))
    svc.audit(db, a, "비밀번호 변경", a["username"], {"strong": S.admin_pw_strong(new)}, req.ip)
    return {"ok": True, "admin": admin_public(db.one("SELECT * FROM admins WHERE id=?", (a["id"],)))}


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
