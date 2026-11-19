"""첨부·계약서 파일 저장소. 파일 이름은 내용의 sha256 (같은 파일은 한 번만 저장, 저장 뒤 불변).

- 로컬: web/data/files/<sha256>  (지금까지와 같음)
- 온라인: Supabase Storage 비공개 버킷 (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY 가 있을 때)
  표준 라이브러리 urllib 로 Storage REST API 를 직접 부른다. 키는 환경 변수에만 둔다.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

from .db import DATA_DIR

_SHA = re.compile(r"^[0-9a-f]{64}$")
# 브라우저가 직접 올리는 임시 파일: incoming/<사용자 id>/<무작위 32자>
INCOMING = re.compile(r"^incoming/(\d+)/[0-9a-f]{32}$")
BUNDLE = re.compile(r"^bundles/[0-9a-f]{64}\.zip$")


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

    # ── 브라우저 직접 올리기·내려받기 (Vercel 함수의 4.5MB 요청·응답 한도를 피한다) ──
    def _json(self, method, path, obj, timeout=30):
        st, out = self._req(method, path, json.dumps(obj).encode(), {"Content-Type": "application/json"}, timeout)
        try:
            return st, json.loads(out or b"{}")
        except ValueError:
            return st, {"raw": out[:200]}

    def sign_upload(self, key: str) -> str:
        """브라우저가 PUT 으로 한 번 올릴 수 있는 주소 (2시간 유효, 덮어쓰기 불가)."""
        assert INCOMING.match(key)
        self._ensure_bucket()
        st, out = self._json("POST", f"/object/upload/sign/{self.bucket}/{key}", {})
        if st not in (200, 201) or "url" not in out:
            raise RuntimeError(f"올리기 주소를 만들지 못했습니다 ({st}): {out}")
        return self.base + out["url"]

    def sign_download(self, key: str, filename: str, expires: int = 300) -> str:
        """잠깐(기본 5분) 쓸 수 있는 내려받기 주소. 파일 이름을 붙여 바로 저장되게 한다."""
        assert _SHA.match(key) or BUNDLE.match(key)
        st, out = self._json("POST", f"/object/sign/{self.bucket}/{key}", {"expiresIn": expires})
        url = out.get("signedURL") or out.get("signedUrl")
        if st not in (200, 201) or not url:
            raise RuntimeError(f"내려받기 주소를 만들지 못했습니다 ({st}): {out}")
        return f"{self.base}{url}&download={quote(filename)}"

    def get_key(self, key: str) -> bytes:
        assert INCOMING.match(key) or BUNDLE.match(key)
        st, out = self._req("GET", f"/object/authenticated/{self.bucket}/{key}", timeout=60)
        if st != 200:
            raise FileNotFoundError(key)
        return out

    def put_key(self, key: str, data: bytes):
        assert BUNDLE.match(key)
        self._ensure_bucket()
        st, out = self._req("POST", f"/object/{self.bucket}/{key}", data,
                            {"Content-Type": "application/zip", "x-upsert": "true"}, timeout=60)
        if st not in (200, 201):
            raise RuntimeError(f"Storage 저장 실패 ({st}): {out[:200]!r}")

    def adopt(self, key: str, sha: str):
        """임시 업로드를 내용 해시 이름으로 옮긴다. 같은 내용이 이미 있으면 임시 파일만 지운다."""
        assert INCOMING.match(key) and _SHA.match(sha)
        st, _ = self._json("POST", "/object/move", {"bucketId": self.bucket, "sourceKey": key, "destinationKey": sha})
        if st not in (200, 201):
            self.delete_keys([key])

    def delete_keys(self, keys: list[str]):
        if keys:
            self._json("DELETE", f"/object/{self.bucket}", {"prefixes": keys})

    def cleanup(self, max_age_hours: float = 24) -> int:
        """등록되지 않고 남은 임시 업로드와 오래된 증명 파일 zip 을 지운다 (Cron)."""
        now, old = time.time(), []
        for prefix in ("incoming/", "bundles/"):
            st, items = self._json("POST", f"/object/list/{self.bucket}", {"prefix": prefix, "limit": 1000})
            for it in items if isinstance(items, list) else []:
                if it.get("id") is None:  # 폴더(incoming/<사용자 id>)
                    st2, sub_items = self._json("POST", f"/object/list/{self.bucket}",
                                                {"prefix": prefix + it["name"] + "/", "limit": 1000})
                    for s in sub_items if isinstance(sub_items, list) else []:
                        if _old(s, now, max_age_hours):
                            old.append(prefix + it["name"] + "/" + s["name"])
                elif _old(it, now, max_age_hours):
                    old.append(prefix + it["name"])
        self.delete_keys(old)
        return len(old)


def _old(item: dict, now: float, hours: float) -> bool:
    try:
        t = datetime.fromisoformat(str(item.get("created_at")).replace("Z", "+00:00"))
        return now - t.replace(tzinfo=t.tzinfo or timezone.utc).timestamp() > hours * 3600
    except ValueError:
        return False


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


def direct() -> bool:
    """브라우저가 Storage 로 직접 올리고 받는가 (온라인). 로컬은 서버를 거친다."""
    return store().kind == "supabase"
