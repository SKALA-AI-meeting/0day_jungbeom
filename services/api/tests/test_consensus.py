"""consensus.judge 단위(가짜 시각): 현재 지지는 참여자당 하나, 3/4 즉시 합의, 시간 초과 선택
4단계."""

from datetime import UTC, datetime, timedelta

from app.services.consensus import judge

T0 = datetime(2026, 10, 21, tzinfo=UTC)


def at(sec: int) -> datetime:
    return T0 + timedelta(seconds=sec)


def option(id_: str, proposer: str, sec: int) -> dict:
    return {"id": id_, "proposer": proposer, "created_at": at(sec)}


def stance(who: str, id_: str, kind: str, sec: int) -> dict:
    return {"participant": who, "option_id": id_, "stance": kind, "created_at": at(sec)}


def test_three_of_four_with_candidate_is_consensus_immediately():
    options = [option("A", "p1", 0)]
    stances = [stance("p3", "A", "support", 1)]
    assert judge(options, stances)["consensus_option_id"] is None
    stances.append(stance("candidate", "A", "support", 2))
    assert judge(options, stances)["consensus_option_id"] == "A"


def test_ai_only_majority_is_not_consensus():
    options = [option("A", "p1", 0)]
    stances = [stance("p2", "A", "support", 1), stance("p3", "A", "support", 2)]
    assert judge(options, stances)["consensus_option_id"] is None


def test_support_for_other_option_replaces_and_later_oppose_withdraws():
    options = [option("A", "p1", 0), option("B", "p3", 1)]
    stances = [stance("candidate", "A", "support", 2), stance("candidate", "B", "support", 3)]
    result = judge(options, stances)
    assert result["current_support"]["candidate"] == "B"
    assert result["supporters"]["A"] == ["p1"]
    stances.append(stance("candidate", "A", "oppose", 4))  # 다른 안 oppose는 지지를 바꾸지 않음
    assert judge(options, stances)["current_support"]["candidate"] == "B"
    stances.append(stance("candidate", "B", "oppose", 5))
    assert judge(options, stances)["current_support"]["candidate"] is None


def test_timeout_selection_most_then_candidate_then_first_then_default():
    a, b = option("A", "p1", 0), option("B", "p3", 1)
    most = judge([a, b], [stance("p2", "B", "support", 2)])
    assert most["timeout_option_id"] == "B"
    tie = judge([a, b], [stance("candidate", "B", "support", 2)])
    assert tie["supporters"]["A"] == ["p1"] and tie["timeout_option_id"] == "B"
    first = judge([a, b], [])
    assert first["timeout_option_id"] == "A"
    assert judge([], [], default_option_id="LEAD")["timeout_option_id"] == "LEAD"
