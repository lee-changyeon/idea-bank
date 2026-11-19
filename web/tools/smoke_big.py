"""온라인 큰 첨부(20MB) 점검: Storage 직접 올리기 → 등록 → 서명 주소로 내려받기 → 증명 파일 검증 → 사업자 NDA 후 열람.

    python web/tools/smoke_big.py https://<배포 주소> [MB]

매번 새 무작위 계정을 만든다(이메일 smoke-big-…@example.com).
"""
from __future__ import annotations

import hashlib
import io
import os
import secrets
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke import Client, check, v1_verify  # noqa: E402


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ideabank-smoke/1"}), timeout=120) as r:
        return r.read()


def put(url: str, data: bytes, mime: str):
    req = urllib.request.Request(url, data=data, method="PUT", headers={"Content-Type": mime, "x-upsert": "false"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status


def run(base: str, mb: int = 20):
    tag = secrets.token_hex(4)
    pw = secrets.token_urlsafe(12)
    print(f"[큰 첨부 점검] {base}  ({mb}MB, 계정 접미사 {tag})")
    cr = Client(base)
    me = cr.call("GET", "/api/me")
    check(me["limits"].get("direct") and me["limits"]["max_file"] >= mb * 1048576,
          f"직접 올리기 켜짐, 파일당 {me['limits']['max_file'] // 1048576}MB")
    cr.call("POST", "/api/signup", {"email": f"smoke-big-c-{tag}@example.com", "password": pw,
                                    "name": f"큰첨부{tag}", "role": "creator", "org": ""})
    data = os.urandom(mb * 1048576 - 7) + b"IDEABNK"
    sha = hashlib.sha256(data).hexdigest()
    up = cr.call("POST", "/api/my/uploads", {"name": "big.bin", "size": len(data), "mime": "application/octet-stream"})
    check(up["path"].startswith("incoming/"), "올리기 주소 받음")
    check(put(up["url"], data, "application/octet-stream") in (200, 201), f"Storage 로 직접 올림 ({mb}MB)")
    other = cr.call("POST", "/api/my/uploads", {"name": "x", "size": 21 * 1048576}, expect=400)
    check("MB" in other["error"], "20MB 넘는 파일은 거부")

    idea = cr.call("POST", "/api/my/ideas", {
        "title": f"큰 첨부 점검 {tag}", "body": f"[무엇] 큰 첨부 {tag}", "tags": ["점검"], "disclosure": "nda",
        "summary": "큰 첨부 점검용 요약", "timestamp": True,
        "attachments": [{"name": "big.bin", "mime": "application/octet-stream", "upload_path": up["path"]}]})
    seq = idea["seq"]
    check(idea["attachments"][0]["sha256"] == sha and idea["attachments"][0]["size"] == len(data),
          f"등록 {idea['idea_no']}: 서버가 확인한 고유 지문 일치")
    check(bool(idea["tsa_time"]), f"공인 시각 {idea['tsa_time']}")

    d = cr.call("GET", f"/api/my/ideas/{seq}/files/{sha}")
    check("download_url" in d, "내려받기: 서명 주소 받음")
    check(hashlib.sha256(fetch(d["download_url"])).hexdigest() == sha, "서명 주소에서 받은 파일이 원본과 같음")

    b = cr.call("GET", f"/api/my/ideas/{seq}/bundle")
    check("download_url" in b, "큰 증명 파일: 서명 주소 받음")
    z = fetch(b["download_url"])
    zf = zipfile.ZipFile(io.BytesIO(z))
    check(hashlib.sha256(zf.read("attachments/big.bin")).hexdigest() == sha, f"증명 파일({len(z) // 1048576}MB) 안 첨부 일치")
    check(v1_verify(z)["ok"], "v1 검증기: 이상 없음")

    biz = Client(base)
    biz.call("POST", "/api/signup", {"email": f"smoke-big-b-{tag}@example.com", "password": pw,
                                     "name": f"큰사업자{tag}", "role": "business", "org": "점검회사"})
    m = biz.call("GET", f"/api/market/{seq}")
    biz.call("POST", f"/api/market/{seq}/nda", {"signer_name": f"큰사업자{tag}", "agree": True,
                                                "template_hash": m["nda_template"]["sha256"]})
    f = biz.call("GET", f"/api/market/{seq}/files/{sha}")
    check(hashlib.sha256(fetch(f["download_url"])).hexdigest() == sha, "사업자: NDA 후 첨부 내려받기 일치")
    views = {v["level"] for v in cr.call("GET", "/api/my/views")["views"] if v["idea_seq"] == seq}
    check("file" in views, "창안자에게 첨부 열람 기록이 보임")
    led = Client(base).call("GET", "/api/ledger/verify")
    check(led["ok"], f"원장 무결성 ({led['count']}건)")
    print("[큰 첨부 점검] 모두 통과")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(args[0], int(args[1]) if len(args) > 1 else 20)
