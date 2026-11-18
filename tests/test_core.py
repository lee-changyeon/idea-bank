"""코어 단위·변조 테스트 — `python -m unittest discover -s tests` (TASK T4.1, T4.2).

공인 시각 기관에는 접속하지 않는다 (tsa_urls 를 비워 둠). 실연동은 T4.3 에서 따로 확인.
"""
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ideabank import bundle, canonical as C, tsa  # noqa: E402
from ideabank.store import Store, UserError  # noqa: E402


class CanonicalTest(unittest.TestCase):
    def doc(self, **kw):
        base = dict(title=" 제목 ", body="첫 줄\r\n둘째 줄", tags=["b", "#a", "b", " "], author="홍",
                    created_at="2026-11-18T00:00:00.000Z", parent=None, attachments=[])
        base.update(kw)
        return C.build(**base)

    def test_stable_bytes(self):
        a, b = C.dumps(self.doc()), C.dumps(self.doc())
        self.assertEqual(a, b)
        d = json.loads(a)
        self.assertEqual(d["tags"], ["a", "b"])
        self.assertEqual(d["body"], "첫 줄\n둘째 줄")
        self.assertEqual(d["title"], "제목")

    def test_nfc(self):
        nfd = "가"  # 'ㄱ'+'ㅏ' 조합형 → '가'
        self.assertEqual(self.doc(body=nfd)["body"], "가")

    def test_one_char_changes_hash(self):
        self.assertNotEqual(C.sha256_hex(C.dumps(self.doc())), C.sha256_hex(C.dumps(self.doc(body="첫 줄\n둘째 줄!"))))


class TsaDerTest(unittest.TestCase):
    def test_request_shape(self):
        req = tsa.build_request(bytes(32), 12345)
        self.assertEqual(req[0], 0x30)
        self.assertIn(tsa.SHA256_OID, req)
        self.assertIn(b"\x04\x20" + bytes(32), req)
        self.assertTrue(req.endswith(b"\x01\x01\xff"))

    def test_real_token_from_idea1(self):
        folder = Path(__file__).resolve().parents[1] / "ideas" / "IB-20261118-000001"
        if not (folder / "token.tsr").exists():
            self.skipTest("1호 아이디어 토큰 없음")
        raw = (folder / "canonical.json").read_bytes()
        t = tsa.parse_response((folder / "token.tsr").read_bytes(), bytes.fromhex(C.sha256_hex(raw)))
        self.assertEqual(t["gen_time"], "2026-11-18T05:14:34Z")
        with self.assertRaises(ValueError):
            tsa.token_time((folder / "token.tsr").read_bytes(), bytes(32))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.s = Store(self.tmp, tsa_urls=[])

    def tearDown(self):
        self.s.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, title="우산꽂이", body="자전거 거치대와 합침", **kw):
        return self.s.create(title=title, body=body, timestamp=False, **kw)

    def raw_db(self):
        return sqlite3.connect(Path(self.tmp) / "ideabank.db", isolation_level=None)

    def test_create_and_chain(self):
        a = self.add(tags=["생활"], author="홍길동")
        b = self.add(title="둘째")
        self.assertEqual(a["seq"], 1)
        self.assertEqual(a["prev_hash"], C.GENESIS)
        self.assertEqual(b["prev_hash"], a["entry_hash"])
        self.assertRegex(a["idea_no"], r"^IB-\d{8}-000001$")
        self.assertTrue(a["tsa_pending"])
        self.assertTrue(self.s.verify_chain()["ok"])

    def test_validation(self):
        with self.assertRaises(UserError):
            self.add(title=" ")
        with self.assertRaises(UserError):
            self.add(body="")

    def test_revision_lineage(self):
        a = self.add()
        b = self.s.create(title="v2", body="개선", parent_seq=a["seq"], timestamp=False)
        c = self.s.create(title="v3", body="또 개선", parent_seq=b["seq"], timestamp=False)
        self.assertEqual((b["version"], c["version"]), (2, 3))
        self.assertEqual(json.loads(b["canonical"])["parent"], a["content_hash"])
        self.assertEqual([x["version"] for x in self.s.get(a["seq"])["lineage"]], [1, 2, 3])

    def test_attachment_and_lookup(self):
        d = self.add(attachments=[{"name": "../스케치.png", "mime": "image/png", "data": b"PNGDATA"}])
        a = d["attachments"][0]
        self.assertEqual(a["name"], "스케치.png")
        self.assertEqual(a["sha256"], C.sha256_hex(b"PNGDATA"))
        hit = self.s.lookup(a["sha256"])
        self.assertEqual(hit["files"][0]["seq"], d["seq"])
        self.assertEqual(self.s.lookup(d["content_hash"])["ideas"][0]["seq"], d["seq"])

    def test_search(self):
        self.add(title="자전거 우산", tags=["생활"])
        self.add(title="AI 회의실", body="화상회의")
        self.assertEqual(len(self.s.list("회의")), 1)
        self.assertEqual(len(self.s.list(tag="생활")), 1)
        self.assertEqual(self.s.tags(), ["생활"])

    # ---- 변조 시나리오 (T4.2) ----
    def test_tamper_body(self):
        self.add(); self.add()
        db = self.raw_db()
        raw = db.execute("SELECT canonical FROM ideas WHERE seq=1").fetchone()[0]
        db.execute("UPDATE ideas SET canonical=?, body=? WHERE seq=1",
                   (bytes(raw).replace("합침".encode(), "분리".encode()), "자전거 거치대와 분리"))
        r = self.s.verify_chain()
        self.assertFalse(r["ok"])
        self.assertEqual(r["broken"][0]["seq"], 1)

    def test_tamper_display_only(self):
        self.add()
        self.raw_db().execute("UPDATE ideas SET title='바뀐 제목' WHERE seq=1")
        self.assertFalse(self.s.verify_chain()["ok"])

    def test_delete_row(self):
        self.add(); self.add(); self.add()
        self.raw_db().execute("DELETE FROM ideas WHERE seq=2")
        r = self.s.verify_chain()
        self.assertFalse(r["ok"])
        self.assertEqual(r["broken"][0]["seq"], 3)

    def test_recompute_hash_breaks_chain(self):
        """내용과 고유 지문을 함께 고쳐도 다음 고리와 맞지 않는다."""
        self.add(); self.add()
        db = self.raw_db()
        raw = bytes(db.execute("SELECT canonical FROM ideas WHERE seq=1").fetchone()[0]).replace("합침".encode(), "분리".encode())
        doc = json.loads(raw)
        db.execute("UPDATE ideas SET canonical=?, body=?, content_hash=? WHERE seq=1", (raw, doc["body"], C.sha256_hex(raw)))
        self.assertFalse(self.s.verify_chain()["ok"])

    def test_swap_attachment_file(self):
        d = self.add(attachments=[{"name": "a.txt", "data": b"original"}])
        (Path(self.tmp) / "files" / d["attachments"][0]["sha256"]).write_bytes(b"forged")
        self.assertFalse(self.s.verify_chain()["ok"])

    # ---- 증명 파일 ----
    def test_bundle_roundtrip_and_tamper(self):
        import io, zipfile
        d = self.add(attachments=[{"name": "a.txt", "data": b"hello"}])
        name, data = bundle.make(self.s, d["seq"])
        self.assertTrue(name.endswith("-증명.zip"))
        r = bundle.verify(self.s, data)
        checks = {c["name"]: c["ok"] for c in r["checks"]}
        self.assertTrue(checks["원문 형식"] and checks["첨부 'a.txt'"] and checks["이 보관함 원장"])
        self.assertFalse(checks["공인 시각"])  # 테스트에서는 공인 시각 없음
        # 첨부를 바꿔치기한 번들
        src = zipfile.ZipFile(io.BytesIO(data)); buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n in src.namelist():
                z.writestr(n, b"evil" if n == "attachments/a.txt" else src.read(n))
        bad = {c["name"]: c["ok"] for c in bundle.verify(self.s, buf.getvalue())["checks"]}
        self.assertFalse(bad["첨부 'a.txt'"])
        with self.assertRaises(UserError):
            bundle.verify(self.s, b"not a zip")

    def test_import_idea1(self):
        folder = Path(__file__).resolve().parents[1] / "ideas" / "IB-20261118-000001"
        if not (folder / "token.tsr").exists():
            self.skipTest("1호 아이디어 없음")
        d = self.s.import_record((folder / "canonical.json").read_bytes(), (folder / "token.tsr").read_bytes(),
                                 "IB-20261118-000001", "http://timestamp.digicert.com")
        self.assertEqual(d["tsa_time"], "2026-11-18T05:14:34Z")
        self.assertEqual(d["content_hash"], "0db6370c3e221c511815c449695bde72c425e5805399c9e106863eec54ec1cd6")
        self.assertTrue(self.s.verify_chain()["ok"])
        with self.assertRaises(UserError):
            self.s.import_record((folder / "canonical.json").read_bytes(), None, "IB-x")


if __name__ == "__main__":
    unittest.main()
