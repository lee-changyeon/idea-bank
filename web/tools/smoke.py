"""사용자 웹 전체 흐름 점검 (로컬 또는 배포 주소).

    python web/tools/smoke.py https://<배포 주소>        # 실제 공인 시각까지 확인
    python web/tools/smoke.py http://localhost:8090 --no-tsa

흐름: 가입(창안자) → 첨부 포함 아이디어 등록(공인 시각) → 증명 파일 받기·검증(웹 + v1 검증기) → 가입(사업자)
→ 요약 열람 → NDA 서명 → 전문·첨부 열람 → 창안자가 열람 기록 확인 → 공개 단계 변경 → 원장 무결성 검사.
매번 새 무작위 계정을 만든다(이메일 smoke-…@example.com).
"""
from __future__ import annotations

import base64
import http.cookiejar
import io
import json
import secrets
import sqlite3
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ideabank import bundle as core_bundle  # noqa: E402
from ideabank import canonical as C  # noqa: E402


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None
        self.last_headers = {}

    def call(self, method, path, body=None, raw=False, expect=200):
        u = urlparse(self.base)
        h = {"Origin": f"{u.scheme}://{u.netloc}", "User-Agent": "ideabank-smoke/1"}
        data = None
        if method == "POST":
            h["Content-Type"] = "application/json"
            if self.csrf:
                h["X-CSRF-Token"] = self.csrf
            data = json.dumps(body or {}).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.op.open(req, timeout=90) as r:
                st, out, self.last_headers = r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            st, out, self.last_headers = e.code, e.read(), dict(e.headers)
        if st != expect:
            raise AssertionError(f"{method} {path} → {st} (기대 {expect}): {out[:300]!r}")
        if raw:
            return out
        j = json.loads(out)
        if isinstance(j, dict) and j.get("csrf"):
            self.csrf = j["csrf"]
        return j


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ✓", msg)


def v1_verify(zip_bytes: bytes) -> dict:
    """v1 검증기(ideabank.bundle.verify)를 빈 v1 원장으로 돌린다 → '이 보관함 원장'만 없음, 나머지는 통과해야 한다."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE ideas (seq INTEGER, idea_no TEXT, content_hash TEXT)")
    return core_bundle.verify(SimpleNamespace(db=con), zip_bytes)


def run(base: str, expect_tsa=True) -> dict:
    tag = secrets.token_hex(4)
    pw = secrets.token_urlsafe(12)
    print(f"[점검] {base}  (계정 접미사 {tag})")

    page = Client(base).call("GET", "/", raw=True)
    check(b"<html" in page.lower() or b"<!doctype" in page.lower(), "첫 화면 HTML")

    cr = Client(base)
    me = cr.call("GET", "/api/me")
    check(me["user"] is None and "limits" in me, "로그인 전 /api/me")
    u = cr.call("POST", "/api/signup", {"email": f"smoke-c-{tag}@example.com", "password": pw, "name": f"창안자{tag}",
                                        "role": "creator", "org": ""})
    check(u["user"]["role"] == "creator", "창안자 가입")
    cookie = cr.last_headers.get("Set-Cookie", "")
    if base.startswith("https://"):
        check("Secure" in cookie and "HttpOnly" in cookie, "세션 쿠키 Secure·HttpOnly")

    att = f"smoke attachment {tag}\n".encode()
    idea = cr.call("POST", "/api/my/ideas", {
        "title": f"점검용 아이디어 {tag}", "body": f"[무엇] 점검 {tag}\n[어떻게] 자동 점검 스크립트", "tags": ["점검"],
        "disclosure": "nda", "summary": "자동 점검용 공개 요약", "timestamp": expect_tsa,
        "attachments": [{"name": "notes.txt", "mime": "text/plain", "data_b64": base64.b64encode(att).decode()}]})
    seq = idea["seq"]
    check(idea["idea_no"].startswith("IBW-"), f"아이디어 등록 {idea['idea_no']}")
    if expect_tsa:
        check(bool(idea["tsa_time"]), f"공인 시각 {idea['tsa_time']} ({idea['tsa_url']})")

    z = cr.call("GET", f"/api/my/ideas/{seq}/bundle", raw=True)
    zf = zipfile.ZipFile(io.BytesIO(z))
    check("canonical.json" in zf.namelist() and "attachments/notes.txt" in zf.namelist(), "증명 파일 내려받기")
    canon = zf.read("canonical.json")
    check(C.sha256_hex(canon) == idea["content_hash"] and json.loads(canon)["schema"] == "ideabank/1",
          "canonical.json = ideabank/1, 고유 지문 일치")
    wv = cr.call("POST", "/api/verify/bundle", {"zip_b64": base64.b64encode(z).decode()})
    v1 = v1_verify(z)
    if expect_tsa:
        check(wv["ok"], "웹 검증: 이상 없음")
        check(v1["ok"], "v1 검증기: 이상 없음")
    else:
        bad = [c["name"] for c in v1["checks"] if not c["ok"] and c["name"] not in ("공인 시각", "이 보관함 원장")]
        check(not bad, "v1 검증기: 원문·첨부 일치 (공인 시각 없이)")
    check(any(c["name"] == "아이디어뱅크 원장" and c["ok"] for c in wv["checks"]), "웹 검증: 원장에 있음")

    biz = Client(base)
    biz.call("POST", "/api/signup", {"email": f"smoke-b-{tag}@example.com", "password": pw, "name": f"사업자{tag}",
                                     "role": "business", "org": "점검회사"})
    lst = biz.call("GET", "/api/market")
    check(any(i["seq"] == seq for i in lst["ideas"]), "사업자 목록에 보임")
    check(all("body" not in i for i in lst["ideas"]), "목록에 본문 없음")
    d = biz.call("GET", f"/api/market/{seq}")
    check(d["nda_template"] and "body" not in d, "요약 열람 (본문 없음)")
    biz.call("GET", f"/api/market/{seq}/full", expect=403)
    check(True, "NDA 전 전문 열람 거부(403)")
    d = biz.call("POST", f"/api/market/{seq}/nda", {"signer_name": f"사업자{tag}", "agree": True,
                                                    "template_hash": d["nda_template"]["sha256"]})
    check(d["nda"] and d["nda"]["doc_hash"], "NDA 서명")
    if expect_tsa:
        check(bool(d["nda"]["tsa_time"]), f"NDA 공인 시각 {d['nda']['tsa_time']}")
    full = biz.call("GET", f"/api/market/{seq}/full")
    check(tag in full["body"], "NDA 후 전문 열람")
    sha = full["attachments"][0]["sha256"]
    got = biz.call("GET", f"/api/market/{seq}/files/{sha}", raw=True)
    check(got == att, "첨부 열람 (저장소 원본과 같음)")

    views = cr.call("GET", "/api/my/views")["views"]
    lv = {v["level"] for v in views if v["idea_seq"] == seq}
    check({"summary", "full", "file"} <= lv, f"창안자 열람 기록 {sorted(lv)}")
    det = cr.call("POST", f"/api/my/ideas/{seq}/disclosure", {"level": "summary", "summary": "요약만 공개로 변경"})
    check(det["disclosure"] == "summary", "공개 단계 변경 (NDA → 요약)")
    biz.call("GET", f"/api/market/{seq}/full", expect=403)
    check(True, "요약 단계에서는 전문 거부(403)")

    led = Client(base).call("GET", "/api/ledger/verify")
    check(led["ok"], f"원장 무결성 검사: 기록 {led['count']}건, 공인 시각 대기 {led['pending']}건")
    cr.call("POST", "/api/logout")
    Client(base).call("POST", "/api/login", {"email": f"smoke-c-{tag}@example.com", "password": "wrong-password"},
                      expect=401)
    ok_login = Client(base).call("POST", "/api/login", {"email": f"smoke-c-{tag}@example.com", "password": pw})
    check(ok_login["user"]["role"] == "creator", "틀린 비밀번호 거부, 다시 로그인")
    print("[점검] 모두 통과")
    return {"seq": seq, "idea_no": idea["idea_no"], "ledger": led}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(args[0] if args else "http://localhost:8090", expect_tsa="--no-tsa" not in sys.argv)
