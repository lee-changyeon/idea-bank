"""사용자 웹(web/) 전체 흐름 — 임시 SQLite 로 서버를 띄워 web/tools/smoke.py 를 돌린다.

공인 시각 기관에는 접속하지 않는다 (tsa_urls 를 비움). 개발용 DB(web/data)는 건드리지 않는다.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = ("IB_DATA_DIR", "DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "VERCEL")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WebFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ibweb-test-")
        cls._env = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        os.environ["IB_DATA_DIR"] = cls.tmp
        for p in (str(ROOT), str(ROOT / "web")):
            if p not in sys.path:
                sys.path.insert(0, p)
        # ibweb.db 가 이미 다른 DATA_DIR 로 import 됐으면 다시 불러온다
        for m in [m for m in sys.modules if m == "ibweb" or m.startswith("ibweb.")]:
            del sys.modules[m]
        cls.mod = _load("ib_web_server_test", ROOT / "web" / "server.py")
        cls.mod.stamper.urls = []  # 오프라인
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), cls.mod.app.handler())
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.smoke = _load("ib_smoke", ROOT / "web" / "tools" / "smoke.py")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.mod.db.conn.close()
        for k, v in cls._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_zip_bomb_rejected(self):
        import base64, io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("canonical.json", b"{}")
            z.writestr("attachments/big.bin", bytes(30 * 1024 * 1024))  # 풀면 30MB, 압축하면 수십 KB
        with self.assertRaises(ValueError):
            self.mod.proof.check_zip(buf.getvalue())
        c = self.smoke.Client(f"http://127.0.0.1:{self.srv.server_address[1]}")
        c.call("POST", "/api/verify/bundle", {"zip_b64": base64.b64encode(buf.getvalue()).decode()}, expect=400)

    def test_decimal_json(self):
        from decimal import Decimal
        from ibweb.httpkit import _json_default
        self.assertEqual(_json_default(Decimal("12")), 12)
        self.assertEqual(_json_default(Decimal("1.5")), 1.5)

    def test_full_flow(self):
        out = self.smoke.run(f"http://127.0.0.1:{self.srv.server_address[1]}", expect_tsa=False)
        self.assertTrue(out["ledger"]["ok"])
        self.assertTrue((Path(self.tmp) / "ideabank_web.db").exists())
        self.assertTrue(any((Path(self.tmp) / "files").iterdir()))


if __name__ == "__main__":
    unittest.main()
