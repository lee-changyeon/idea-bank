"""첨부·계약서 파일 저장소. 파일 이름은 내용의 sha256 (같은 파일은 한 번만 저장, 저장 뒤 불변).

- 로컬: web/data/files/<sha256>  (지금까지와 같음)
- 온라인: Supabase Storage 비공개 버킷 (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY 가 있을 때)
  표준 라이브러리 urllib 로 Storage REST API 를 직접 부른다. 키는 환경 변수에만 둔다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .db import DATA_DIR

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _check(sha: str) -> str:
    if not _SHA.match(sha or ""):
        raise ValueError("bad file id")
    return sha


class LocalFiles:
    kind = "local"

    def __init__(self):
        self.dir = DATA_DIR / "files"

    def put(self, sha: str, data: bytes):
        p = self.dir / _check(sha)
        if not p.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def get(self, sha: str) -> bytes:
        return (self.dir / _check(sha)).read_bytes()

    def exists(self, sha: str) -> bool:
        return (self.dir / _check(sha)).exists()


class SupabaseFiles:
    kind = "supabase"

    def __init__(self, url: str, key: str, bucket: str):
        self.base = url.rstrip("/") + "/storage/v1"
        self.key = key
        self.bucket = bucket
        self._bucket_ok = False

    def _req(self, method: str, path: str, data: bytes | None = None, headers: dict | None = None, timeout=30):
        h = {"Authorization": f"Bearer {self.key}", "apikey": self.key, **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _ensure_bucket(self):
        if self._bucket_ok:
            return
        st, _ = self._req("GET", f"/bucket/{self.bucket}")
        if st != 200:
            body = json.dumps({"id": self.bucket, "name": self.bucket, "public": False}).encode()
            st, out = self._req("POST", "/bucket", body, {"Content-Type": "application/json"})
            if st not in (200, 201) and b"already exists" not in out.lower() and b"duplicate" not in out.lower():
                raise RuntimeError(f"Storage 버킷을 만들지 못했습니다 ({st}): {out[:200]!r}")
        self._bucket_ok = True

    def put(self, sha: str, data: bytes):
        _check(sha)
        self._ensure_bucket()
        st, out = self._req("POST", f"/object/{self.bucket}/{sha}", data,
                            {"Content-Type": "application/octet-stream", "x-upsert": "false"}, timeout=60)
        if st in (200, 201):
            return
        # 같은 이름(= 같은 내용)이 이미 있으면 성공으로 본다
        if st in (400, 409) and (b"exists" in out.lower() or b"duplicate" in out.lower()):
            return
        raise RuntimeError(f"Storage 저장 실패 ({st}): {out[:200]!r}")

    def get(self, sha: str) -> bytes:
        st, out = self._req("GET", f"/object/authenticated/{self.bucket}/{_check(sha)}", timeout=60)
        if st != 200:
            raise FileNotFoundError(sha)
        return out

    def exists(self, sha: str) -> bool:
        st, _ = self._req("HEAD", f"/object/authenticated/{self.bucket}/{_check(sha)}")
        return st == 200


_store = None


def store():
    global _store
    if _store is None:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if url and key:
            _store = SupabaseFiles(url, key, os.environ.get("IB_STORAGE_BUCKET", "ideabank-files").strip())
        else:
            _store = LocalFiles()
    return _store


def put(sha: str, data: bytes):
    store().put(sha, data)


def get(sha: str) -> bytes:
    return store().get(sha)


def exists(sha: str) -> bool:
    return store().exists(sha)
