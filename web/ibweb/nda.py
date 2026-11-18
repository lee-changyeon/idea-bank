"""표준 비밀유지 약정(NDA) 템플릿. 클릭 서명 방식(모의 전자서명)."""
from __future__ import annotations

from ideabank import canonical as C

VERSION = "NDA-IB-2026-v1"

TEMPLATE = """아이디어 열람 비밀유지 약정서 ({version})

열람자(이하 "을")는 아이디어뱅크에 적립된 아래 아이디어(이하 "대상 아이디어")의 전문을 열람하기 전에,
창안자(이하 "갑")에게 다음과 같이 약정합니다.

제1조 (목적) 을은 대상 아이디어를 사용권 허락(아이디어 대출) 협의를 검토하는 목적으로만 열람합니다.
제2조 (비밀유지) 을은 대상 아이디어의 내용을 갑의 서면 동의 없이 제3자에게 알리거나 공개하지 않습니다. 검토에 꼭 필요한 임직원·자문가에게 알리는 경우, 그들에게도 같은 의무를 지웁니다.
제3조 (사용 금지) 을은 갑과 사용권 약정을 맺기 전에는 대상 아이디어를 사업에 쓰거나, 이를 바탕으로 한 제품·서비스를 만들거나, 특허·디자인·상표 출원에 쓰지 않습니다.
제4조 (예외) 다음 정보는 비밀유지 대상이 아닙니다. ① 열람 전에 이미 공개된 정보  ② 을이 열람 전에 이미 가지고 있었음을 서면으로 증명할 수 있는 정보 ③ 을의 잘못 없이 공개된 정보  ④ 법령이나 법원 명령으로 공개해야 하는 정보
제5조 (열람 기록) 을은 아이디어뱅크가 을의 열람 사실(열람자, 시각, 대상 아이디어의 고유 지문)을 원장에 기록하고 공인 시각을 받아 갑에게 보여 주는 데 동의합니다. 이 기록은 분쟁 시 증거로 쓸 수 있습니다.
제6조 (기간) 이 약정은 서명일부터 3년간 효력이 있습니다.
제7조 (위반) 을이 이 약정을 위반하면 갑이 입은 손해를 배상합니다. 갑은 부정경쟁방지 및 영업비밀보호에 관한 법률 등에 따른 권리를 따로 행사할 수 있습니다.
제8조 (전자 서명) 을이 아래에 성명을 입력하고 동의 버튼을 누르면 이 약정에 서명한 것으로 봅니다. 서명 내용(이 약정문의 고유 지문 포함)은 원장에 기록되고 공인 시각을 받습니다.

※ 표준 초안입니다. 정식 서비스 전에 변호사 검토가 필요합니다.
""".format(version=VERSION)

TEMPLATE_HASH = C.sha256_hex(C.text(TEMPLATE).encode("utf-8"))


def build_doc(*, idea: dict, signer_name: str, org: str, user_id: int, email: str, signed_at: str, ip: str) -> bytes:
    """서명 문서 = 약정 템플릿의 고유 지문 + 대상 아이디어의 고유 지문 + 서명자 정보. 이 문서의 해시가 NDA 문서 해시."""
    return C.dumps({
        "schema": "ideabank-nda/1",
        "template": {"version": VERSION, "sha256": TEMPLATE_HASH},
        "idea": {"idea_no": idea["idea_no"], "content_hash": idea["content_hash"], "title": idea["title"]},
        "signer": {"user_id": user_id, "name": C.text(signer_name).strip(), "org": C.text(org).strip(), "email": email},
        "method": "click-through (아이디어뱅크 웹, 성명 입력 + 동의)",
        "ip": ip,
        "signed_at": signed_at,
    })
