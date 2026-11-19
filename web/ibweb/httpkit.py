"""작은 HTTP 프레임워크 (http.server 기반): 라우팅, JSON, 세션 쿠키, CSRF, 역할 검사, 정적 파일."""
from __future__ import annotations

import json
import mimetypes
from decimal import Decimal
import os
import re
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import security as S

MAX_BODY = 30 * 1024 * 1024
ON_VERCEL = bool(os.environ.get("VERCEL"))
# 운영(HTTPS)에서는 쿠키에 Secure 를 붙인다. 로컬 http://localhost 에서는 붙이면 쿠키가 저장되지 않는다.
SECURE_COOKIES = ON_VERCEL or os.environ.get("IB_SECURE_COOKIES") == "1"

SEC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _json_default(o):
    if isinstance(o, Decimal):  # Postgres SUM(bigint) 등은 numeric → Decimal 로 온다
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(f"JSON 으로 바꿀 수 없는 값: {type(o).__name__}")


class HttpError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status
        self.msg = msg


def bad(msg):        return HttpError(400, msg)
def forbidden(msg="권한이 없습니다."): return HttpError(403, msg)
def notfound(msg="찾을 수 없습니다."): return HttpError(404, msg)


class Response:
    def __init__(self, body: bytes, ctype: str, status=200, headers=None):
        self.body, self.ctype, self.status, self.headers = body, ctype, status, headers or {}


def download(data: bytes, filename: str, ctype="application/octet-stream") -> Response:
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "file"
    return Response(data, ctype, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"})


class Request:
    def __init__(self, h: "Handler", params: dict):
        self.h = h
        u = urlparse(h.path)
        self.path = u.path
        self.query = {k: v[0] for k, v in parse_qs(u.query).items()}
        self.params = params
        self.ip = h.client_address[0]
        if ON_VERCEL:  # Vercel 프록시 뒤: Vercel 이 넣는 X-Real-IP 가 실제 접속 IP
            real = (h.headers.get("X-Real-IP") or "").strip()
            fwd = (h.headers.get("X-Forwarded-For") or "").split(",")[-1].strip()  # 마지막 값 = 프록시가 본 IP
            self.ip = real or fwd or self.ip
        self.session = None
        self.user = None  # users 또는 admins 행
        self._json = None

    @property
    def json(self) -> dict:
        if self._json is None:
            n = int(self.h.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise HttpError(413, "요청이 너무 큽니다 (최대 30MB).")
            raw = self.h.rfile.read(n) if n else b"{}"
            try:
                self._json = json.loads(raw or b"{}")
            except ValueError:
                raise bad("요청 형식이 올바르지 않습니다.")
            if not isinstance(self._json, dict):
                raise bad("요청 형식이 올바르지 않습니다.")
        return self._json

    def get(self, key, default=""):
        v = self.json.get(key, default)
        return v if v is not None else default


class App:
    """kind='user' 이면 users 테이블, 'admin' 이면 admins 테이블로 로그인한다. 쿠키 이름도 서로 다르다."""

    def __init__(self, name: str, db, kind: str, cookie: str, static_dirs: list[Path]):
        self.name, self.db, self.kind, self.cookie = name, db, kind, cookie
        self.static_dirs = static_dirs
        self.routes: list[tuple[str, re.Pattern, callable, object]] = []
        self.guard = None  # guard(req, path): 로그인한 요청마다 추가 검사 (관리자: 정식 서비스 때 약한 비밀번호 차단)

    def route(self, method: str, pattern: str, auth=None):
        """auth: None(공개) | 'any'(로그인) | 'creator' | 'business' | 'admin'"""
        rx = re.compile("^" + re.sub(r"{(\w+)}", r"(?P<\1>[^/]+)", pattern) + "$")

        def deco(fn):
            self.routes.append((method, rx, fn, auth))
            return fn
        return deco

    def load_user(self, req: Request):
        token = self._cookie(req.h)
        s = S.get_session(self.db, self.kind, token)
        if not s:
            return
        table = "users" if self.kind == "user" else "admins"
        u = self.db.one(f"SELECT * FROM {table} WHERE id=?", (s["subject_id"],))
        if not u or (self.kind == "user" and u["status"] != "active"):
            return
        req.session, req.user = s, u

    def _cookie(self, h) -> str | None:
        c = SimpleCookie()
        try:
            c.load(h.headers.get("Cookie") or "")
        except Exception:
            return None
        m = c.get(self.cookie)
        return m.value if m else None

    def set_cookie(self, token: str | None) -> dict:
        sec = "; Secure" if SECURE_COOKIES else ""
        if token:
            v = f"{self.cookie}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={S.SESSION_TTL}{sec}"
        else:
            v = f"{self.cookie}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{sec}"
        return {"Set-Cookie": v}

    def handler(self):
        app = self

        class H(Handler):
            pass
        H.app = app
        return H

    def serve(self, host: str, port: int):
        srv = ThreadingHTTPServer((host, port), self.handler())
        srv.daemon_threads = True
        print(f"{self.name}: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
        srv.serve_forever()


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "IdeaBank"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in {**SEC_HEADERS, **(headers or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj, headers=None):
        self._send(status, json.dumps(obj, ensure_ascii=False, default=_json_default).encode("utf-8"),
                   "application/json; charset=utf-8", headers)

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # 브라우저 외 클라이언트 (CSRF 토큰과 SameSite 쿠키가 따로 막는다)
        return urlparse(origin).netloc == self.headers.get("Host")

    def _dispatch(self, method: str):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/"):
                return self._api(method, path)
            if method != "GET":
                raise notfound()
            return self._static(path)
        except HttpError as e:
            self._json(e.status, {"error": e.msg})
        except Exception as ex:
            traceback.print_exc()
            if any(c.__name__ == "OperationalError" for c in type(ex).__mro__):  # psycopg: DB 에 연결하지 못함
                return self._json(503, {"error": "데이터베이스에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요."})
            self._json(500, {"error": "서버 오류가 났습니다. 잠시 뒤 다시 시도해 주세요."})

    def _api(self, method, path):
        app = self.app
        for m, rx, fn, auth in app.routes:
            if m != method:
                continue
            mt = rx.match(path)
            if not mt:
                continue
            req = Request(self, mt.groupdict())
            app.load_user(req)
            if method == "POST":
                if not self._same_origin():
                    raise forbidden("다른 사이트에서 온 요청은 받지 않습니다.")
                if "application/json" not in (self.headers.get("Content-Type") or ""):
                    raise HttpError(415, "JSON 요청만 받습니다.")
                # 로그인한 상태의 모든 POST 는 CSRF 토큰 필수
                if req.session and not S.csrf_ok(req.session, self.headers.get("X-CSRF-Token")):
                    raise forbidden("보안 토큰이 맞지 않습니다. 페이지를 새로 고친 뒤 다시 시도해 주세요.")
            if auth:
                if not req.user:
                    raise HttpError(401, "로그인이 필요합니다.")
                if auth in ("creator", "business") and req.user["role"] != auth:
                    raise forbidden("이 기능은 " + ("창안자" if auth == "creator" else "사업자") + " 계정만 쓸 수 있습니다.")
                if auth == "admin" and app.kind != "admin":
                    raise forbidden()
                if app.guard:
                    app.guard(req, path)
            out = fn(req)
            if isinstance(out, Response):
                return self._send(out.status, out.body, out.ctype, out.headers)
            status, headers = 200, None
            if isinstance(out, tuple):
                out, headers = out
            return self._json(status, out, headers)
        raise notfound("없는 API 입니다.")

    def _static(self, path: str):
        rel = path.lstrip("/") or "index.html"
        if ".." in rel.split("/") or "\\" in rel:
            raise notfound()
        for base in self.app.static_dirs:
            p = (base / rel).resolve()
            if p.is_file() and base.resolve() in p.parents:
                ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                    ctype += "; charset=utf-8"
                return self._send(200, p.read_bytes(), ctype)
        raise notfound()

