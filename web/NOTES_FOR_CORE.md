# 코어(ideabank/)에 바라는 변경 — 웹(v2) 쪽 메모

> 웹 앱은 `ideabank/` 를 고치지 않고 import 만 합니다. 아래는 코어 담당 세션이 판단해 반영하면 좋을 점입니다. 반영 전까지는 `web/ibweb/proof.py` 의 어댑터로 우회합니다.

## 1. `bundle.make()` 가 `Store` 에 묶여 있음
- 현재 `bundle.make(store, seq)` 는 `store.get()`, `store.file_path()`, `ideas.tsa_token` 열을 직접 읽습니다.
- 웹은 공인 시각을 `events` 테이블에 두므로, 같은 zip 구조를 만드는 사본 함수(`proof.make`)를 두었습니다. 안내문은 `bundle.GUIDE` 를 그대로 씁니다.
- **제안**: 저장소와 무관한 함수를 하나 두면 웹은 사본 없이 그것만 호출할 수 있습니다.
  - 형태: `bundle.build_zip(canonical: bytes, tsa_response: bytes|None, attachments: list[(name, bytes)], ledger: dict, guide_fields: dict) -> bytes`
  - `make()` 는 이 함수를 감싸는 래퍼로 바꿉니다.

## 2. `bundle.verify()` 의 원장 조회
- `verify(store, data)` 는 `store.db.execute("SELECT seq, idea_no FROM ideas WHERE content_hash=?")` 만 씁니다.
  - 웹 DB 에도 같은 열이 있어 `SimpleNamespace(db=conn)` 로 넘겨 재사용 중입니다.
- **제안**: 조회 함수를 인자로 받으면 결합이 줄어듭니다. 예: `lookup: Callable[[str], dict|None]`.
  - 결과의 check 이름 `"이 보관함 원장"` 도 상수로 빼 주세요. 웹은 지금 문자열을 비교해 `"아이디어뱅크 원장"` 으로 바꿔 표시합니다.

## 3. `bundle.verify()` 첨부 이름 비교 버그 (추정)
- `n.lstrip("attachments/")` 는 접두어가 아니라 **문자 집합**을 지웁니다.
  - 예: 첨부 이름이 `a`, `t`, `c`, `h`, `m`, `e`, `n`, `s`, `/` 로 시작하면(`notes.txt`, `chart.png` 등) 앞글자가 잘려 일치하지 않습니다.
- **제안**: `n[len("attachments/"):]` 또는 `removeprefix("attachments/")` 로 바꿔 주세요.

## 4. 원장 일반화 (TRD §10)
- 웹은 v1 과 같은 규칙(`canonical.entry_hash`)으로 `events` 테이블에 모든 이벤트를 체인합니다.
  - 아이디어 등록 이벤트의 payload 는 `ideabank/1` 정규화 JSON 원문입니다.
  - 다른 이벤트는 `{"schema": "ideabank-event/1", "kind": ..., "at": ...}` 형식이고, NDA 는 `ideabank-nda/1` 형식입니다.
- 나중에 v1 → 온라인 이전 기능을 만들 때 참고하세요.
  - v1 의 `ideas` 행은 `idea.register` 이벤트로 그대로 옮길 수 있습니다. 고유 지문과 공인 시각 토큰은 바뀌지 않습니다.
  - 다만 seq·고리값은 새 체인 기준으로 다시 계산됩니다.
- **제안**: 이벤트 스키마 문자열(`ideabank-event/1`, `ideabank-nda/1`)을 `canonical.py` 의 상수로 함께 관리하면 좋겠습니다.

## 5. 등록번호 접두어
- 웹은 v1 로컬 번호(`IB-…`)와 겹치지 않도록 `IBW-YYYYMMDD-NNNNNN` 을 씁니다.
- 공식 번호 체계를 코어에서 정하면 따르겠습니다.
