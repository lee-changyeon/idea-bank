"""Vercel 파이썬 함수 입구: 아이디어뱅크 사용자 웹(web/server.py)과 관리자 사이트(admin/server.py).

vercel.json 이 모든 경로를 이 함수로 보낸다. 요청의 호스트 이름으로 어느 앱인지 고른다.
- 관리자 주소(IB_ADMIN_HOSTS, 기본 idea-bank-admin.vercel.app) → 관리자 사이트
- 그 밖의 주소 → 사용자 웹
두 앱은 로그인·쿠키·API 가 서로 완전히 분리되어 있고, 같은 DB·원장을 쓴다. 설계: web/DEPLOY_SUPABASE.md
"""
import importlib.util
import os
import sys
from http.server import BaseHTTPRequestHandler  # noqa: F401  (Vercel 파이썬 런타임 표식)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
for p in (str(ROOT), str(WEB)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load(name: str, path: Path):
    # 루트의 server.py(v1 로컬 앱)와 이름이 겹치지 않도록 파일 경로로 불러온다
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_web = _load("ideabank_web_server", WEB / "server.py")
_admin = _load("ideabank_admin_server", ROOT / "admin" / "server.py")

from ibweb.httpkit import Handler  # noqa: E402

ADMIN_HOSTS = {h.strip().lower() for h in os.environ.get("IB_ADMIN_HOSTS", "idea-bank-admin.vercel.app").split(",")
               if h.strip()}


def pick_app(host: str, path: str = ""):
    if path.startswith("/api/cron/"):  # Vercel Cron 은 운영 주소로 부른다 — 주소와 관계없이 사용자 앱이 처리
        return _web.app
    return _admin.app if (host or "").split(":")[0].strip().lower() in ADMIN_HOSTS else _web.app


class handler(Handler):  # Vercel 이 부르는 이름. web/ibweb/httpkit.Handler(BaseHTTPRequestHandler)
    app = _web.app

    def _dispatch(self, method):
        self.app = pick_app(self.headers.get("Host"), self.path)
        return super()._dispatch(method)
