"""완료 기준: estimate_reuse 예시 2개(verbatim 1.0, edited 0.5)."""

from app.services.reuse import Revision, estimate_reuse

# 정규화(공백·구두점 제거) 뒤 길이가 정확히 120자가 되도록 만든 어시스턴트 응답
FIRST = (
    "재참여율을높이려면첫모임직후에다음모임일정을바로잡아주는기능이필요합니다"
    "참여자의절반이정말다음일정을몰라서다시오지않아요"
)
SECOND = (
    "모임장이두번째모임을열때지난참여자에게개별알림을보내고"
    "응답을한곳에모아보여주는화면을제안합니다짧은리마인드가효과적이에요"
)
RESPONSE = f"{FIRST[:30]} {FIRST[30:]}. {SECOND[:40]}, {SECOND[40:]}!"


def test_estimate_reuse_examples():
    assert (len(FIRST), len(SECOND)) == (60, 60)

    pasted = [
        Revision(part_no=2, revision=1, content="초안"),
        Revision(part_no=1, revision=3, content=f"배경 설명.\n{RESPONSE}\n끝."),
    ]
    assert estimate_reuse(RESPONSE, pasted) == ("verbatim", 1.0, 1, 3)

    half = [
        Revision(part_no=4, revision=2, content=f"제 생각은 이렇습니다. {FIRST[:30]} {FIRST[30:]}")
    ]
    assert estimate_reuse(RESPONSE, half) == ("edited", 0.5, 4, 2)
