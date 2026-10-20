"""완료 기준(G2-A7·G3-B1): 계약 비교가 잘못된 계약 값·필수 필드 null·필수 키 누락과 단계에
맞지 않는 상태 값·null을 거부한다."""

import copy

import pytest

from tests.contract import assert_contract, assert_shape, load_contract


def test_contract_check_rejects_wrong_values():
    state = load_contract("state")
    assert_contract(state, "state")  # 정본 자체는 통과

    for mutate in (
        lambda s: s["session"].__setitem__("status", "banana"),
        lambda s: s["messages"][0].__setitem__("channel", "banana"),
        lambda s: s["session"].__setitem__("status", None),
    ):
        broken = copy.deepcopy(state)
        mutate(broken)
        with pytest.raises(AssertionError):
            assert_shape(broken, state, "state")

    reporting = load_contract("state_reporting")
    del reporting["session"]["deadline_at"]
    with pytest.raises(AssertionError):
        assert_contract(reporting, "state_reporting")

    # 단계별 검사(관문 3 리뷰 B1): 세션 자리에 보드 상태 값, reporting인데 deadline_at null
    for mutate in (
        lambda s: s["session"].__setitem__("status", "todo"),
        lambda s: s["session"].__setitem__("deadline_at", None),
    ):
        broken = load_contract("state_reporting")
        mutate(broken)
        with pytest.raises(AssertionError):
            assert_contract(broken, "state_reporting")
