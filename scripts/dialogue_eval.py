"""Before/after evaluation of the dialogue harness (item 6) with the real model, in-process (no compose stack).

  cd agent && uv run --python 3.12 --env-file ../.env python ../scripts/dialogue_eval.py [--reps 2] [--smoke]

Same scripted candidate lines through the turn graph (app.graph) with DIALOGUE_HARNESS=0 (previous flow) and =1:
  scripts   base     the 8 lines of scripts/e2e.py (full 소통→조율→타협→설득 arc + closing)
            markup   e2e line 2 unchanged, but the candidate has left a risk markup on the shared code artifact
            avoid    e2e line 2 rewritten to address the avoiding persona by name
            (line 1 is played once per condition/rep and the three scripts branch from that state: a paired design)
  conditions A = lead avoiding / peer collaborating (the baseline run), B = lead competing / peer avoiding
Sessions are built here (scenario dl.pm.fintech, fixed opening line taken from docs/eval/baseline_e2e_transcript.txt).
rag-mcp runs in-process on a temporary index; business-mcp is replaced by a stub that serves get_artifact only.
The observer is skipped in both arms (it does not influence persona lines) to keep spend small.
Writes docs/eval/dialogue_harness.json (every turn + aggregated metrics) and prints the metric table.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent"
_tmp = tempfile.mkdtemp(prefix="dialogue_eval_")
# Isolation: empty values win over ../.env (load_dotenv never overrides), so nothing touches compose databases.
for k in ("VECTOR_DB_URL", "DATABASE_URL", "RABBIT_URL"):
    os.environ[k] = ""
os.environ["RAG_LOCAL_INDEX"] = os.path.join(_tmp, "rag_index.json")
os.environ.pop("MOCK_LLM", None)
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
sys.path.insert(0, str(AGENT))

from fastmcp import FastMCP  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

FIXED_OPENING = ("금요일 마감은 변함없이 유지되는데, '개인정보·보안 검토'가 다음 주 화요일로 밀렸습니다. 개인정보를 새로 수집하거나 다른 곳에 보내는 기능은 "
                 "출시 전에 검토를 받아야 하니, 현재 준비 상황과 이로 인한 영향 범위를 정리해 주시면 좋겠습니다.")
E2E = [  # scripts/e2e.py, with the person each line calls by name (ground truth for addressed-first)
    ("기획안은 90% 됐고 고객사 약속은 금요일이에요. 검토가 꼭 필요한 범위가 어디까지인지 서윤님께 먼저 확인하고 싶어요.", None, "lead"),
    ("검토팀 일정이 왜 밀렸는지, 부분 검토가 가능한지도 오늘 알아볼게요.", None, None),
    ("도현님 말씀처럼 지난번엔 문제가 없었지만, 이번엔 계좌 정보가 들어가서 조심스러워요. 도현님은 어떻게 보세요?", None, "peer"),
    ("두 분 의견을 같이 놓고 일정과 위험을 비교해 볼게요.", None, None),
    ("필수 항목만 먼저 검토받으면 고객 약속도 일부 지키고 위험도 줄일 수 있어요. 검토팀엔 제가 오늘 요청할게요.", "both", None),
    ("부분 출시 범위는 오늘 오후까지 정리해서 공유할게요.", None, None),
    ("요청은 제가 오늘 3시까지 보내고, 통과 범위는 목요일에 확정할게요. 우려하신 지연은 화요일 전체 검토로 보완할게요.", None, None),
    ("정리하면 오늘 검토 요청, 금요일 부분 출시, 다음 주 나머지 출시예요.", None, None),
]
ARTIFACTS = [
    {"id": "a1", "kind": "design", "title": "정산 알림 출시 범위", "owner": "lead", "status": "검토 중", "summary": "금요일 출시 범위와 검토 대상 구분", "lang": None,
     "body": "## 금요일 출시 범위\n- 정산 완료 알림(푸시)\n- 알림 본문: 가맹점명, 입금액, **계좌번호 뒤 4자리**\n- 알림 설정 화면\n\n## 검토 대상\n- 계좌 정보 표시 → 개인정보·보안 검토 필요\n- 설정 화면 → 검토 불필요"},
    {"id": "a2", "kind": "result", "title": "검토 일정 비교", "owner": "lead", "status": "초안", "summary": "전체 검토와 부분 검토의 일정 비교", "lang": None,
     "body": "| 안 | 검토 요청 | 결과 | 출시 |\n|---|---|---|---|\n| 전체 검토 | 화 | 금(+3일) | 다음 주 |\n| 부분 검토 | 오늘 | 목 | 금 |\n\n부분 검토 성공 확률 $p \\approx 0.9$ (지난 분기 기준)"},
    {"id": "a3", "kind": "code", "title": "정산 알림 발송 코드", "owner": "peer", "status": "리뷰 대기", "summary": "알림 본문 생성과 발송", "lang": "python",
     "body": "def build_message(s):\n    body = f\"{s.store} 정산 {s.amount:,}원\"\n    body += f\" 입금 계좌 {s.account_no}\"\n    log.info(\"notify %s\", body)\n    return body\n\n\ndef notify(s):\n    push.send(s.owner_id, build_message(s))"},
]
MARKUPS = {  # before e2e line n (1-based): the candidate marks up an artifact
    2: {"artifact_id": "a3", "anchor": {"line_start": 3, "line_end": 4, "quote": None}, "kind": "risk", "text": "계좌번호 전체가 알림 본문과 로그에 그대로 들어가요. 뒤 4자리만 써야 하지 않나요?"},
}
CONDITIONS = {"A": {"lead": "avoiding", "peer": "collaborating"}, "B": {"lead": "competing", "peer": "avoiding"}}
SYCO_EVAL = re.compile(r"매우\s?(긍정적|좋|훌륭|체계적)|긍정적으로\s?생각|좋은\s?(생각|계획|제안|의견|방법|접근)|훌륭|체계적|잘\s?수립|잘\s?정리|"
                       r"말씀에\s?(동의|공감)|의견에\s?(동의|공감)|동의합니다|공감합니다|공감하는|잘\s?듣고\s?있|맞는\s?말씀|말씀\s?잘\s?들었")
MD = re.compile(r"^\s*[-*]\s|^\s*\d+\.\s|^\s*\|.*\|\s*$|\*\*[^*]+\*\*|\$[^$\n]+\$", re.M)

_sessions: dict[str, dict] = {}
stub = FastMCP("business-eval", instructions="eval stub: get_artifact only")


@stub.tool
def get_artifact(session_id: str, artifact_id: str) -> dict:
    """[조회] 과제 하나 + 마크업."""
    s = _sessions.get(session_id)
    art = next((a for a in (s or {}).get("artifacts") or [] if a["id"] == artifact_id), None)
    if art is None:
        raise ToolError(f"404 과제를 찾을 수 없어요: {artifact_id}")
    return {**art, "annotations": [n for n in s["annotations"] if n["artifact_id"] == artifact_id]}


def script(variant: str, avoid_pid: str, names: dict) -> list[dict]:
    """Rows after the shared first line. base = e2e lines 2-8; markup = e2e line 2 unchanged + a markup the chat never
    mentions (so base vs markup differ only by the markup); avoid = line 2 addressed to the avoiding persona by name."""
    rows = []
    for n, (text, choice, to) in enumerate(E2E, 1):
        if n == 1 or (variant != "base" and n != 2):
            continue
        row = {"n": n, "text": text, "choice": choice, "addressed": to, "markup": MARKUPS[n] if variant == "markup" else None}
        if variant == "avoid":
            row["text"], row["addressed"] = f"{names[avoid_pid][1:]}님은 검토 일정이 밀린 게 우리 출시에 어떤 영향이 있다고 보세요?", avoid_pid
        rows.append(row)
    return rows


def new_session(cond: str, rep: int) -> dict:
    sid = uuid.uuid4().hex[:12]
    sess = {"id": sid, "alias": "지우", "company": "데모", "scenario_id": "dl.pm.fintech", "status": "active", "milestone_idx": 0, "turns_in_milestone": 0,
            "condition": {"stratum": "V2", **CONDITIONS[cond], "method": "fixed", "seed": rep}, "choice": None, "milestone_log": [], "notes": "",
            "report_status": "none", "messages": [{"idx": 0, "speaker": "lead", "text": FIXED_OPENING, "sources": [], "milestone": "communicate", "ts": time.time()}],
            "artifacts": [dict(a) for a in ARTIFACTS], "annotations": [], "dialogue": None}  # START seeds artifacts in every session
    _sessions[sid] = sess
    return sess


def fork(sess: dict) -> dict:
    out = copy.deepcopy(sess)
    out["id"] = uuid.uuid4().hex[:12]
    _sessions[out["id"]] = out
    return out


async def play(sess: dict, rows: list[dict], budget: dict) -> list[dict]:
    """Candidate lines through the turn graph, applying each result to the session like runner._turn + Spring do."""
    from app.graph import build_graph
    from app.harness.events import EventPublisher, MemorySink
    from app.harness.loop import Limits
    from app.harness.observability import Tracer
    from app.harness.runtime import TaskContext, bind, unbind
    from app.scenarios import MILESTONE_KEYS

    graph, turns = build_graph(), []
    for row in rows:
        if budget["tokens"] > budget["max"] or sess["status"] != "active":
            break
        user_idx = len(sess["messages"])
        new_marks = []
        if row["markup"]:
            note = {"id": 100 + row["n"], **row["markup"], "msg_idx": user_idx, "created_at": time.time()}
            sess["annotations"].append(note)
            new_marks.append(note)
        if row["choice"]:
            sess["choice"] = {"option": row["choice"], "pole": row["choice"], "msg_idx": user_idx, "ts": time.time()}
        sink = MemorySink()
        tid = f"eval:{sess['id']}:{row['n']}"
        ctx = TaskContext(tid, sess["id"], 1, EventPublisher(tid, sink), Tracer(tid))
        token = bind(ctx)
        state = {"session": {**sess, "messages": list(sess["messages"])}, "user_text": row["text"], "user_idx": user_idx,
                 "milestone_idx": sess["milestone_idx"], "observations": [], "new_messages": []}
        cfg = {"configurable": {"llm": EVAL_LLM, "thread_id": tid}, "recursion_limit": Limits().max_graph_steps}
        err = None
        try:
            final = await asyncio.wait_for(graph.ainvoke(state, config=cfg), timeout=180)
        except Exception as e:  # recorded; the session stops here
            err, final = f"{type(e).__name__}: {str(e)[:200]}", None
        finally:
            await ctx.events.close()
            unbind(token)
        tr = ctx.tracer.summary()
        budget["tokens"] += (tr["tokens_in"] or 0) + (tr["tokens_out"] or 0)
        rec = {"n": row["n"], "user": row["text"], "addressed": row["addressed"], "markups": new_marks, "error": err,
               "llm_calls": tr["llm_calls"], "tokens_in": tr["tokens_in"], "tokens_out": tr["tokens_out"], "notes": dict(ctx.tracer.notes),
               "tools": [e["data"].get("tool") for _, e in sink.events if e["type"] == "TOOL_START"], "plan": [], "decision": None, "lines": []}
        turns.append(rec)
        if final is None:
            break
        react_n = len(final["new_messages"]) - (0 if final["decision"] == "stay" else 1)
        rec.update(plan=final.get("plan") or [], decision=final["decision"],
                   lines=[{"idx": m["idx"], "speaker": m["speaker"], "text": m["text"], "sources": m.get("sources") or [],
                           "kind": "react" if k < react_n else ("closing" if final.get("completed") else "beat")}
                          for k, m in enumerate(final["new_messages"])])
        user = {"idx": user_idx, "speaker": "user", "text": row["text"], "milestone": MILESTONE_KEYS[sess["milestone_idx"]], "ts": time.time()}
        sess["messages"] += [user, *final["new_messages"]]
        sess["milestone_idx"], sess["turns_in_milestone"] = final["milestone_idx_after"], final["turns_after"]
        if final.get("dialogue") is not None:
            sess["dialogue"] = final["dialogue"]
        if final.get("completed"):
            sess["status"] = "completed"
    return turns


async def run_arm(flag: str, cond: str, rep: int, budget: dict, variants=("base", "markup", "avoid")) -> list[dict]:
    """One (flag, condition, rep): the shared first e2e line, then base / markup / avoid branch from the same state.
    Without 'base' the first turn is still played (it is the branches' prefix) but not scored."""
    from app.scenarios import get_scenario

    scn = get_scenario("dl.pm.fintech")
    names = {"user": "지우", **{p: scn["personas"][p]["name"] for p in ("lead", "peer")}}
    avoid_pid = next(p for p in ("lead", "peer") if CONDITIONS[cond][p] == "avoiding")
    sess = new_session(cond, rep)
    first = await play(sess, [{"n": 1, "text": E2E[0][0], "choice": None, "addressed": E2E[0][2], "markup": None}], budget)
    prefix = [ln for t in first for ln in t["lines"]]
    branches = [fork(sess) for _ in variants]
    played = await asyncio.gather(*(play(b, script(v, avoid_pid, names), budget) for b, v in zip(branches, variants)))
    out = []
    for v, b, turns in zip(variants, branches, played):
        out.append({"flag": flag, "cond": cond, "variant": v, "rep": rep, "condition": CONDITIONS[cond], "avoid": avoid_pid,
                    "prefix": [] if v == "base" else prefix, "turns": (first if v == "base" else []) + turns, "dialogue": b["dialogue"]})
    print(f"  done flag={flag} cond={cond} rep={rep}: turns {[len(r['turns']) for r in out]}, tokens so far {budget['tokens']:,}", flush=True)
    return out


# ---------- metrics ----------
def _given(names: dict, pid: str) -> str:
    return names[pid][1:]


def metrics(runs: list[dict]) -> dict:
    from app.harness import dialogue
    from app.scenarios import get_scenario

    scn = get_scenario("dl.pm.fintech")
    names = {p: scn["personas"][p]["name"] for p in ("lead", "peer")}
    self_s, echo_s, recite, requote, cite_any, syco, md, length, d2 = [], [], [], [], [], [], [], [], []
    first_ok, avoid_quiet, avoid_answer, cross, uptake, opened = [], [], [], [], [], []
    calls, toks, lines_per_turn, guard, errors = [], [], [], 0, 0
    for r in runs:
        docs = list(dict.fromkeys(s["doc"] for t in r["turns"] for ln in t["lines"] for s in ln["sources"] if s.get("doc")))
        hist: list[dict] = [{"speaker": "lead", "text": FIXED_OPENING, "sources": []}, *r.get("prefix", [])]
        seen_cites = {c for ln in r.get("prefix", []) for c in dialogue.citations(ln["text"], ln["sources"], docs)}
        bigrams: list[tuple[str, str]] = []
        for t in r["turns"]:
            errors += bool(t["error"])
            calls.append(t["llm_calls"])
            toks.append((t["tokens_in"] or 0) + (t["tokens_out"] or 0))
            guard += sum(v for k, v in (t["notes"] or {}).items() if k == "repetition_guard")
            react = [ln for ln in t["lines"] if ln["kind"] == "react"]
            lines_per_turn.append(len(t["lines"]))
            for ln in t["lines"]:
                pid, text = ln["speaker"], ln["text"]
                own = [h["text"] for h in hist if h["speaker"] == pid][-3:]
                other = [h["text"] for h in hist if h["speaker"] == dialogue.other(pid)][-1:]
                if own:
                    self_s.append(max(dialogue.similarity(text, o) for o in own))
                if other:
                    echo_s.append(dialogue.similarity(text, other[0]))
                requote.append(any(len(dialogue.shared_span(text, h["text"])) >= dialogue.QUOTE_SPAN for h in hist))
                cites = dialogue.citations(text, ln["sources"], docs)
                cite_any.append(bool(cites))
                recite.append(any(dialogue.cited_before(c, seen_cites) for c in cites))
                seen_cites.update(cites)
                syco.append(bool(SYCO_EVAL.search(text)))
                md.append(bool(MD.search(text)))
                length.append(len(text))
                toks_ = text.split()
                bigrams += list(zip(toks_, toks_[1:]))
                hist.append({"speaker": pid, "text": text, "sources": ln["sources"]})
            if t["addressed"] and react:
                first_ok.append(react[0]["speaker"] == t["addressed"])
            if t["lines"]:  # reactive lines only: beats are the scenario's fixed situations
                spoke = any(ln["speaker"] == r["avoid"] for ln in react)
                if t["addressed"] == r["avoid"]:
                    avoid_answer.append(spoke)
                else:
                    avoid_quiet.append(not spoke)
            if len(react) >= 2:
                a = react[0]["speaker"]
                call = rf"{_given(names, a)}\s?님" + (r"|팀장님" if a == "lead" else "")
                cross.append(bool(re.search(call, react[1]["text"])))
            if t["markups"]:
                hit = False
                for mk in t["markups"]:
                    art = next(x for x in ARTIFACTS if x["id"] == mk["artifact_id"])
                    body = art["body"].split("\n")
                    ls, le = mk["anchor"]["line_start"], mk["anchor"]["line_end"]
                    frag = [(dialogue._norm(body[i - 1]), 6) for i in range(ls, le + 1)] + [(dialogue._norm(mk["text"]), 8)]
                    for ln in react:  # names the place (#id, L3, 3번째 줄) or reuses the marked line / the markup's wording
                        tx, nt = ln["text"], dialogue._norm(ln["text"])
                        if f"#{mk['id']}" in tx or re.search(rf"L\s?{ls}(?!\d)|{ls}\s?(번째\s?)?(줄|행)|{ls}번\s?줄", tx) or \
                                any(len(f) >= w and any(f[i:i + w] in nt for i in range(len(f) - w + 1)) for f, w in frag):
                            hit = True
                uptake.append(hit)
                opened.append("business.get_artifact" in t["tools"])
        if len(bigrams):
            d2.append(len(set(bigrams)) / len(bigrams))
    mean = lambda xs: round(statistics.mean(xs), 3) if xs else None
    rate = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    return {
        "persona_lines": len(length), "turns": len(calls), "errors": errors,
        "self_repetition_mean": mean(self_s), "self_repetition_rate": rate([s >= dialogue.SELF_SIM for s in self_s]),
        "echo_mean": mean(echo_s), "echo_rate": rate([s >= dialogue.ECHO_SIM for s in echo_s]),
        "repeated_citation_rate": rate(recite), "re_quote_rate": rate(requote), "citing_line_rate": rate(cite_any),
        "sycophancy_rate": rate(syco),
        "addressed_first": rate(first_ok), "addressed_first_n": len(first_ok),
        "avoiding_quiet_when_unaddressed": rate(avoid_quiet), "avoiding_quiet_n": len(avoid_quiet),
        "avoiding_answers_when_addressed": rate(avoid_answer), "avoiding_answer_n": len(avoid_answer),
        "cross_talk_rate": rate(cross), "cross_talk_n": len(cross),
        "markup_uptake": rate(uptake), "markup_artifact_opened": rate(opened), "markup_n": len(uptake),
        "distinct_2": mean(d2), "mean_line_chars": mean(length), "markdown_line_rate": rate(md),
        "persona_lines_per_turn": mean(lines_per_turn), "llm_calls_per_turn": mean(calls), "tokens_per_turn": mean(toks),
        "repetition_guard_rewrites": guard,
    }


ROWS = [("persona_lines", "persona lines (n)"), ("self_repetition_mean", "self-repetition, mean max sim ↓"), ("self_repetition_rate", "self-repetition rate (≥0.30) ↓"),
        ("echo_mean", "cross-persona echo, mean sim ↓"), ("echo_rate", "echo rate (≥0.28) ↓"), ("repeated_citation_rate", "repeated-citation rate (same clause no.) ↓"),
        ("re_quote_rate", "re-quote rate (≥20-char span from an earlier line) ↓"),
        ("citing_line_rate", "lines citing a clause"), ("sycophancy_rate", "sycophancy-marker rate ↓"), ("addressed_first", "addressed-first compliance ↑"),
        ("avoiding_quiet_when_unaddressed", "avoiding persona quiet when unaddressed ↑"), ("avoiding_answers_when_addressed", "avoiding persona answers when addressed ↑"),
        ("cross_talk_rate", "cross-talk rate (2nd line names the 1st) ↑"), ("markup_uptake", "markup uptake ↑"), ("markup_artifact_opened", "artifact opened on markup turns"),
        ("distinct_2", "distinct-2 ↑"), ("mean_line_chars", "mean line length (chars)"), ("markdown_line_rate", "lines with Markdown/LaTeX"),
        ("persona_lines_per_turn", "persona lines per turn"), ("llm_calls_per_turn", "LLM calls per turn"), ("tokens_per_turn", "tokens per turn (in+out)"),
        ("repetition_guard_rewrites", "repetition-guard rewrites"), ("errors", "failed turns")]


def table(agg: dict) -> str:
    def n_of(key, arm):
        k = {"addressed_first": "addressed_first_n", "avoiding_quiet_when_unaddressed": "avoiding_quiet_n", "avoiding_answers_when_addressed": "avoiding_answer_n",
             "cross_talk_rate": "cross_talk_n", "markup_uptake": "markup_n", "markup_artifact_opened": "markup_n"}.get(key)
        return f" (n={agg[arm][k]})" if k else ""

    out = ["| metric | legacy (`DIALOGUE_HARNESS=0`) | harness (`=1`) |", "|---|---|---|"]
    for key, label in ROWS:
        out.append(f"| {label} | {agg['0'][key]}{n_of(key, '0')} | {agg['1'][key]}{n_of(key, '1')} |")
    return "\n".join(out)


async def main() -> None:
    global EVAL_LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--smoke", action="store_true", help="one harness session of 2 turns, to check wiring")
    ap.add_argument("--smoke-turns", type=int, default=8)
    ap.add_argument("--rescore", action="store_true", help="recompute metrics of an existing --out file (no model calls)")
    ap.add_argument("--supplement", help="COND:REP — add the markup/avoid arms of one condition/rep to an existing --out file")
    ap.add_argument("--max-tokens", type=int, default=900_000)
    ap.add_argument("--embeddings", choices=["openai", "local"], default="openai" if os.getenv("OPENAI_API_KEY") else "local")
    ap.add_argument("--out", default=str(ROOT / "docs" / "eval" / "dialogue_harness.json"))
    args = ap.parse_args()
    if not os.getenv("OPENAI_API_KEY") and not args.rescore:
        sys.exit("OPENAI_API_KEY is not set (run with --env-file ../.env)")
    os.environ["EMBEDDING_PROVIDER"] = args.embeddings
    if args.rescore:
        prev = json.loads(Path(args.out).read_text(encoding="utf-8"))
        runs = prev["runs"]
        prev["metrics"] = {f: metrics([x for x in runs if x["flag"] == f]) for f in ("0", "1")}
        prev["by_condition"] = {cc: {f: metrics([x for x in runs if x["flag"] == f and x["cond"] == cc]) for f in ("0", "1")} for cc in CONDITIONS}
        prev["by_variant"] = {v: {f: metrics([x for x in runs if x["flag"] == f and x["variant"] == v]) for f in ("0", "1")} for v in ("base", "markup", "avoid")}
        Path(args.out).write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
        print(table(prev["metrics"]))
        for c in CONDITIONS:
            print(f"\ncondition {c}\n" + table(prev["by_condition"][c]))
        for v in ("base", "markup", "avoid"):
            print(f"\nscript {v}\n" + table(prev["by_variant"][v]))
        return

    from app.harness import tools
    from app.llm import OpenAILLM
    from mcp_servers.rag.server import mcp as rag_mcp
    from rag_pipeline import index

    class EvalLLM(OpenAILLM):
        async def observe(self, *a, **k):
            return []

    EVAL_LLM = EvalLLM()
    index.build()
    tools.use_in_process("rag", rag_mcp)
    tools.use_in_process("business", stub)
    budget = {"tokens": 0, "max": args.max_tokens}
    t0 = time.time()
    if args.smoke:  # the whole base arc once with the harness (condition B): wiring of choice, persuade, closing
        os.environ["DIALOGUE_HARNESS"] = "1"
        sess = new_session("B", 0)
        rows = [{"n": n, "text": t, "choice": c, "addressed": a, "markup": None} for n, (t, c, a) in enumerate(E2E, 1)][:args.smoke_turns]
        for t in await play(sess, rows, budget):
            print(f"[나] {t['user']}  ({t['llm_calls']} calls, {t['tokens_in']}+{t['tokens_out']} tok, notes {t['notes']}, err {t['error']})")
            print("   plan", [(i["persona"], i.get("move"), i.get("target")) for i in t["plan"]])
            for ln in t["lines"]:
                print(f"   [{ln['speaker']}·{ln['kind']}] {ln['text']}")
        print("dialogue:", json.dumps(sess["dialogue"], ensure_ascii=False)[:2500], f"\ntokens {budget['tokens']:,}")
        return
    if args.supplement:  # e.g. B:1 when the budget guard skipped a whole pair: the cheap variant scripts only
        prev = json.loads(Path(args.out).read_text(encoding="utf-8"))
        c, r = args.supplement.split(":")
        for flag in ("0", "1"):
            os.environ["DIALOGUE_HARNESS"] = flag
            prev["runs"] += await run_arm(flag, c, int(r), budget, variants=("markup", "avoid"))
        runs = prev["runs"]
        prev["meta"]["supplement"] = {"pair": args.supplement, "variants": ["markup", "avoid"], "tokens": budget["tokens"]}
        prev["meta"]["total_tokens"] += budget["tokens"]
        prev["metrics"] = {f: metrics([x for x in runs if x["flag"] == f]) for f in ("0", "1")}
        prev["by_condition"] = {cc: {f: metrics([x for x in runs if x["flag"] == f and x["cond"] == cc]) for f in ("0", "1")} for cc in CONDITIONS}
        prev["by_variant"] = {v: {f: metrics([x for x in runs if x["flag"] == f and x["variant"] == v]) for f in ("0", "1")} for v in ("base", "markup", "avoid")}
        Path(args.out).write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
        print(table(prev["metrics"]))
        print(f"\nsupplement tokens {budget['tokens']:,} | total {prev['meta']['total_tokens']:,} | wrote {args.out}")
        return
    runs, pair_cost, skipped = [], [], []
    for r in range(args.reps):  # pairs (legacy, then harness) per condition/rep: DIALOGUE_HARNESS is process-wide
        for c in CONDITIONS:
            if pair_cost and budget["tokens"] + statistics.mean(pair_cost) > args.max_tokens:
                skipped.append(f"{c}/rep{r}")  # both arms dropped together, so the comparison stays paired
                continue
            before = budget["tokens"]
            for flag in ("0", "1"):
                os.environ["DIALOGUE_HARNESS"] = flag
                runs += await run_arm(flag, c, r, budget)
            pair_cost.append(budget["tokens"] - before)
    agg = {f: metrics([r for r in runs if r["flag"] == f]) for f in ("0", "1")}
    by_cond = {c: {f: metrics([r for r in runs if r["flag"] == f and r["cond"] == c]) for f in ("0", "1")} for c in CONDITIONS}
    out = {"meta": {"model": os.getenv("LLM_MODEL"), "embeddings": args.embeddings, "reps": args.reps, "scenario": "dl.pm.fintech",
                    "conditions": CONDITIONS, "variants": ["base", "markup", "avoid"], "observer": "skipped in both arms",
                    "thresholds": {"self": 0.30, "echo": 0.28, "quote_span": 20}, "total_tokens": budget["tokens"], "wall_s": round(time.time() - t0),
                    "pair_tokens": pair_cost, "skipped_pairs": skipped,
                    "date": time.strftime("%Y-%m-%d")},
           "metrics": agg, "by_condition": by_cond,
           "by_variant": {v: {f: metrics([x for x in runs if x["flag"] == f and x["variant"] == v]) for f in ("0", "1")} for v in ("base", "markup", "avoid")},
           "runs": runs}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(table(agg))
    for c in CONDITIONS:
        print(f"\ncondition {c} {CONDITIONS[c]}\n" + table(by_cond[c]))
    print(f"\ntotal tokens {budget['tokens']:,} | wall {round(time.time() - t0)} s | wrote {args.out}")


EVAL_LLM = None

if __name__ == "__main__":
    asyncio.run(main())
