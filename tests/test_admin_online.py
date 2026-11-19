"""온라인 입구(api/index.py): 호스트 이름으로 사용자 웹 / 관리자 사이트를 고르고, 첫 관리자 만들기가 한 번만 열리는지.

임시 SQLite 를 쓰고 공인 시각 기관에는 접속하지 않는다.
"""
import http.cookiejar
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = ("IB_DATA_DIR", "DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "VERCEL", "ADMIN_SETUP_TOKEN",
            "IB_ADMIN_HOSTS")
ADMIN_HOST = "admin.test"
TOKEN = "setup-token-for-test"


class Client:
    def __init__(self, port, host):
        self.base, self.host = f"http://127.0.0.1:{port}", host
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = None

    def call(self, method, path, body=None):
        h = {"Host": self.host, "Origin": f"http://{self.host}"}
        data = None
        if method == "POST":
            h["Content-Type"] = "application/json"
            if self.csrf:
                h["X-CSRF-Token"] = self.csrf
            data = json.dumps(body or {}).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.op.open(req, timeout=30) as r:
                st, out = r.status, r.read()
        except urllib.error.HTTPError as e:
            st, out = e.code, e.read()
        try:
            j = json.loads(out)
        except ValueError:
            j = out
        if isinstance(j, dict) and j.get("csrf"):
            self.csrf = j["csrf"]
        return st, j


class AdminOnlineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ibadmin-test-")
        cls._env = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        os.environ.update(IB_DATA_DIR=cls.tmp, ADMIN_SETUP_TOKEN=TOKEN, IB_ADMIN_HOSTS=ADMIN_HOST)
        for p in (str(ROOT), str(ROOT / "web")):
            if p not in sys.path:
                sys.path.insert(0, p)
        for m in [m for m in sys.modules if m == "ibweb" or m.startswith("ibweb.")]:
            del sys.modules[m]
        spec = importlib.util.spec_from_file_location("ib_api_index_test", ROOT / "api" / "index.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.mod._web.stamper.urls = []
        cls.mod._admin.stamper.urls = []
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), cls.mod.handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.mod._web.db.conn.close()
        cls.mod._admin.db.conn.close()
        for k, v in cls._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_host_routing_and_setup(self):
        user = Client(self.port, "web.test")
        admin = Client(self.port, ADMIN_HOST)

        # 호스트에 따라 다른 앱
        self.assertIn("limits", user.call("GET", "/api/me")[1])
        self.assertIn("admin", admin.call("GET", "/api/me")[1])
        self.assertEqual(user.call("GET", "/api/dashboard")[0], 404)   # 사용자 주소에는 관리자 API 가 없다
        self.assertEqual(admin.call("POST", "/api/signup", {})[0], 404)  # 관리자 주소에는 가입 API 가 없다
        st, page = admin.call("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn(b"admin.js", page)

        # 첫 관리자 만들기: 토큰이 틀리면 거부, 맞으면 한 번만
        self.assertTrue(admin.call("GET", "/api/setup")[1]["needed"])
        body = {"token": "wrong", "username": "ceo", "name": "대표", "password": "a-long-password-123"}
        self.assertEqual(admin.call("POST", "/api/setup", body)[0], 403)
        body["token"] = TOKEN
        self.assertEqual(admin.call("POST", "/api/setup", {**body, "password": "short"})[0], 400)
        self.assertEqual(admin.call("POST", "/api/setup", body)[0], 200)
        self.assertFalse(admin.call("GET", "/api/setup")[1]["needed"])
        self.assertEqual(admin.call("POST", "/api/setup", {**body, "username": "second"})[0], 403)

        # 로그인 → 대시보드 → 원장·감사 로그 무결성
        st, me = admin.call("POST", "/api/login", {"username": "ceo", "password": "a-long-password-123"})
        self.assertEqual(st, 200, me)
        self.assertEqual(admin.call("GET", "/api/dashboard")[0], 200)
        st, led = admin.call("POST", "/api/ledger/verify", {})
        self.assertEqual(st, 200, led)
        st, aud = admin.call("GET", "/api/audit")
        self.assertTrue(aud["integrity"]["ok"])
        self.assertTrue(any(r["action"] == "첫 관리자 계정 만들기" for r in aud["audit"]))

        # 관리자 쿠키는 사용자 주소에서 쓰이지 않는다 (호스트별 쿠키)
        self.assertIsNone(user.call("GET", "/api/me")[1]["user"])


if __name__ == "__main__":
    unittest.main()
