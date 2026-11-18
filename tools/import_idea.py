"""이미 공인 시각을 받은 기록 폴더(canonical.json + token.tsr)를 보관함 원장에 옮겨 담는다.

사용법:  python tools/import_idea.py ideas/IB-20261118-000001
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ideabank.store import Store  # noqa: E402
from server import load_config  # noqa: E402


def main(folder: str):
    f = Path(folder)
    cfg = load_config()
    s = Store(ROOT / cfg["data_dir"], cfg["tsa_urls"], cfg["tz_hours"])
    tsr = f / "token.tsr"
    url = None
    proof = f / "proof.txt"
    if proof.exists():
        for line in proof.read_text(encoding="utf-8").splitlines():
            if line.startswith("시각 기관"):
                url = line.split(None, 2)[-1].strip()
    d = s.import_record((f / "canonical.json").read_bytes(), tsr.read_bytes() if tsr.exists() else None, f.name, url)
    print(f"가져옴: {d['idea_no']} (원장 {d['seq']}번) 공인 시각 {d['tsa_time']}")


if __name__ == "__main__":
    main(sys.argv[1])
