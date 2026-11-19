"""업무 로직: 회원, 아이디어, 공개 단계, 열람, NDA, 대출 신청, 계약·정산, 감사 로그.

모든 쓰기는 db.tx() 안에서 원장 이벤트와 함께 기록된다.
사업자에게 전문(body·첨부)을 돌려주는 함수는 반드시 has_nda() 를 먼저 확인한다.
"""
from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timedelta, timezone

from ideabank import canonical as C

from . import files as F
from . import ledger as L
from . import nda as N
from . import security as S
from .db import row
from .httpkit import bad, forbidden, notfound

KST = timezone(timedelta(hours=9))
MAX_FILE = 20 * 1024 * 1024
# Vercel 함수는 요청 본문이 4.5MB 까지라, 온라인에서는 한 번에 올리는 첨부 합계를 줄인다 (base64 로 약 4/3 배가 됨)
MAX_TOTAL = 3 * 1024 * 1024 if os.environ.get("VERCEL") else 200 * 1024 * 1024
LIMITS = {"max_file": min(MAX_FILE, MAX_TOTAL), "max_total": MAX_TOTAL}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DISCLOSURE = {"private": "비공개", "summary": "요약 공개", "nda": "NDA 후 전문 공개"}
PAY_KINDS = {"upfront": "계약금", "royalty": "매출 로열티", "profit": "이익 배당", "equity": "지분"}


def kst_day(iso: str) -> str:
    d = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return d.astimezone(KST).strftime("%Y%m%d")


def safe_name(name: str) -> str:
    name = C.text(name).replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "_", name)
    return name[:120] or "file"


# ───────────────────────────── 회원 ─────────────────────────────

def public_user(u) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"], "org": u["org"],
            "role_label": "창안자" if u["role"] == "creator" else "사업자"}


def signup(db, email, password, name, role, org) -> dict:
    email = C.text(email).strip().lower()
    name = C.text(name).strip()
    org = C.text(org).strip()
    if not EMAIL.match(email):
        raise bad("이메일 주소를 확인해 주세요.")
    if len(password) < 8:
        raise bad("비밀번호는 8자 이상으로 정해 주세요.")
    if not name:
        raise bad("이름을 적어 주세요.")
    if role not in ("creator", "business"):
        raise bad("회원 유형(창안자/사업자)을 골라 주세요.")
    if role == "business" and not org:
        raise bad("사업자는 회사(기관) 이름을 적어 주세요.")
    if db.one("SELECT 1 FROM users WHERE email=?", (email,)):
        raise bad("이미 가입된 이메일입니다.")
    try:
        cur = db.exec("INSERT INTO users (email, name, role, org, pw, created_at) VALUES (?,?,?,?,?,?)",
                      (email, name, role, org, S.hash_password(password), C.now_iso()))
    except Exception as ex:  # 동시에 같은 이메일로 가입 (sqlite3.IntegrityError / psycopg UniqueViolation)
        if any(c.__name__ in ("IntegrityError", "UniqueViolation") for c in type(ex).__mro__):
            raise bad("이미 가입된 이메일입니다.")
        raise
    return row(db.one("SELECT * FROM users WHERE id=?", (cur.lastrowid,)))


def authenticate(db, table: str, key_col: str, key: str, password: str):
    u = db.one(f"SELECT * FROM {table} WHERE {key_col}=?", (key,))
    if not u:
        S.check_password(password, S.DUMMY_HASH)
        return None
    return u if S.check_password(password, u["pw"]) else None


# ───────────────────────────── 아이디어 ─────────────────────────────

def _idea_dict(db, r, *, full: bool) -> dict:
    ev = db.one("SELECT * FROM events WHERE seq=?", (r["event_seq"],))
    owner = db.one("SELECT name FROM users WHERE id=?", (r["owner_id"],))
    d = {
        "seq": r["seq"], "idea_no": r["idea_no"], "title": r["title"], "tags": json.loads(r["tags"]),
        "author": r["author"], "owner_name": owner["name"] if owner else "", "created_at": r["created_at"],
        "content_hash": r["content_hash"], "version": r["version"], "root_seq": r["root_seq"], "parent_seq": r["parent_seq"],
        "disclosure": r["disclosure"], "disclosure_label": DISCLOSURE[r["disclosure"]], "summary": r["summary"],
        "hidden": bool(r["hidden"]), "event_seq": r["event_seq"],
        "tsa_time": ev["tsa_time"], "tsa_url": ev["tsa_url"], "tsa_pending": ev["tsa_token"] is None, "tsa_error": ev["tsa_error"],
        "entry_hash": ev["entry_hash"], "prev_hash": ev["prev_hash"],
    }
    if full:
        d["body"] = r["body"]
        d["canonical"] = bytes(r["canonical"])
        d["attachments"] = [dict(a) for a in db.q("SELECT name, sha256, size, mime FROM attachments WHERE idea_seq=?", (r["seq"],))]
    return d


def strip_bytes(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "canonical"}


def create_idea(db, stamper, user, *, title, body, tags, attachments, parent_seq=None, disclosure="private",
                summary="", timestamp=True) -> dict:
    title, body = C.text(title).strip(), C.text(body)
    if not title or not body.strip():
        raise bad("제목과 내용을 모두 적어 주세요.")
    if len(title) > 200 or len(body) > 200_000:
        raise bad("제목은 200자, 내용은 20만 자까지 쓸 수 있습니다.")
    if disclosure not in DISCLOSURE:
        raise bad("공개 단계를 확인해 주세요.")
    summary = C.text(summary).strip()
    if disclosure != "private" and not summary:
        raise bad("요약 공개나 NDA 후 공개를 고르면 공개 요약을 적어 주세요. (전문은 공개되지 않습니다)")
    if not isinstance(tags, list):
        tags = [t for t in re.split(r"[,\s]+", str(tags or "")) if t]
    parent = None
    if parent_seq:
        parent = db.one("SELECT * FROM ideas WHERE seq=?", (int(parent_seq),))
        if not parent or parent["owner_id"] != user["id"]:
            raise notfound("개정할 원본 아이디어를 찾을 수 없습니다.")

    files = []
    total = 0
    for a in attachments or []:
        try:
            data = base64.b64decode(a.get("data_b64") or "", validate=True)
        except Exception:
            raise bad("첨부파일을 읽을 수 없습니다.")
        if len(data) > LIMITS["max_file"]:
            raise bad(f"첨부 '{a.get('name')}' 가 {LIMITS['max_file'] // 1048576}MB 를 넘습니다.")
        total += len(data)
        if total > MAX_TOTAL:
            raise bad(f"첨부파일 합계가 {MAX_TOTAL // 1048576}MB 를 넘습니다.")
        sha = C.sha256_hex(data)
        F.put(sha, data)
        files.append({"name": safe_name(a.get("name") or "file"), "sha256": sha, "size": len(data),
                      "mime": (a.get("mime") or "application/octet-stream")[:100]})

    created = C.now_iso()
    doc = C.build(title=title, body=body, tags=tags, author=user["name"], created_at=created,
                  parent=parent["content_hash"] if parent else None, attachments=files)
    raw = C.dumps(doc)
    with db.tx() as conn:
        seq = (conn.execute("SELECT COALESCE(MAX(seq),0) FROM ideas").fetchone()[0]) + 1
        ev = L.append(conn, "idea.register", raw, f"user:{user['id']}", idea_seq=seq)
        idea_no = f"IBW-{kst_day(created)}-{seq:06d}"
        conn.execute(
            "INSERT INTO ideas (seq, idea_no, owner_id, event_seq, parent_seq, root_seq, version, title, body, tags, author,"
            " canonical, content_hash, created_at, disclosure, summary) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (seq, idea_no, user["id"], ev["seq"], parent["seq"] if parent else None,
             parent["root_seq"] if parent else seq, (parent["version"] + 1) if parent else 1,
             doc["title"], doc["body"], json.dumps(doc["tags"], ensure_ascii=False), doc["author"],
             raw, ev["content_hash"], created, disclosure, summary))
        for f in files:
            conn.execute("INSERT INTO attachments (idea_seq, name, sha256, size, mime) VALUES (?,?,?,?,?)",
                         (seq, f["name"], f["sha256"], f["size"], f["mime"]))
        if disclosure != "private":
            L.append(conn, "idea.disclosure", L.event_payload(
                "idea.disclosure", idea=ev["content_hash"], idea_no=idea_no, level=disclosure,
                summary_sha256=C.sha256_hex(summary.encode())), f"user:{user['id']}", seq)
    if timestamp:
        stamper.stamp(ev["seq"])  # 등록은 바로 공인 시각을 받는다 (실패하면 대기 → 작업자가 다시 시도)
    stamper.wake.set()
    return get_idea(db, seq)


def get_idea(db, seq: int) -> dict:
    r = db.one("SELECT * FROM ideas WHERE seq=?", (seq,))
    if not r:
        raise notfound("아이디어를 찾을 수 없습니다.")
    return _idea_dict(db, r, full=True)


def own_idea(db, user, seq) -> dict:
    d = get_idea(db, int(seq))
    r = db.one("SELECT owner_id FROM ideas WHERE seq=?", (d["seq"],))
    if r["owner_id"] != user["id"]:
        raise notfound("아이디어를 찾을 수 없습니다.")
    return d


def my_ideas(db, user, q="") -> list[dict]:
    sql = "SELECT * FROM ideas WHERE owner_id=?"
    args = [user["id"]]
    if q:
        sql += " AND (title LIKE ? OR body LIKE ? OR tags LIKE ? OR idea_no LIKE ?)"
        args += [f"%{q}%"] * 4
    out = []
    for r in db.q(sql + " ORDER BY seq DESC", args):
        d = _idea_dict(db, r, full=False)
        d["view_count"] = db.val("SELECT COUNT(*) FROM views WHERE idea_seq=?", (r["seq"],))
        d["nda_count"] = db.val("SELECT COUNT(*) FROM ndas WHERE idea_seq=?", (r["seq"],))
        d["loan_count"] = db.val("SELECT COUNT(*) FROM loans WHERE idea_seq=?", (r["seq"],))
        out.append(d)
    return out


def idea_detail_for_owner(db, user, seq) -> dict:
    d = own_idea(db, user, seq)
    d["revisions"] = [{"seq": r["seq"], "idea_no": r["idea_no"], "version": r["version"], "title": r["title"],
                       "created_at": r["created_at"]}
                      for r in db.q("SELECT * FROM ideas WHERE root_seq=? ORDER BY version", (d["root_seq"],))]
    d["views"] = views_for_ideas(db, [d["seq"]])
    d["ndas"] = [nda_public(db, n) for n in db.q("SELECT * FROM ndas WHERE idea_seq=? ORDER BY id DESC", (d["seq"],))]
    d["loans"] = [loan_public(db, x) for x in db.q("SELECT * FROM loans WHERE idea_seq=? ORDER BY id DESC", (d["seq"],))]
    d["history"] = [L.event_public(e) for e in db.q("SELECT * FROM events WHERE idea_seq=? ORDER BY seq", (d["seq"],))]
    return strip_bytes(d)


def set_disclosure(db, stamper, user, seq, level, summary) -> dict:
    d = own_idea(db, user, seq)
    summary = C.text(summary).strip()
    if level not in DISCLOSURE:
        raise bad("공개 단계를 확인해 주세요.")
    if level != "private" and not summary:
        raise bad("공개 요약을 적어 주세요. 사업자는 이 요약만 먼저 봅니다.")
    if len(summary) > 2000:
        raise bad("공개 요약은 2,000자까지 쓸 수 있습니다.")
    with db.tx() as conn:
        conn.execute("UPDATE ideas SET disclosure=?, summary=? WHERE seq=?", (level, summary, d["seq"]))
        L.append(conn, "idea.disclosure", L.event_payload(
            "idea.disclosure", idea=d["content_hash"], idea_no=d["idea_no"], level=level,
            summary_sha256=C.sha256_hex(summary.encode())), f"user:{user['id']}", d["seq"])
    stamper.wake.set()
    return idea_detail_for_owner(db, user, d["seq"])


def restamp(db, stamper, user, seq) -> dict:
    d = own_idea(db, user, seq)
    r = stamper.stamp(d["event_seq"])
    if not r["ok"]:
        raise bad("공인 시각 기관에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요.")
    return idea_detail_for_owner(db, user, d["seq"])


def attachment(db, seq, sha) -> tuple[dict, bytes]:
    a = db.one("SELECT * FROM attachments WHERE idea_seq=? AND sha256=?", (int(seq), sha))
    if not a:
        raise notfound("첨부파일을 찾을 수 없습니다.")
    return dict(a), F.get(a["sha256"])


def views_for_ideas(db, seqs: list[int]) -> list[dict]:
    if not seqs:
        return []
    qs = ",".join("?" * len(seqs))
    out = []
    for v in db.q(f"SELECT v.*, u.name, u.org, u.email, i.idea_no, i.title, e.tsa_time, e.content_hash AS ev_hash "
                  f"FROM views v JOIN users u ON u.id=v.user_id JOIN ideas i ON i.seq=v.idea_seq "
                  f"JOIN events e ON e.seq=v.event_seq WHERE v.idea_seq IN ({qs}) ORDER BY v.id DESC", seqs):
        out.append({"id": v["id"], "idea_seq": v["idea_seq"], "idea_no": v["idea_no"], "title": v["title"],
                    "viewer": v["name"], "org": v["org"], "level": v["level"],
                    "level_label": {"summary": "요약", "full": "전문", "file": "첨부"}[v["level"]],
                    "detail": v["detail"], "at": v["at"], "tsa_time": v["tsa_time"], "event_seq": v["event_seq"],
                    "event_hash": v["ev_hash"]})
    return out


def my_views(db, user) -> list[dict]:
    return views_for_ideas(db, [r[0] for r in db.q("SELECT seq FROM ideas WHERE owner_id=?", (user["id"],))])


# ───────────────────────────── 사업자: 둘러보기·NDA·열람 ─────────────────────────────

def has_nda(db, user, seq) -> bool:
    return bool(db.one("SELECT 1 FROM ndas WHERE idea_seq=? AND user_id=?", (int(seq), user["id"])))


def _listed(db, seq):
    r = db.one("SELECT * FROM ideas WHERE seq=?", (int(seq),))
    if not r or r["disclosure"] == "private" or r["hidden"]:
        raise notfound("공개된 아이디어가 아닙니다.")
    return r


def market(db, user, q="", tag="") -> list[dict]:
    sql = "SELECT * FROM ideas WHERE disclosure IN ('summary','nda') AND hidden=0"
    args = []
    if q:  # 검색은 공개된 필드(제목·요약·태그)에서만
        sql += " AND (title LIKE ? OR summary LIKE ? OR tags LIKE ?)"
        args += [f"%{q}%"] * 3
    out = []
    for r in db.q(sql + " ORDER BY seq DESC", args):
        d = summary_view(db, r, user)
        if tag and tag not in d["tags"]:
            continue
        out.append(d)
    return out


def summary_view(db, r, user) -> dict:
    """사업자에게 보여 주는 요약. body·첨부·canonical 은 절대 넣지 않는다."""
    ev = db.one("SELECT tsa_time FROM events WHERE seq=?", (r["event_seq"],))
    owner = db.one("SELECT name FROM users WHERE id=?", (r["owner_id"],))
    return {"seq": r["seq"], "idea_no": r["idea_no"], "title": r["title"], "summary": r["summary"],
            "tags": json.loads(r["tags"]), "owner_name": owner["name"], "created_at": r["created_at"],
            "tsa_time": ev["tsa_time"], "content_hash": r["content_hash"], "version": r["version"],
            "disclosure": r["disclosure"], "disclosure_label": DISCLOSURE[r["disclosure"]],
            "nda_signed": has_nda(db, user, r["seq"]),
            "attachment_count": db.val("SELECT COUNT(*) FROM attachments WHERE idea_seq=?", (r["seq"],))}


VIEW_DEDUP_MINUTES = 10


def _log_view(db, stamper, user, idea_row, level, detail="", nda_hash=None):
    if level in ("full", "file"):
        since = (datetime.now(timezone.utc) - timedelta(minutes=VIEW_DEDUP_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
        if db.one("SELECT 1 FROM views WHERE idea_seq=? AND user_id=? AND level=? AND detail=? AND at >= ?",
                  (idea_row["seq"], user["id"], level, detail, since)):
            return  # 방금 같은 열람을 기록했음
    with db.tx() as conn:
        ev = L.append(conn, f"view.{level}", L.event_payload(
            f"view.{level}", idea=idea_row["content_hash"], idea_no=idea_row["idea_no"],
            viewer={"user_id": user["id"], "name": user["name"], "org": user["org"]},
            nda=nda_hash, detail=detail), f"user:{user['id']}", idea_row["seq"])
        conn.execute("INSERT INTO views (idea_seq, user_id, level, detail, event_seq, at) VALUES (?,?,?,?,?,?)",
                     (idea_row["seq"], user["id"], level, detail, ev["seq"], C.now_iso()))
    stamper.wake.set()


def market_detail(db, stamper, user, seq) -> dict:
    r = _listed(db, seq)
    # 요약 열람은 같은 사업자·같은 아이디어에 하루 1건만 기록 (원장 부풀림 방지)
    today = C.now_iso()[:10]
    if not db.one("SELECT 1 FROM views WHERE idea_seq=? AND user_id=? AND level='summary' AND substr(at,1,10)=?",
                  (r["seq"], user["id"], today)):
        _log_view(db, stamper, user, r, "summary")
    d = summary_view(db, r, user)
    n = db.one("SELECT * FROM ndas WHERE idea_seq=? AND user_id=?", (r["seq"], user["id"]))
    d["nda"] = nda_public(db, n) if n else None
    d["nda_template"] = {"version": N.VERSION, "sha256": N.TEMPLATE_HASH, "text": N.TEMPLATE} if r["disclosure"] == "nda" else None
    d["my_loans"] = [loan_public(db, x) for x in db.q("SELECT * FROM loans WHERE idea_seq=? AND business_id=? ORDER BY id DESC",
                                                       (r["seq"], user["id"]))]
    return d


def market_full(db, stamper, user, seq) -> dict:
    """전문 열람. NDA 후 공개 단계 + 서명한 NDA 가 있어야만 본문을 돌려준다. 매번 원장에 기록."""
    r = _listed(db, seq)
    if r["disclosure"] != "nda":
        raise forbidden("창안자가 이 아이디어의 전문을 공개하지 않았습니다.")
    n = db.one("SELECT * FROM ndas WHERE idea_seq=? AND user_id=?", (r["seq"], user["id"]))
    if not n:
        raise forbidden("NDA에 서명해야 전문을 볼 수 있습니다.")
    _log_view(db, stamper, user, r, "full", nda_hash=n["doc_hash"])
    d = get_idea(db, r["seq"])
    return {k: d[k] for k in ("seq", "idea_no", "title", "body", "tags", "author", "created_at", "content_hash",
                              "tsa_time", "version", "attachments")}


def market_file(db, stamper, user, seq, sha) -> tuple[dict, bytes]:
    r = _listed(db, seq)
    n = db.one("SELECT * FROM ndas WHERE idea_seq=? AND user_id=?", (r["seq"], user["id"]))
    if r["disclosure"] != "nda" or not n:
        raise forbidden("NDA에 서명해야 첨부를 볼 수 있습니다.")
    a, data = attachment(db, r["seq"], sha)
    _log_view(db, stamper, user, r, "file", detail=a["name"], nda_hash=n["doc_hash"])
    return a, data


def sign_nda(db, stamper, user, seq, signer_name, agree, template_hash, ip) -> dict:
    r = _listed(db, seq)
    if r["disclosure"] != "nda":
        raise bad("이 아이디어는 NDA 후 전문 공개 대상이 아닙니다.")
    if not agree:
        raise bad("약정 내용에 동의해야 서명할 수 있습니다.")
    if template_hash != N.TEMPLATE_HASH:
        raise bad("약정문이 바뀌었습니다. 페이지를 새로 고친 뒤 다시 읽고 서명해 주세요.")
    signer_name = C.text(signer_name).strip()
    if signer_name != user["name"]:
        raise bad(f"서명란에 가입한 이름('{user['name']}')을 똑같이 적어 주세요.")
    if has_nda(db, user, r["seq"]):
        raise bad("이미 이 아이디어의 NDA에 서명했습니다.")
    signed_at = C.now_iso()
    doc = N.build_doc(idea=dict(r), signer_name=signer_name, org=user["org"], user_id=user["id"], email=user["email"],
                      signed_at=signed_at, ip=ip)
    doc_hash = C.sha256_hex(doc)
    with db.tx() as conn:
        # NDA 문서 자체를 payload 로 → 이벤트 고유 지문 = NDA 문서 해시, 공인 시각도 그 해시에 받는다
        ev = L.append(conn, "nda.sign", doc, f"user:{user['id']}", r["seq"])
        conn.execute("INSERT INTO ndas (idea_seq, user_id, signer_name, org, template_ver, template_hash, doc, doc_hash,"
                     " event_seq, signed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (r["seq"], user["id"], signer_name, user["org"], N.VERSION, N.TEMPLATE_HASH, doc, doc_hash,
                      ev["seq"], signed_at))
    stamper.stamp(ev["seq"])
    return market_detail(db, stamper, user, r["seq"])


def nda_public(db, n) -> dict:
    ev = db.one("SELECT tsa_time, tsa_url FROM events WHERE seq=?", (n["event_seq"],))
    i = db.one("SELECT idea_no, title FROM ideas WHERE seq=?", (n["idea_seq"],))
    return {"id": n["id"], "idea_seq": n["idea_seq"], "idea_no": i["idea_no"], "title": i["title"],
            "signer_name": n["signer_name"], "org": n["org"], "template_ver": n["template_ver"],
            "doc_hash": n["doc_hash"], "signed_at": n["signed_at"], "tsa_time": ev["tsa_time"],
            "tsa_url": ev["tsa_url"], "event_seq": n["event_seq"]}


def my_ndas(db, user) -> list[dict]:
    return [nda_public(db, n) for n in db.q("SELECT * FROM ndas WHERE user_id=? ORDER BY id DESC", (user["id"],))]


# ───────────────────────────── 대출 신청 (LA-2026-001 조건) ─────────────────────────────

def _num(v, name, lo=0, hi=None, allow_float=False):
    try:
        x = float(v) if allow_float else int(str(v).replace(",", ""))
    except (TypeError, ValueError):
        raise bad(f"{name} 값을 숫자로 적어 주세요.")
    if x < lo or (hi is not None and x > hi):
        raise bad(f"{name} 값이 허용 범위를 벗어났습니다.")
    return x


def request_loan(db, stamper, user, seq, f: dict) -> dict:
    r = _listed(db, seq)
    if r["disclosure"] == "nda" and not has_nda(db, user, r["seq"]):
        raise forbidden("NDA 후 공개 아이디어는 NDA 서명 뒤에 대출 신청을 할 수 있습니다.")
    if db.one("SELECT 1 FROM loans WHERE idea_seq=? AND business_id=? AND status='submitted'", (r["seq"], user["id"])):
        raise bad("이 아이디어에 심사 중인 신청이 이미 있습니다.")
    field = C.text(f.get("field") or "").strip()
    if not field:
        raise bad("사용 분야를 적어 주세요. (제3조)")
    exclusive = bool(f.get("exclusive"))
    territory = C.text(f.get("territory") or "대한민국").strip()
    term_years = _num(f.get("term_years"), "기간(년)", 1, 30)
    mvp_months = _num(f.get("mvp_months") or 6, "첫 서비스 출시 목표(개월)", 1, 60)
    pay_in = f.get("pay") or {}
    pay = {}
    if pay_in.get("upfront"):
        pay["upfront"] = {"amount": _num(pay_in["upfront"].get("amount"), "계약금", 1)}
    if pay_in.get("equity"):
        pay["equity"] = {"pct": _num(pay_in["equity"].get("pct"), "지분율", 0.01, 100, True)}
    if pay_in.get("royalty"):
        x = pay_in["royalty"]
        pay["royalty"] = {"pct": _num(x.get("pct"), "로열티율", 0.01, 100, True),
                          "annual_cap": _num(x.get("annual_cap") or 0, "연간 상한", 0),
                          "years": _num(x.get("years") or 5, "로열티 지급 기간", 1, 30)}
    if pay_in.get("profit"):
        pay["profit"] = {"pct": _num(pay_in["profit"].get("pct"), "배당 연동 비율", 0.01, 100, True)}
    if not pay:
        raise bad("대가 방식을 하나 이상 골라 주세요. (제5조: 계약금 / 로열티 / 이익 배당 / 지분)")
    terms = {
        "template": "LA-2026-001 아이디어 사용권 약정서",
        "field": field, "exclusive": exclusive, "territory": territory, "term_years": term_years,
        "mvp_months": mvp_months, "pay": pay, "message": C.text(f.get("message") or "").strip()[:4000],
    }
    with db.tx() as conn:
        n = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0] + 1
        loan_no = f"LR-{datetime.now(KST):%Y}-{n:04d}"
        ev = L.append(conn, "loan.request", L.event_payload(
            "loan.request", loan_no=loan_no, idea=r["content_hash"], idea_no=r["idea_no"],
            business={"user_id": user["id"], "name": user["name"], "org": user["org"]}, terms=terms),
            f"user:{user['id']}", r["seq"])
        cur = conn.execute("INSERT INTO loans (loan_no, idea_seq, business_id, terms, event_seq, created_at) VALUES (?,?,?,?,?,?)",
                           (loan_no, r["seq"], user["id"], json.dumps(terms, ensure_ascii=False), ev["seq"], C.now_iso()))
    stamper.wake.set()
    return loan_public(db, db.one("SELECT * FROM loans WHERE id=?", (cur.lastrowid,)))


STATUS_LABEL = {"submitted": "심사 중", "approved": "승인", "rejected": "반려"}
RESP_LABEL = {"pending": "응답 전", "accepted": "동의", "declined": "거절"}


def loan_public(db, x) -> dict:
    i = db.one("SELECT idea_no, title, owner_id FROM ideas WHERE seq=?", (x["idea_seq"],))
    b = db.one("SELECT name, org FROM users WHERE id=?", (x["business_id"],))
    c = db.one("SELECT name FROM users WHERE id=?", (i["owner_id"],))
    ev = db.one("SELECT tsa_time, content_hash FROM events WHERE seq=?", (x["event_seq"],))
    ct = db.one("SELECT contract_no, signed_on, status FROM contracts WHERE loan_id=?", (x["id"],))
    return {"id": x["id"], "loan_no": x["loan_no"], "idea_seq": x["idea_seq"], "idea_no": i["idea_no"],
            "title": i["title"], "creator": c["name"], "business": b["name"], "org": b["org"],
            "terms": json.loads(x["terms"]), "status": x["status"], "status_label": STATUS_LABEL[x["status"]],
            "creator_response": x["creator_response"], "creator_response_label": RESP_LABEL[x["creator_response"]],
            "creator_note": x["creator_note"], "review_note": x["review_note"], "reviewed_at": x["reviewed_at"],
            "created_at": x["created_at"], "tsa_time": ev["tsa_time"], "event_hash": ev["content_hash"],
            "contract": dict(ct) if ct else None}


def biz_loans(db, user):
    return [loan_public(db, x) for x in db.q("SELECT * FROM loans WHERE business_id=? ORDER BY id DESC", (user["id"],))]


def creator_loans(db, user):
    return [loan_public(db, x) for x in db.q(
        "SELECT l.* FROM loans l JOIN ideas i ON i.seq=l.idea_seq WHERE i.owner_id=? ORDER BY l.id DESC", (user["id"],))]


def creator_respond(db, stamper, user, loan_id, accept, note) -> dict:
    x = db.one("SELECT l.*, i.owner_id, i.content_hash FROM loans l JOIN ideas i ON i.seq=l.idea_seq WHERE l.id=?", (int(loan_id),))
    if not x or x["owner_id"] != user["id"]:
        raise notfound("대출 신청을 찾을 수 없습니다.")
    if x["status"] != "submitted":
        raise bad("심사가 끝난 신청에는 응답을 바꿀 수 없습니다.")
    resp = "accepted" if accept else "declined"
    note = C.text(note or "").strip()[:2000]
    with db.tx() as conn:
        L.append(conn, "loan.creator_response", L.event_payload(
            "loan.creator_response", loan_no=x["loan_no"], idea=x["content_hash"], response=resp, note=note),
            f"user:{user['id']}", x["idea_seq"])
        conn.execute("UPDATE loans SET creator_response=?, creator_note=? WHERE id=?", (resp, note, x["id"]))
    stamper.wake.set()
    return loan_public(db, db.one("SELECT * FROM loans WHERE id=?", (x["id"],)))


# ───────────────────────────── 공개 검증 ─────────────────────────────

def lookup(db, h: str) -> dict:
    """누구나 조회. 비공개 아이디어 보호를 위해 제목·내용은 돌려주지 않는다."""
    h = (h or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", h):
        raise bad("고유 지문은 64자리 영문·숫자입니다.")
    out = []
    for r in db.q("SELECT i.idea_no, i.created_at, i.version, e.tsa_time, e.tsa_url, 'content' AS hit FROM ideas i "
                  "JOIN events e ON e.seq=i.event_seq WHERE i.content_hash=? "
                  "UNION SELECT i.idea_no, i.created_at, i.version, e.tsa_time, e.tsa_url, 'attachment' FROM attachments a "
                  "JOIN ideas i ON i.seq=a.idea_seq JOIN events e ON e.seq=i.event_seq WHERE a.sha256=?", (h, h)):
        out.append(dict(r))
    ev = db.one("SELECT seq, kind, created_at, tsa_time FROM events WHERE content_hash=? AND kind!='idea.register'", (h,))
    return {"hash": h, "ideas": out, "event": ({**dict(ev), "kind_label": L.KIND_LABEL.get(ev["kind"], ev["kind"])} if ev else None)}


def ledger_status(db) -> dict:
    last = db.one("SELECT seq, entry_hash, created_at FROM events ORDER BY seq DESC LIMIT 1")
    return {"count": last["seq"] if last else 0, "head": last["entry_hash"] if last else C.GENESIS,
            "updated_at": last["created_at"] if last else None,
            "pending": db.val("SELECT COUNT(*) FROM events WHERE tsa_token IS NULL")}


# ───────────────────────────── 관리자 ─────────────────────────────

def audit(db, admin, action, target="", detail=None, ip=""):
    """관리자 행동 기록. 자체 해시 체인: entry = sha256(prev:id:sha256(record))."""
    with db.tx() as conn:
        last = conn.execute("SELECT id, entry_hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        nid = (last["id"] + 1) if last else 1
        prev = last["entry_hash"] if last else C.GENESIS
        at = C.now_iso()
        d = json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)
        rec = C.dumps({"id": nid, "admin": admin["username"] if admin else "-", "action": action, "target": target,
                       "detail": d, "ip": ip, "at": at})
        conn.execute("INSERT INTO audit (id, admin_id, admin_name, action, target, detail, ip, at, prev_hash, entry_hash)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (nid, admin["id"] if admin else None, admin["username"] if admin else "-", action, target, d, ip, at,
                      prev, C.entry_hash(prev, nid, C.sha256_hex(rec))))


def verify_audit(db) -> dict:
    prev = C.GENESIS
    bad_rows = []
    for r in db.q("SELECT * FROM audit ORDER BY id"):
        rec = C.dumps({"id": r["id"], "admin": r["admin_name"], "action": r["action"], "target": r["target"],
                       "detail": r["detail"], "ip": r["ip"], "at": r["at"]})
        if r["prev_hash"] != prev or C.entry_hash(prev, r["id"], C.sha256_hex(rec)) != r["entry_hash"]:
            bad_rows.append(r["id"])
        prev = r["entry_hash"]
    return {"ok": not bad_rows, "broken": bad_rows}


def admin_idea_view(db, r) -> dict:
    """관리자는 본문을 보지 않는다. 공개된 아이디어만 제목·요약을 본다."""
    ev = db.one("SELECT tsa_time, tsa_token IS NULL AS p FROM events WHERE seq=?", (r["event_seq"],))
    owner = db.one("SELECT name, email FROM users WHERE id=?", (r["owner_id"],))
    listed = r["disclosure"] != "private"
    return {"seq": r["seq"], "idea_no": r["idea_no"], "title": r["title"] if listed else "(비공개 아이디어)",
            "summary": r["summary"] if listed else "", "tags": json.loads(r["tags"]) if listed else [],
            "owner": owner["name"], "owner_email": owner["email"], "created_at": r["created_at"],
            "content_hash": r["content_hash"], "version": r["version"], "disclosure": r["disclosure"],
            "disclosure_label": DISCLOSURE[r["disclosure"]], "hidden": bool(r["hidden"]), "hidden_reason": r["hidden_reason"],
            "tsa_time": ev["tsa_time"], "tsa_pending": bool(ev["p"]),
            "views": db.val("SELECT COUNT(*) FROM views WHERE idea_seq=?", (r["seq"],)),
            "ndas": db.val("SELECT COUNT(*) FROM ndas WHERE idea_seq=?", (r["seq"],)),
            "loans": db.val("SELECT COUNT(*) FROM loans WHERE idea_seq=?", (r["seq"],))}


def set_hidden(db, stamper, admin, seq, hidden, reason, ip) -> dict:
    r = db.one("SELECT * FROM ideas WHERE seq=?", (int(seq),))
    if not r:
        raise notfound()
    reason = C.text(reason or "").strip()
    if not reason:
        raise bad("숨김·해제 사유를 적어 주세요. 감사 로그에 남습니다.")
    kind = "idea.hide" if hidden else "idea.unhide"
    with db.tx() as conn:
        conn.execute("UPDATE ideas SET hidden=?, hidden_reason=? WHERE seq=?", (1 if hidden else 0, reason, r["seq"]))
        L.append(conn, kind, L.event_payload(kind, idea=r["content_hash"], idea_no=r["idea_no"], reason=reason,
                                             admin=admin["username"]), f"admin:{admin['id']}", r["seq"])
    audit(db, admin, "아이디어 숨김" if hidden else "아이디어 숨김 해제", r["idea_no"], {"reason": reason}, ip)
    stamper.wake.set()
    return admin_idea_view(db, db.one("SELECT * FROM ideas WHERE seq=?", (r["seq"],)))


def review_loan(db, stamper, admin, loan_id, decision, note, ip) -> dict:
    x = db.one("SELECT l.*, i.content_hash FROM loans l JOIN ideas i ON i.seq=l.idea_seq WHERE l.id=?", (int(loan_id),))
    if not x:
        raise notfound()
    if x["status"] != "submitted":
        raise bad("이미 심사가 끝난 신청입니다.")
    if decision not in ("approved", "rejected"):
        raise bad("승인 또는 반려를 골라 주세요.")
    note = C.text(note or "").strip()[:2000]
    if decision == "rejected" and not note:
        raise bad("반려 사유를 적어 주세요.")
    with db.tx() as conn:
        L.append(conn, "loan.review", L.event_payload(
            "loan.review", loan_no=x["loan_no"], idea=x["content_hash"], decision=decision, note=note,
            admin=admin["username"]), f"admin:{admin['id']}", x["idea_seq"])
        conn.execute("UPDATE loans SET status=?, review_note=?, reviewed_by=?, reviewed_at=? WHERE id=?",
                     (decision, note, admin["id"], C.now_iso(), x["id"]))
    audit(db, admin, "대출 신청 " + ("승인" if decision == "approved" else "반려"), x["loan_no"],
          {"note": note, "creator_response": x["creator_response"]}, ip)
    stamper.wake.set()
    return loan_public(db, db.one("SELECT * FROM loans WHERE id=?", (x["id"],)))


def contract_public(db, c) -> dict:
    loan = loan_public(db, db.one("SELECT * FROM loans WHERE id=?", (c["loan_id"],)))
    ev = db.one("SELECT tsa_time, content_hash FROM events WHERE seq=?", (c["event_seq"],))
    sts = []
    for s in db.q("SELECT * FROM settlements WHERE contract_id=? ORDER BY id", (c["id"],)):
        sev = db.one("SELECT tsa_time FROM events WHERE seq=?", (s["event_seq"],))
        sts.append({**dict(s), "kind_label": PAY_KINDS.get(s["kind"], s["kind"]), "tsa_time": sev["tsa_time"]})
    return {**{k: c[k] for k in ("id", "contract_no", "loan_id", "signed_on", "doc_name", "doc_hash", "status", "created_at")},
            "terms": json.loads(c["terms"]), "loan": loan, "tsa_time": ev["tsa_time"], "event_hash": ev["content_hash"],
            "settlements": sts, "settled_total": sum(s["amount"] for s in sts)}


def create_contract(db, stamper, admin, f, ip) -> dict:
    x = db.one("SELECT l.*, i.content_hash FROM loans l JOIN ideas i ON i.seq=l.idea_seq WHERE l.id=?", (int(f.get("loan_id") or 0),))
    if not x or x["status"] != "approved":
        raise bad("승인된 대출 신청에만 계약을 기록할 수 있습니다.")
    if db.one("SELECT 1 FROM contracts WHERE loan_id=?", (x["id"],)):
        raise bad("이 신청에는 이미 계약 기록이 있습니다.")
    signed_on = (f.get("signed_on") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", signed_on):
        raise bad("약정일을 YYYY-MM-DD 형식으로 적어 주세요.")
    doc_name, doc_hash = "", ""
    if f.get("doc_b64"):
        data = base64.b64decode(f["doc_b64"])
        doc_hash = C.sha256_hex(data)
        doc_name = safe_name(f.get("doc_name") or "contract")
        F.put(doc_hash, data)
    terms = json.loads(x["terms"])
    terms["note"] = C.text(f.get("note") or "").strip()[:4000]
    with db.tx() as conn:
        n = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] + 1
        cno = f"LA-{datetime.now(KST):%Y}-{n + 1:03d}"  # LA-2026-001 은 대표 1호 계약(문서)이 이미 사용
        ev = L.append(conn, "contract.create", L.event_payload(
            "contract.create", contract_no=cno, loan_no=x["loan_no"], idea=x["content_hash"], signed_on=signed_on,
            terms=terms, document_sha256=doc_hash or None, admin=admin["username"]), f"admin:{admin['id']}", x["idea_seq"])
        cur = conn.execute("INSERT INTO contracts (contract_no, loan_id, signed_on, terms, doc_name, doc_hash, event_seq,"
                           " created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                           (cno, x["id"], signed_on, json.dumps(terms, ensure_ascii=False), doc_name, doc_hash, ev["seq"],
                            admin["id"], C.now_iso()))
    audit(db, admin, "계약 기록 등록", cno, {"loan_no": x["loan_no"], "signed_on": signed_on, "doc_sha256": doc_hash}, ip)
    stamper.wake.set()
    return contract_public(db, db.one("SELECT * FROM contracts WHERE id=?", (cur.lastrowid,)))


def add_settlement(db, stamper, admin, contract_id, f, ip) -> dict:
    c = db.one("SELECT c.*, l.idea_seq, l.loan_no FROM contracts c JOIN loans l ON l.id=c.loan_id WHERE c.id=?", (int(contract_id),))
    if not c:
        raise notfound()
    period = C.text(f.get("period") or "").strip()
    kind = f.get("kind")
    if not period:
        raise bad("정산 기간을 적어 주세요. 예) 2027-1Q")
    if kind not in PAY_KINDS:
        raise bad("정산 종류를 골라 주세요.")
    amount = _num(f.get("amount"), "금액", 0, 10 ** 15)
    paid_on = (f.get("paid_on") or "").strip()
    note = C.text(f.get("note") or "").strip()[:2000]
    with db.tx() as conn:
        ev = L.append(conn, "settlement.create", L.event_payload(
            "settlement.create", contract_no=c["contract_no"], period=period, pay_kind=kind, amount=amount, paid_on=paid_on,
            note=note, admin=admin["username"]), f"admin:{admin['id']}", c["idea_seq"])
        conn.execute("INSERT INTO settlements (contract_id, period, kind, amount, paid_on, note, event_seq, created_by, created_at)"
                     " VALUES (?,?,?,?,?,?,?,?,?)", (c["id"], period, kind, amount, paid_on, note, ev["seq"], admin["id"], C.now_iso()))
    audit(db, admin, "정산 기록 등록", c["contract_no"], {"period": period, "kind": kind, "amount": amount}, ip)
    stamper.wake.set()
    return contract_public(db, db.one("SELECT * FROM contracts WHERE id=?", (c["id"],)))


def user_contracts(db, user) -> list[dict]:
    if user["role"] == "creator":
        rows = db.q("SELECT c.* FROM contracts c JOIN loans l ON l.id=c.loan_id JOIN ideas i ON i.seq=l.idea_seq "
                    "WHERE i.owner_id=? ORDER BY c.id DESC", (user["id"],))
    else:
        rows = db.q("SELECT c.* FROM contracts c JOIN loans l ON l.id=c.loan_id WHERE l.business_id=? ORDER BY c.id DESC",
                    (user["id"],))
    return [contract_public(db, c) for c in rows]
