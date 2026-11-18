"""아이디어뱅크 로컬 웹 서버 — `python server.py` (TRD §6)."""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from ideabank import bundle
from ideabank.store import Store, UserError

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_BODY = 30 * 1024 * 1024
DEFAULTS = {"host": "127.0.0.1", "port": 8080, "data_dir": "data", "tz_hours": 9,
            "tsa_urls": ["http://timestamp.digicert.com", "https://freetsa.org/tsr"], "open_browser": True}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    p = ROOT / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


class Handler(BaseHTTPRequestHandler):
    store: Store = None  # type: ignore
    server_version = "IdeaBank/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    # ---------- 응답 도우미 ----------
    def send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def json(self, obj, code: int = 200):
        self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def error(self, msg: str, code: int = 400):
        self.json({"error": msg}, code)

    def attachment(self, name: str, data: bytes, ctype: str = "application/octet-stream"):
        self.send(200, data, ctype, {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise UserError("보낸 내용이 너무 큽니다 (최대 30MB).")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise UserError("요청 형식이 올바르지 않습니다.")

    # ---------- 라우팅 ----------
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method: str):
        url = urlparse(self.path)
        path = unquote(url.path)
        try:
            if path.startswith("/api/"):
                return self.api(method, path[5:], parse_qs(url.query))
            if method != "GET":
                return self.error("허용되지 않은 요청입니다.", 405)
            return self.static(path)
        except UserError as e:
            self.error(str(e), 400)
        except Exception:
            traceback.print_exc()
            self.error("서버 내부 오류가 발생했습니다. 검은 창의 메시지를 확인하세요.", 500)

    def static(self, path: str):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (STATIC / rel).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            return self.error("찾을 수 없습니다.", 404 if STATIC.resolve() in target.parents else 403)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self.send(200, target.read_bytes(), ctype)

    def api(self, method: str, p: str, qs: dict):
        s = self.store
        q = lambda k: (qs.get(k) or [""])[0]
        if method == "GET" and p == "status":
            return self.json(s.status())
        if method == "GET" and p == "tags":
            return self.json(s.tags())
        if method == "GET" and p == "guide":
            md = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
            return self.send(200, md.encode("utf-8"), "text/markdown; charset=utf-8")
        if p == "ideas":
            if method == "GET":
                return self.json(s.list(q("q"), q("tag")))
            b = self.body()
            atts = []
            for a in b.get("attachments") or []:
                try:
                    atts.append({"name": a["name"], "mime": a.get("mime"), "data": base64.b64decode(a["data_b64"])})
                except Exception:
                    raise UserError("첨부파일을 읽을 수 없습니다.")
            parent = b.get("parent_seq")
            d = s.create(title=b.get("title", ""), body=b.get("body", ""), tags=b.get("tags") or [],
                         author=b.get("author", ""), parent_seq=int(parent) if parent else None,
                         attachments=atts, timestamp=bool(b.get("timestamp", True)))
            return self.json(d, 201)
        m = re.fullmatch(r"ideas/(\d+)(?:/(timestamp|bundle|files/([0-9a-f]{64})))?", p)
        if m:
            seq, sub, sha = int(m.group(1)), m.group(2), m.group(3)
            if not sub and method == "GET":
                return self.json(s.get(seq))
            if sub == "timestamp" and method == "POST":
                return self.json(s.stamp(seq))
            if sub == "bundle" and method == "GET":
                name, data = bundle.make(s, seq)
                return self.attachment(name, data, "application/zip")
            if sha and method == "GET":
                path, a = s.file_path(seq, sha)
                return self.attachment(a["name"], path.read_bytes())
        if method == "GET" and p == "verify/chain":
            return self.json(s.verify_chain())
        if method == "POST" and p == "verify/bundle":
            b = self.body()
            try:
                data = base64.b64decode(b.get("zip_b64", ""))
            except Exception:
                raise UserError("파일을 읽을 수 없습니다.")
            return self.json(bundle.verify(s, data))
        m = re.fullmatch(r"lookup/(\w+)", p)
        if method == "GET" and m:
            return self.json(s.lookup(m.group(1)))
        return self.error("찾을 수 없는 요청입니다.", 404)


def main():
    cfg = load_config()
    args = sys.argv[1:]
    for flag, key, cast in (("--data", "data_dir", str), ("--port", "port", int)):
        if flag in args:  # 시험용 보관함: python server.py --data <폴더> --port 8081
            cfg[key] = cast(args[args.index(flag) + 1])
    Handler.store = Store(ROOT / cfg["data_dir"], cfg["tsa_urls"], cfg["tz_hours"])
    srv = ThreadingHTTPServer((cfg["host"], cfg["port"]), Handler)
    url = f"http://{'localhost' if cfg['host'] in ('127.0.0.1', '0.0.0.0') else cfg['host']}:{cfg['port']}"
    print(f"아이디어뱅크가 실행 중입니다: {url}\n이 창을 닫으면 앱이 꺼집니다. (Ctrl+C 로 종료)")
    if cfg["open_browser"] and "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
