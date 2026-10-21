"""Dialogue harness (app/harness/dialogue.py + graph/llm wiring): ledger, speaker policy, repetition guard, markups, flag."""
import asyncio
import json
import re
from pathlib import Path

import pytest

from app import llm as llm_mod
from app.dilemmas import build_cached
from app.graph import build_graph
from app.harness import dialogue
from app.harness.events import EventPublisher, MemorySink
from app.harness.loop import Limits
from app.harness.observability import Tracer
from app.harness.runtime import TaskContext, bind, unbind
from app.llm import MockLLM

SCN = build_cached("dl.pm.fintech")  # lead 한서윤 (절차), peer 이도현 (먼저 출시)
BASELINE = Path(__file__).resolve().parents[2] / "docs" / "eval" / "baseline_e2e_transcript.txt"
CONTRACT_KEYS = {"version", "summary", "issues", "commitments", "positions", "turns", "markups_seen", "cited"}


def session(**kw) -> dict:
    s = {"id": "s1", "alias": "지우", "scenario_id": "dl.pm.fintech", "status": "active", "milestone_idx": 0, "turns_in_milestone": 0,
         "condition": {"lead": "avoiding", "peer": "collaborating"}, "choice": None,
         "messages": [{"idx": 0, "speaker": "lead", "text": "금요일 마감은 그대로인데 개인정보·보안 검토가 다음 주 화요일로 밀렸어요.",
                       "sources": [], "milestone": "communicate", "ts": 0.0}],
         "artifacts": [], "annotations": [], "dialogue": None}
    s.update(kw)
    return s


async def run_turn(sess: dict, text: str, llm=None, ctx: TaskContext | None = None) -> dict:
    token = bind(ctx) if ctx else None
    try:
        state = {"session": {**sess}, "user_text": text, "user_idx": len(sess["messages"]), "milestone_idx": sess["milestone_idx"],
                 "observations": [], "new_messages": []}
        cfg = {"configurable": {"llm": llm or MockLLM()}, "recursion_limit": Limits().max_graph_steps}
        return await build_graph().ainvoke(state, config=cfg)
    finally:
        if token:
            unbind(token)


def apply(sess: dict, text: str, final: dict) -> dict:
    """What runner._turn + Spring do with a turn result (enough for multi-turn tests)."""
    user = {"idx": len(sess["messages"]), "speaker": "user", "text": text, "milestone": "communicate", "ts": 0.0}
    return {**sess, "messages": [*sess["messages"], user, *final["new_messages"]], "milestone_idx": final["milestone_idx_after"],
            "turns_in_milestone": final["turns_after"], "dialogue": final.get("dialogue")}


def task_ctx() -> TaskContext:
    return TaskContext("t", "s1", 1, EventPublisher("t", MemorySink()), Tracer("t"))


# ---------- ledger ----------
def test_ledger_update_keeps_ids_dedupes_commitments_and_compacts():
    hist = [{"idx": 0, "speaker": "lead", "text": "검토가 밀렸어요."}, {"idx": 1, "speaker": "user", "text": "범위가 어디까지인가요?"},
            {"idx": 2, "speaker": "peer", "text": "먼저 내고 보완하죠."}]
    led = dialogue.new_ledger()
    assert dialogue.pending(led, hist) == hist
    upd = {"summary": "가" * 900, "issues": [{"title": "검토가 필요한 범위", "status": "open", "raised_by": "user"}],
           "new_commitments": [{"who": "user", "what": "검토팀에 필수 항목 검토 요청 보내기", "due": "오늘 3시까지", "idx": 1}],
           "lead": {"claim": "검토 절차는 생략할 수 없다", "conceded": None}, "peer": {"claim": "먼저 내고 보완", "conceded": None},
           "user": {"claim": "범위부터 확인", "conceded": None}}
    led = dialogue.apply_update(led, upd, hist)
    assert led["upto_idx"] == 2 and len(led["summary"]) <= dialogue.SUMMARY_MAX + 1, "summary is compacted to a bounded size"
    assert led["issues"] == [{"id": "i1", "title": "검토가 필요한 범위", "status": "open", "raised_by": "user", "last_idx": 2}]
    assert led["commitments"][0] == {"who": "user", "what": "검토팀에 필수 항목 검토 요청 보내기", "due": "오늘 3시까지", "idx": 1}
    assert led["positions"]["lead"]["claim"] == "검토 절차는 생략할 수 없다"
    hist += [{"idx": 3, "speaker": "user", "text": "필수 항목만 먼저 받고, 요청은 제가 오늘 4시까지 보낼게요."},
             {"idx": 4, "speaker": "lead", "text": "그럼 필수 항목만 먼저 받죠. 고객사에는 제가 말씀드리겠습니다."}]
    assert [m["idx"] for m in dialogue.pending(led, hist)] == [3, 4], "only what the ledger has not folded in yet"
    upd2 = {"summary": "요약", "issues": [{"title": "i1", "status": "agreed", "raised_by": "lead"}, {"title": "i9", "status": "open", "raised_by": "lead"},
                                       {"title": "고객사 일정 공유", "status": "open", "raised_by": "peer"}],
            "new_commitments": [{"who": "user", "what": "검토팀에 필수 항목 검토 요청 보내기", "due": "오늘 4시까지", "idx": 99},
                                {"who": "lead", "what": "고객사에 알리기", "due": None, "idx": 4}],
            "lead": {"claim": None, "conceded": "필수 항목 먼저 검토는 받아들임"}, "peer": {"claim": "지원자 안에 찬성", "conceded": None},
            "user": {"claim": None, "conceded": None}}
    led = dialogue.apply_update(led, upd2, hist[3:])
    assert [(i["id"], i["title"], i["status"]) for i in led["issues"]] == [("i1", "검토가 필요한 범위", "agreed"), ("i2", "고객사 일정 공유", "open")], \
        "issue ids are stable; an id used as a title maps back, an unknown id is dropped"
    assert [(c["who"], c["due"], c["idx"]) for c in led["commitments"]] == [("user", "오늘 4시까지", 3)], \
        "a duplicate updates the due; '말씀드리겠습니다' is not a lead commitment"
    assert led["positions"]["lead"] == {"claim": "검토 절차는 생략할 수 없다", "conceded": "필수 항목 먼저 검토는 받아들임"}
    assert led["positions"]["peer"]["claim"] == "먼저 내고 보완", "the peer did not speak in this batch, so its position stays"
    again = dialogue.load({"dialogue": json.dumps(led, ensure_ascii=False)})
    assert again == led and CONTRACT_KEYS <= set(again)


def test_ledger_drops_null_strings_from_the_model():
    pend = [{"idx": 1, "speaker": "user", "text": "제가 정리할게요."}]
    upd = {"summary": "null", "issues": [{"title": "null", "status": "open", "raised_by": "user"}],
           "new_commitments": [{"who": "user", "what": "범위 정리", "due": "null", "idx": 1}],
           "lead": {"claim": "null", "conceded": "None"}, "peer": {"claim": None, "conceded": None}, "user": {"claim": "범위부터", "conceded": "null"}}
    led = dialogue.apply_update(dialogue.new_ledger(), upd, pend)
    assert led["summary"] == "" and led["issues"] == [] and led["commitments"] == [{"who": "user", "what": "범위 정리", "due": None, "idx": 1}]
    assert led["positions"]["lead"] == {"claim": None, "conceded": None} and led["positions"]["user"]["claim"] == "범위부터"


def test_ledger_fallback_compacts_by_rules_and_finds_candidate_commitments():
    pend = [{"idx": 4, "speaker": "lead", "text": "그럼 범위부터 정해요."},
            {"idx": 5, "speaker": "user", "text": "요청은 제가 오늘 3시까지 보내고, 통과 범위는 목요일에 확정할게요."}]
    led = dialogue.fallback_update({**dialogue.new_ledger(), "summary": "앞부분"}, pend, {"user": "지우", "lead": "한서윤"})
    assert led["summary"].startswith("앞부분 / [한서윤] 그럼 범위부터") and led["upto_idx"] == 5
    assert led["commitments"][0]["who"] == "user" and led["commitments"][0]["due"] == "오늘 3시까지" and led["commitments"][0]["idx"] == 5


def test_rule_update_counts_turns_and_citations():
    msgs = [{"idx": 3, "speaker": "peer", "text": "개인정보·보안 검토 규정 3조에 따르면 필수 항목만 먼저 볼 수 있어요.",
             "sources": [{"doc": "개인정보·보안 검토 규정", "section": "3조 부분 검토"}]},
            {"idx": 4, "speaker": "lead", "text": "4조는 개인정보가 없는 기능만이에요.", "sources": [{"doc": "개인정보·보안 검토 규정", "section": "4조 조건부 출시"}]}]
    plan = [{"persona": "peer", "move": "propose", "issue": "범위"}, {"persona": "lead", "move": "challenge", "issue": "범위"}]
    led = dialogue.rule_update(dialogue.new_ledger(), msgs, plan=plan)
    assert led["turns"]["peer"] == {"last_idx": 3, "count": 1} and led["turns"]["lead"] == {"last_idx": 4, "count": 1}
    assert led["cited"] == ["개인정보·보안 검토 규정 §3", "개인정보·보안 검토 규정 §4"]
    assert [m["move"] for m in led["last_moves"]] == ["propose", "challenge"]


# ---------- speaker policy ----------
MODES = {"lead": "avoiding", "peer": "collaborating"}


def test_addressed_detection():
    assert dialogue.addressed("도현님 말씀처럼 지난번엔 문제가 없었지만, 서윤님은 어떻게 보세요?", SCN) == ["lead", "peer"]
    assert dialogue.addressed("도현님, 서윤님이 걱정하시는 건 계좌 정보예요.", SCN)[0] == "peer", "a leading vocative wins"
    assert dialogue.addressed("팀장님 이건 어떻게 할까요?", SCN) == ["lead"]
    assert dialogue.addressed("두 분 의견을 같이 놓고 비교해 볼게요.", SCN) == []


def test_policy_addressed_first_and_avoiding_only_when_addressed():
    led = dialogue.new_ledger()
    director = [{"persona": "lead", "move": "answer"}, {"persona": "peer", "move": "build_on"}]
    items = dialogue.select(director, scn=SCN, modes=MODES, user_text="두 분 의견을 같이 놓고 일정과 위험을 비교해 볼게요.", ledger=led)
    assert [i["persona"] for i in items] == ["peer"], "the avoiding lead stays out when nobody calls her by name"
    items = dialogue.select([{"persona": "peer", "move": "propose"}], scn=SCN, modes=MODES, user_text="서윤님은 이 일정에서 뭐가 제일 걱정되세요?", ledger=led)
    assert [i["persona"] for i in items] == ["lead", "peer"], "addressed persona answers first even if the director skipped her"
    assert items[0]["target"] == "user" and items[1]["target"] == "lead"
    items = dialogue.select(director[::-1], scn=SCN, modes=MODES, user_text="서윤님, 도현님 안은 어떻게 보세요?", ledger=led, tension=True)
    assert [i["persona"] for i in items] == ["lead", "peer"]
    assert items[1]["target"] == "lead" and items[1]["move"] == "challenge", "cross-talk: the second speaker answers the first"


def test_policy_line_budget_balance_and_accommodating_cross_talk():
    modes = {"lead": "competing", "peer": "accommodating"}
    led = dialogue.new_ledger()
    two = [{"persona": "peer", "move": "answer"}, {"persona": "lead", "move": "answer"}]
    one = dialogue.select(two, scn=SCN, modes=modes, user_text="일정 위험을 정리해 볼게요.", ledger=led, max_lines=1, next_speaker="peer")
    assert [i["persona"] for i in one] == ["lead"], "with a beat coming, one reactive line and not from the beat speaker"
    both = dialogue.select(two[::-1], scn=SCN, modes=modes, user_text="일정 위험을 정리해 볼게요.", ledger=led, tension=True)
    assert both[1]["persona"] == "peer" and both[1]["move"] == "concede" and both[1]["target"] == "lead"
    busy = {**led, "turns": {"lead": {"last_idx": 9, "count": 6}, "peer": {"last_idx": 4, "count": 2}}}
    bal = dialogue.select([{"persona": "lead", "move": "answer"}], scn=SCN, modes=modes, user_text="어떻게 할까요?", ledger=busy)
    assert [i["persona"] for i in bal] == ["peer"], "balance: the quiet persona gets the floor"
    named = dialogue.select([{"persona": "lead", "move": "answer"}], scn=SCN, modes=modes, user_text="서윤님 어떻게 할까요?", ledger=busy)
    assert named[0]["persona"] == "lead", "but never against an explicit address"


def test_new_markup_goes_to_the_artifact_owner():
    sess = session(artifacts=[{"id": "a1", "kind": "code", "title": "정산 알림 발송", "owner": "peer", "status": "검토 중", "summary": "", "lang": "python",
                               "body": "def notify(u):\n    log.info(u.account_no)\n    send(u)"}],
                   annotations=[{"id": 12, "artifact_id": "a1", "anchor": {"line_start": 2, "line_end": 2, "quote": None}, "kind": "risk",
                                 "text": "계좌번호를 로그에 남기면 검토 대상 아닌가요?", "msg_idx": 1, "created_at": 0.0}])
    led = dialogue.load(sess)
    marks = dialogue.new_markups(sess, led)
    items = dialogue.select([{"persona": "lead", "move": "answer"}], scn=SCN, modes={"lead": "competing", "peer": "collaborating"},
                            user_text="코드에 표시 하나 남겼어요.", ledger=led, session=sess, marks=marks)
    holder = next(i for i in items if i["markup_id"])
    assert holder["persona"] == "peer" and holder["move"] == "address_markup" and holder["markup_id"] == "12"
    card = dialogue.move_values(holder, {"user": "지우", "lead": "한서윤", "peer": "이도현"}, session=sess, marks=marks)
    assert "#12" in card["extra"] and "L2:     log.info(u.account_no)" in card["extra"], "the card quotes the marked line"
    assert dialogue.new_markups(sess, dialogue.mark_seen(led, marks)) == []
    beat_next = dialogue.select([{"persona": "lead", "move": "answer"}], scn=SCN, modes={"lead": "competing", "peer": "collaborating"},
                                user_text="코드에 표시 하나 남겼어요.", ledger=led, session=sess, marks=marks, max_lines=1, next_speaker="peer")
    assert [(i["persona"], i["move"]) for i in beat_next] == [("lead", "address_markup")], "the owner speaks the beat next, so the other one answers"


def test_markup_turn_through_the_graph_then_marked_seen():
    sess = session(condition={"lead": "competing", "peer": "collaborating"},
                   artifacts=[{"id": "a2", "kind": "result", "title": "검토 일정표", "owner": "lead", "status": "초안", "summary": "", "lang": None,
                               "body": "| 항목 | 일정 |\n|---|---|\n| 부분 검토 | 3일 |"}],
                   annotations=[{"id": 7, "artifact_id": "a2", "anchor": {"line_start": 3, "line_end": 3, "quote": None}, "kind": "question",
                                 "text": "3일은 영업일 기준인가요?", "msg_idx": 1, "created_at": 0.0}])
    final = asyncio.run(run_turn(sess, "일정표에 질문 하나 남겼어요."))
    assert any(i["move"] == "address_markup" and i["persona"] == "lead" for i in final["plan"])
    assert any("#7" in m["text"] for m in final["new_messages"]) and final["dialogue"]["markups_seen"] == ["7"]
    final2 = asyncio.run(run_turn(apply(sess, "일정표에 질문 하나 남겼어요.", final), "네, 그럼 다음으로 넘어가요."))
    assert not any(i["move"] == "address_markup" for i in final2["plan"]), "an answered markup is not answered again"


def test_two_new_markups_cited_one_first_the_other_carried_over():
    arts = [{"id": "a1", "kind": "design", "title": "정산 예정일 미리보기 기획", "owner": "lead", "status": "초안", "summary": "", "lang": None,
             "body": "\n".join(f"line {n}" for n in range(1, 16))},
            {"id": "a3", "kind": "code", "title": "트래킹 명세", "owner": "peer", "status": "검토 중", "summary": "", "lang": "yaml",
             "body": "\n".join(f"row {n}" for n in range(1, 16))}]
    marks_in = [{"id": 1, "artifact_id": "a3", "anchor": {"line_start": 13, "line_end": 13, "quote": None}, "kind": "risk",
                 "text": "requires에 검토 게이트가 없어요.", "msg_idx": 1, "created_at": 0.0},
                {"id": 2, "artifact_id": "a1", "anchor": {"line_start": 4, "line_end": 4, "quote": None}, "kind": "question",
                 "text": "누가 정하나요?", "msg_idx": 1, "created_at": 0.0}]
    sess = session(artifacts=arts, annotations=marks_in, condition={"lead": "avoiding", "peer": "collaborating"})
    led = dialogue.load(sess)
    marks = dialogue.new_markups(sess, led)
    text = "[트래킹 명세 L13-14] 여기 한번 봐 주세요."
    assert dialogue.pick_markup(marks, text, sess)["id"] == 1, "the cited markup, not the newest"
    assert dialogue.pick_markup(marks, "", sess)["id"] == 2, "nothing cited: the newest asking one"
    items = dialogue.select([{"persona": "peer", "move": "answer", "markup_id": "2"}], scn=SCN, modes={"lead": "avoiding", "peer": "collaborating"},
                            user_text=text, ledger=led, session=sess, marks=marks)
    assert [(i["persona"], i["markup_id"]) for i in items] == [("peer", "1")], "citation beats the director's pick; the avoiding owner of a1 stays quiet"
    led2 = dialogue.mark_seen(led, marks, dialogue.answered_markups(items))
    assert led2["markups_seen"] == ["1"] and [a["id"] for a in dialogue.new_markups(sess, led2)] == [2], "the unanswered markup carries over"
    both = dialogue.select([{"persona": "peer", "move": "answer"}, {"persona": "lead", "move": "answer"}], scn=SCN,
                           modes={"lead": "competing", "peer": "collaborating"}, user_text=text, ledger=led, session=sess, marks=marks)
    assert {i["markup_id"] for i in both} == {"1", "2"}, "the second speaker owns the other markup and answers it"


def test_stale_issue_is_parked_and_touched_issue_kept_open():
    led = {**dialogue.new_ledger(), "issues": [{"id": "i1", "title": "베타 범위", "status": "open", "raised_by": "user", "last_idx": 1},
                                               {"id": "i2", "title": "계좌 끝자리 트래킹", "status": "open", "raised_by": "lead", "last_idx": 1}]}
    pend = [{"idx": 14, "speaker": "user", "text": "베타 범위는 40곳으로 가요."}]
    upd = {"summary": "", "issues": [{"title": "베타 범위", "status": "open"}, {"title": "계좌 끝자리 트래킹", "status": "open"}], "new_commitments": []}
    out = {i["id"]: i for i in dialogue.apply_update(led, upd, pend)["issues"]}
    assert out["i1"]["status"] == "open" and out["i1"]["last_idx"] == 14
    assert out["i2"]["status"] == "parked", "untouched for 12+ messages"


def test_commitment_due_follows_its_text_and_rewordings_merge():
    led = dialogue.new_ledger()
    dialogue._add_commitment(led, "user", "통과 범위는 목요일에 확정", "오늘 3시", 5)
    assert led["commitments"][0]["due"] == "목요일"
    dialogue._add_commitment(led, "user", "통과 범위를 목요일까지 확정할게요", None, 9)
    assert len(led["commitments"]) == 1


def test_guard_flags_a_reworded_stance():
    led = {**dialogue.new_ledger(), "positions": {"lead": {"claim": "검토를 통과한 범위만 출시할 수 있다", "conceded": None}}}
    v = dialogue.check("결국 검토를 통과한 범위만 출시할 수 있어요.", "lead", history=[], ledger=led)
    assert any(x["rule"] == "restate_claim" for x in v)
    assert not dialogue.check("베타 40곳은 목요일 오전에 다시 볼게요.", "lead", history=[], ledger=led)


def test_named_question_is_answered_and_metric_talk_gets_a_formula():
    items = dialogue.select([{"persona": "lead", "move": "challenge"}], scn=SCN, modes={"lead": "competing", "peer": "collaborating"},
                            user_text="서윤님, 재참여율은 어떻게 계산하나요?", ledger=dialogue.new_ledger())
    assert items[0]["persona"] == "lead" and items[0]["move"] == "answer" and items[0]["form"] == "formula"


def test_informal_address_counts_and_a_third_person_mention_does_not_wake_an_avoider():
    assert dialogue.addressed("서윤이는 어떻게 생각해?", SCN) == ["lead"] and dialogue.addressed("도현아, 이거 봐줘", SCN, 2) == ["peer"]
    items = dialogue.select([{"persona": "peer", "move": "answer"}], scn=SCN, modes={"lead": "avoiding", "peer": "collaborating"},
                            user_text="한서윤 팀장님이 말씀하신 대로 할게요.", ledger=dialogue.new_ledger())
    assert [i["persona"] for i in items] == ["peer"]


# ---------- repetition / echo guard ----------
def _baseline_lines() -> list[tuple[str, str]]:
    out = []
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s+\[(lead|peer)[^\]]*\] (.*?)(  ⟨근거.*)?$", line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def test_guard_flags_the_baseline_failures():
    lines = _baseline_lines()
    hist = [{"idx": n, "speaker": sp, "text": t, "sources": [{"doc": "개인정보·보안 검토 규정", "section": "3조 부분 검토"}]} for n, (sp, t) in enumerate(lines)]
    led = dialogue.new_ledger()
    rules = lambda n, mode="collaborating": {v["rule"] for v in dialogue.check(lines[n][1], lines[n][0], history=hist[:n], ledger=led, mode=mode,
                                                                                 docs=["개인정보·보안 검토 규정"])}
    assert {"echo", "sycophancy"} <= rules(7), "'도현님 말씀에 동의합니다' + copying the other persona"
    assert "re_cite" in rules(4) and "self_repeat" in rules(5), "§3 again, and the same line again"
    assert "sycophancy" in rules(11) and "sycophancy" in rules(18, "accommodating"), "'매우 긍정적', '매우 체계적' are flagged for every mode"
    assert "echo" in rules(14) and "same_opener" in rules(19)
    assert "re_quote" in rules(16) and "re_quote" in rules(18), "'영업일 기준 3일 안에 결과를' restated without a clause number"
    assert "re_quote" not in rules(10) and "re_quote" not in rules(20)
    flagged = sum(bool(dialogue.check(t, sp, history=hist[:n], ledger=led, docs=["개인정보·보안 검토 규정"])) for n, (sp, t) in enumerate(lines))
    assert flagged >= len(lines) // 2, "most of the baseline persona lines break at least one rule"


def test_guard_passes_fresh_lines_and_allows_asked_clauses():
    hist = [{"idx": 1, "speaker": "peer", "text": "개인정보·보안 검토 규정 3조에 따르면 필수 항목만 먼저 볼 수 있어요.", "sources": []}]
    led = dialogue.new_ledger()
    fresh = "필수 항목 목록은 제가 오늘 오후까지 정리할게요. 고객사에는 금요일 범위를 먼저 알려야 해요."
    assert dialogue.check(fresh, "lead", history=hist, ledger=led) == []
    again = "3조로 가면 통과한 범위만 낼 수 있어요."
    src = [{"doc": "개인정보·보안 검토 규정", "section": "3조 부분 검토"}]
    assert dialogue.check(again, "lead", history=hist, ledger=led, sources=src)[0] == {"rule": "re_cite", "keys": ["개인정보·보안 검토 규정 §3"]}
    assert dialogue.check(again, "lead", history=hist, ledger=led, sources=src, user_text="3조가 정확히 뭐예요?") == [], "the candidate asked for it"
    assert dialogue.sycophancy("도현님 말씀에 동의합니다. 그렇게 하죠.", "accommodating") is None, "agreeing is the accommodating mode's job"
    fb = dialogue.feedback([{"rule": "echo", "score": 0.4}, {"rule": "re_cite", "keys": ["X §3"]}], {"lead": "한서윤", "peer": "이도현"}, "lead")
    assert "이도현의 직전 말" in fb and "X 3조" in fb and "§" not in fb and fb.endswith("대사만 출력:")
    assert dialogue.citations("규정 §3에 따르면 됩니다", [], ["규정"]) == ["규정 §3"], "the ledger's own notation is caught too"
    assert dialogue.check("3조대로면 금요일엔 일부만 나가요.", "peer", history=hist, ledger=led)[0]["rule"] == "re_cite", "a bare clause number matches too"


def test_mock_rewrites_a_repeated_line_and_traces_it():
    base = session(condition={"lead": "competing", "peer": "accommodating"})
    said = MockLLM.LINES["accommodating"][0]  # the pool would hand the peer this line again (len(history) % 2 == 0)
    sess = {**base, "messages": [*base["messages"], {"idx": 1, "speaker": "user", "text": "일정부터 볼게요."},
                                 {"idx": 2, "speaker": "peer", "text": said, "sources": []}]}
    ctx = task_ctx()
    final = asyncio.run(run_turn(sess, "일정은 어떻게 할까요?", ctx=ctx))
    line = final["new_messages"][0]
    assert line["speaker"] == "peer" and line["text"] != said and line["text"].startswith(MockLLM.REWRITE["answer"])
    assert ctx.tracer.notes["repetition_guard"] == 1 and ctx.tracer.notes["repetition_guard.self_repeat"] == 1
    assert "dialogue_move" in ctx.tracer.prompts and "directive_react" not in ctx.tracer.prompts


# ---------- graph wiring, flag, limits ----------
def test_flag_off_is_the_legacy_path(monkeypatch):
    monkeypatch.setenv("DIALOGUE_HARNESS", "0")
    ctx = task_ctx()
    final = asyncio.run(run_turn(session(), "두 분 의견을 같이 놓고 일정과 위험을 비교해 볼게요.", ctx=ctx))
    assert final["plan"] == [{"persona": "peer", "intent": "지원자 발화에 답한다"}, {"persona": "lead", "intent": "자기 입장에서 의견을 보탠다"}]
    assert [(m["speaker"], m["text"]) for m in final["new_messages"]] == [("peer", MockLLM.LINES["collaborating"][0]), ("lead", MockLLM.LINES["avoiding"][1])]
    assert "dialogue" not in final, "nothing to persist: Spring keeps dialogue_json as it was"
    assert {"directive_react", "directive_react_second"} <= set(ctx.tracer.prompts) and not any("dialogue" in p for p in ctx.tracer.prompts)

    monkeypatch.setenv("DIALOGUE_HARNESS", "1")
    final = asyncio.run(run_turn(session(), "두 분 의견을 같이 놓고 일정과 위험을 비교해 볼게요."))
    assert [m["speaker"] for m in final["new_messages"]] == ["peer"], "same input, harness on: the avoiding lead is not dragged in"
    assert CONTRACT_KEYS <= set(final["dialogue"]) and final["dialogue"]["turns"]["peer"]["count"] == 1


def test_openai_speak_picks_the_path_by_flag(monkeypatch):
    llm = llm_mod.OpenAILLM()
    calls = []

    async def legacy(*a, **k):
        calls.append("legacy")
        return {"text": "", "sources": []}

    async def harness(*a, **k):
        calls.append("dialogue")
        return {"text": "", "sources": []}

    monkeypatch.setattr(llm, "_speak_legacy", legacy)
    monkeypatch.setattr(llm, "_speak_dialogue", harness)
    for flag in ("0", "1"):
        monkeypatch.setenv("DIALOGUE_HARNESS", flag)
        asyncio.run(llm.speak(SCN, "lead", [], {"user": "지우"}, "BEAT: x"))
    assert calls == ["legacy", "dialogue"]


def test_failures_in_ledger_and_director_never_break_a_turn():
    class Flaky(MockLLM):
        async def update_ledger(self, *a, **k):
            raise RuntimeError("ledger model down")

        async def direct(self, *a, **k):
            raise RuntimeError("director model down")

    ctx = task_ctx()
    final = asyncio.run(run_turn(session(), "요청은 제가 오늘 3시까지 보낼게요.", llm=Flaky(), ctx=ctx))
    assert final["new_messages"] and final["new_messages"][0]["speaker"] == "peer", "fallback speaker (not the avoiding beat speaker)"
    assert final["dialogue"]["commitments"][0]["due"] == "오늘 3시까지" and final["dialogue"]["upto_idx"] == 1
    assert ctx.tracer.notes["ledger_failed"] == 1 and ctx.tracer.notes["director_failed"] == 1


def test_harness_stays_within_loop_limits():
    lim = Limits()
    worst = 3 + 2 * (llm_mod.MAX_TOOL_ROUNDS + 1 + 1)  # director + observer + ledger; 2 persona lines x (tool rounds + answer + rewrite)
    assert worst <= lim.max_model_calls
    sess = session(condition={"lead": "competing", "peer": "collaborating"}, turns_in_milestone=1)
    final = asyncio.run(run_turn(sess, "서윤님, 도현님 두 안을 같이 비교해서 정리해 볼게요."))  # 'next': react + beat inside the step limit
    assert final["decision"] == "next" and len(final["new_messages"]) == 2, "one reactive line + the beat: still ≤ 2 persona lines"
    assert final["new_messages"][1]["milestone"] == "coordinate"
