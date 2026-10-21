"""카드 전달·기준안·관찰과 계약 테스트 C5(testing.md "수용·경청 카드")."""

from conftest import intent_of, say

FLEX, PRESSURE = "flexibility_majority", "listening_pressure"


def problem(harness, **scripts):
    h = harness("problem", **scripts)
    h.server.confirm_keyword("water")
    return h


def option_id(h, key: str) -> str:
    return next(o["option_id"] for o in h.server.options if o["scenario_option_key"] == key)


def bump_generation(h, line: dict):
    """두 번째 화자 생성 중에 새 지원자 메시지가 들어온 상황."""

    def step(_messages):
        h.server.candidate_says("잠깐만요, 하나 더 말할게요.")
        return line

    return step


async def test_c5_lead_lock_joint_delivery_and_observations(harness):
    h = problem(
        harness,
        persona=[
            say(
                "그건 핵심이 아니에요. 침수가 먼저예요.",
                {"option_id": "water_p2", "stance": "support"},
            ),
            say(
                "저도 침수 피해 쪽이 더 크다고 봐요.",
                {"option_id": "water_p2", "stance": "support"},
            ),
        ],
    )
    h.candidate("가뭄 문제가 제일 커요.", intent_of("propose", key="water_p1"))

    run = await h.run("card_due", card_id=FLEX)

    assert run.ok and run.status == "finished"
    p2 = option_id(h, "water_p2")
    # 기준안 = 지원자 현재 지지(P1)가 아닌 첫 시나리오 안(P2), 첫 담당 자리가 행을 만든다
    assert next(o for o in h.server.options if o["option_id"] == p2)["proposer"] == "p1"
    posts = h.posted()
    assert [m["sender"] for m in posts] == ["p1", "p3"]
    assert posts[0]["card_ids"] == [FLEX, PRESSURE] and posts[1]["card_ids"] == [FLEX]
    assert h.server.cards[FLEX]["delivered"] == ["p1", "p3"]
    assert h.server.cards[PRESSURE]["delivered"] == ["p1"]
    # 관찰은 카드마다 1건, 같은 trigger 메시지(공동 전달)
    assert {c: o["trigger_message_id"] for c, o in h.server.observations.items()} == {
        FLEX: posts[0]["id"],
        PRESSURE: posts[0]["id"],
    }
    assert [n for n, _ in h.assessment.calls] == ["record_observation"] * 2
    assert h.server.support["p1"] == h.server.support["p3"] == p2
    assert run.decision["speakers"][0]["purpose"] == "card"


async def test_c5_api_lock_is_used(harness):
    h = problem(
        harness, persona=[say("침수가 핵심이에요.", {"option_id": "water_p3", "stance": "support"})]
    )
    p3 = h.server.add_option("water_p3", "p1")
    h.server.lock(FLEX, p3)
    await h.run("card_due", card_id=FLEX)
    assert h.server.support["p1"] == p3


async def test_c5_dropped_card_speaker_resumes_next_run(harness):
    h = problem(
        harness,
        persona=[
            say("침수가 먼저예요.", {"option_id": "water_p2", "stance": "support"}),
        ],
    )
    h.persona.script.append(
        bump_generation(
            h, say("저도 침수 쪽이에요.", {"option_id": "water_p2", "stance": "support"})
        )
    )
    h.candidate("가뭄 문제가 제일 커요.", intent_of("propose", key="water_p1"))

    first = await h.run("card_due", card_id=FLEX)

    assert first.decision["dropped_seats"] == ["p3"]
    assert [m["sender"] for m in h.posted()] == ["p1"]
    assert h.server.cards[FLEX]["delivered"] == ["p1"]

    h.persona.script.append(
        say("저도 침수 쪽이에요.", {"option_id": "water_p2", "stance": "support"})
    )
    second = await h.run("card_due", card_id=PRESSURE)  # 같은 시각 카드의 card_due, 새 run_id

    assert [s["seat"] for s in second.decision["speakers"]] == ["p3"]
    assert second.decision["speakers"][0]["card_ids"] == [FLEX]
    assert h.server.cards[FLEX]["delivered"] == ["p1", "p3"]
    assert len(h.server.observations) == 2 and len(h.assessment.calls) == 2
    assert h.server.support["p3"] == option_id(h, "water_p2")


async def test_c5_critic_moves_after_two_counters_stubborn_holds(harness):
    support_p2 = {"option_id": "water_p2", "stance": "support"}
    h = problem(
        harness,
        persona=[say("침수가 먼저예요.", support_p2), say("저도 침수 쪽이에요.", support_p2)],
    )
    h.candidate("가뭄 문제가 제일 커요.", intent_of("propose", key="water_p1"))
    await h.run("card_due", card_id=FLEX)
    p1, p2 = option_id(h, "water_p1"), option_id(h, "water_p2")

    h.candidate("침수는 이미 대책이 많아요.", intent_of("oppose", option_id=p2))
    h.candidate("침수보다 가뭄이 더 자주 와요.", intent_of("oppose", option_id=p2))
    h.persona.script += [
        say("듣고 보니 가뭄 쪽이 맞네요.", {"option_id": p1, "stance": "support"}),
        say("그래도 침수가 핵심이에요.", support_p2),
    ]
    mid = h.candidate("지안님, 한결님 어떻게 보세요?", intent_of("question", to=("p3", "p1")))
    run = await h.run("message", message_id=mid)

    assert [s["seat"] for s in run.decision["speakers"]] == ["p3", "p1"]
    assert h.server.support["p3"] == p1  # 비판형은 지원자 안으로 이동
    assert h.server.support["p1"] == p2  # 고집형은 확정 전 불변
    assert all(m["meta"]["stance_check"] == "pass" for m in h.posted()[-2:])


async def test_critic_does_not_move_after_one_counter(harness):
    support_p2 = {"option_id": "water_p2", "stance": "support"}
    h = problem(
        harness,
        persona=[say("침수가 먼저예요.", support_p2), say("저도 침수 쪽이에요.", support_p2)],
    )
    h.candidate("가뭄 문제가 제일 커요.", intent_of("propose", key="water_p1"))
    await h.run("card_due", card_id=FLEX)
    p1, p2 = option_id(h, "water_p1"), option_id(h, "water_p2")
    h.candidate("침수는 이미 대책이 많아요.", intent_of("oppose", option_id=p2))
    h.persona.script += [
        say("듣고 보니 가뭄 쪽이 맞네요.", {"option_id": p1, "stance": "support"}),
        say("듣고 보니 가뭄 쪽이 맞네요.", {"option_id": p1, "stance": "support"}),
    ]
    mid = h.candidate("지안님 어떻게 보세요?", intent_of("question", to=("p3",)))

    await h.run("message", message_id=mid)

    last = h.posted("p3")[-1]
    assert last["meta"]["stance_check"] == "fallback"
    assert h.server.support["p3"] == p2


async def test_card_due_keyword_critic_pushes_own_keyword(harness):
    h = harness(
        "keyword",
        persona=[
            say(
                "저는 바람이 낫다고 봐요. 물은 너무 넓지 않아요?",
                {"option_id": "wind", "stance": "support"},
            )
        ],
    )
    h.candidate("물이 좋겠어요.", intent_of("propose", key="water"))
    run = await h.run("card_due", card_id="persuasion_keyword")
    assert run.decision["speakers"] == [
        {"seat": "p3", "purpose": "card", "option_id": None, "card_ids": ["persuasion_keyword"]}
    ]
    assert list(h.server.observations) == ["persuasion_keyword"]


async def test_card_due_keyword_stubborn_when_candidate_backs_wind(harness):
    h = harness(
        "keyword", persona=[say("불이 맞아요.", {"option_id": "fire", "stance": "support"})]
    )
    h.candidate("바람이 좋겠어요.", intent_of("propose", key="wind"))
    run = await h.run("card_due", card_id="persuasion_keyword")
    assert [s["seat"] for s in run.decision["speakers"]] == ["p1"]


async def test_inclusion_silence_fixed_line_without_llm(harness):
    h = harness("solution")
    h.server.confirm_keyword("water")
    run = await h.run("card_due", card_id="inclusion_silence")
    post = h.posted("p2")[0]
    assert post["content"] == h.server.catalog.card("inclusion_silence")["fixed_line"]
    assert post["card_ids"] == ["inclusion_silence"] and not h.persona.calls
    assert run.ok and list(h.server.observations) == ["inclusion_silence"]


async def test_persuasion_solution_swaps_actor_not_stance(harness):
    h = harness(
        "solution",
        persona=[say("센서 데이터가 먼저예요.", {"option_id": "water_s1", "stance": "support"})],
    )
    h.server.confirm_keyword("water")
    h.candidate("주민 캠페인이 좋겠어요.", intent_of("propose", key="water_s2"))
    run = await h.run("card_due", card_id="persuasion_solution")
    assert [s["seat"] for s in run.decision["speakers"]] == ["p1"]
    assert h.server.support["p1"] == option_id(h, "water_s1")
    assert h.server.support["p3"] is None


async def test_honesty_credit_observed_on_proposal_start(harness):
    h = harness("proposal")
    h.server.confirm_keyword("water")
    notice = h.server.system_says("기획안 작성 단계예요.")
    run = await h.run("phase_started")
    assert run.decision["speakers"] == [] and not h.posted()
    assert h.server.observations["honesty_credit"]["trigger_message_id"] == notice
