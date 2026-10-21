"""Dialogue harness (item 6): context engineering for the 3-party chat. Behind DIALOGUE_HARNESS ("1" default, "0" = legacy).

  Ledger   structured notes per session (session["dialogue"] in, final turn state "dialogue" out; api-contract §2):
           rolling summary of older turns (compaction), issues, commitments, positions, turn stats, cited clauses,
           markups_seen. One cheap structured LLM call per turn (graph.ledger, parallel to observer and director);
           everything else is updated by the rules in this file.
  Policy   AG2-style allowed speaker transitions, enforced in code after the director: addressed persona first,
           an avoiding persona only when addressed by name, at most 2 persona lines per candidate turn, balance,
           cross-talk when positions conflict, a new markup gets answered by one persona (owner first).
  Cards    the director picks a move per speaker; a persona gets that move card plus an assembled context
           (summary + recent window + ledger slice + own position + the other's last claim + shared artifacts).
  Guard    self-repetition / restated stance / echo / repeated citation / same opener / sycophancy check on each persona line;
           a violation triggers one non-streamed rewrite (llm.speak), traced via tracer.note.
Design notes and sources: docs/architecture/dialogue-harness.md.
"""
from __future__ import annotations

import copy
import json
import os
import re
from difflib import SequenceMatcher

from .. import artifacts
from ..personas import PREFERRED_MOVES
from . import context

VERSION = 1
WINDOW = 6  # recent messages kept verbatim (about three exchanges); older ones live in the rolling summary
SUMMARY_MAX = 700  # chars kept from the summary (the ledger prompt asks for ~400)
MAX_PENDING = 12  # messages folded into the ledger per update
MAX_ISSUES, MAX_COMMITMENTS, MAX_CITED = 8, 12, 24
SELF_SIM, ECHO_SIM = 0.30, 0.28  # char-trigram Jaccard, calibrated on docs/eval/baseline_e2e_transcript.txt
QUOTE_SPAN = 20  # chars (no spaces/punct.) shared with any earlier persona line = restating a clause or a sentence
BALANCE_GAP = 3  # an unaddressed persona that spoke this many lines more than the other yields the floor
STALE_MSGS = 12  # an open issue nobody has talked about for this many messages (about four turns) is parked
TOUCH, CLAIM_SIM = 0.35, 0.5  # share of an issue title's / a persona claim's trigrams found in a line
PERSONAS = ("lead", "peer")

MOVES = {
    "answer": ("답하기", "상대의 질문·요청에 직접 답한다. 결론부터 말한다."),
    "ask_clarify": ("되묻기", "판단에 필요한 정보 하나를 구체적으로 되묻는다."),
    "challenge": ("반박", "상대 주장의 한 지점을 근거를 들어 반박한다. 동의나 칭찬으로 시작하지 않는다."),
    "propose": ("제안", "새 구체안 하나를 낸다(누가·무엇·언제)."),
    "concede": ("양보", "한 지점을 조건을 붙여 양보한다. 무엇을 양보하고 무엇은 지키는지 밝힌다."),
    "build_on": ("덧붙이기", "상대 말에 새 정보나 조건 하나를 더한다. 같은 말을 되풀이하지 않는다."),
    "address_markup": ("마크업 답하기", "지원자가 과제에 남긴 마크업 하나에 답한다. 해당 줄을 짚고, 고칠지 그대로 둘지 이유와 함께 말한다."),
    "summarize": ("정리", "정해진 것과 남은 쟁점을 짧게 정리한다(목록 가능). 결정을 대신 내리지 않는다."),
}
STATUS_LABEL = {"open": "열림", "agreed": "합의", "parked": "보류"}
FORMS = {
    "plain": "",
    "list": "선택지·단계가 여럿이면 짧은 글머리 목록(- )으로 쓴다.",
    "table": "안이나 일정을 견줄 때는 작은 Markdown 표(3열·3행 이내)로 쓴다.",
    "formula": "지표·계산은 LaTeX로 쓴다(문장 안은 $…$, 따로 보일 식은 $$…$$).",
}


def enabled() -> bool:
    return os.getenv("DIALOGUE_HARNESS", "1").strip() != "0"


def other(pid: str) -> str:
    return "peer" if pid == "lead" else "lead"


# ---------- ledger (structured note-taking + compaction) ----------
def new_ledger() -> dict:
    return {
        "version": VERSION, "summary": "", "issues": [], "commitments": [],
        "positions": {"lead": {"claim": None, "conceded": None}, "peer": {"claim": None, "conceded": None}, "user": {"claim": None}},
        "turns": {"lead": {"last_idx": None, "count": 0}, "peer": {"last_idx": None, "count": 0}},
        "markups_seen": [], "cited": [],
        "upto_idx": -1,  # last message idx folded into summary/issues/commitments/positions
        "last_moves": [],  # [{persona, move, issue, idx}] so the director does not repeat itself
    }


def load(session: dict) -> dict:
    """session["dialogue"] (opaque JSON kept by Spring) normalised to the v1 shape; a fresh ledger when absent or unreadable."""
    raw = session.get("dialogue")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    led = new_ledger()
    if not isinstance(raw, dict):
        return led
    for k, v in copy.deepcopy(raw).items():
        if k in ("positions", "turns") and isinstance(v, dict):
            for who, val in v.items():
                if isinstance(val, dict):
                    led[k].setdefault(who, {}).update(val)
        elif v is not None:
            led[k] = v
    led["markups_seen"] = [str(x) for x in led.get("markups_seen") or []]
    return led


def pending(ledger: dict, history: list[dict]) -> list[dict]:
    """Messages not yet folded into the ledger (the previous turn's persona lines + this candidate line)."""
    upto = ledger.get("upto_idx", -1)
    return [m for m in history if m.get("speaker") != "system" and m["idx"] > upto][-MAX_PENDING:]


def _next_issue_id(issues: list[dict]) -> str:
    nums = [int(i["id"][1:]) for i in issues if re.fullmatch(r"i\d+", str(i.get("id", "")))]
    return f"i{max(nums, default=0) + 1}"


def _find_issue(issues: list[dict], title: str) -> dict | None:
    best, score = None, 0.0
    for it in issues:
        s = 1.0 if _norm(it["title"]) == _norm(title) else similarity(it["title"], title)
        if s > score:
            best, score = it, s
    return best if score >= 0.5 else None


_NULLISH = {"", "null", "none", "n/a", "-", "없음", "(없음)"}


def _val(v) -> str | None:
    """Model output -> clean string or None (small models sometimes write the string "null")."""
    v = (v or "").strip() if isinstance(v, str) else v
    return None if v is None or (isinstance(v, str) and v.lower() in _NULLISH) else v


def apply_update(ledger: dict, upd: dict, pend: list[dict]) -> dict:
    """Merge the ledger model's output (LedgerUpdate as a dict) into the ledger. Issue ids stay stable across turns."""
    led = copy.deepcopy(ledger)
    last = pend[-1]["idx"] if pend else led.get("upto_idx", -1)
    idxs = {m["idx"] for m in pend}
    summary = _val(upd.get("summary")) or ""
    if summary:
        led["summary"] = summary if len(summary) <= SUMMARY_MAX else "…" + summary[-SUMMARY_MAX:]
    for it in upd.get("issues") or []:
        title = (_val(it.get("title")) or "")[:60]
        status = it.get("status") if it.get("status") in ("open", "agreed", "parked") else "open"
        if not title:
            continue
        by_id = next((i for i in led["issues"] if i["id"] == title), None) if re.fullmatch(r"i\d+", title) else None
        if re.fullmatch(r"i\d+", title) and by_id is None:
            continue  # an id the model made up
        old = by_id or _find_issue(led["issues"], title)
        if by_id is not None:
            title = by_id["title"]
        if old is None:
            raised = it.get("raised_by") if it.get("raised_by") in ("user", "lead", "peer") else "user"
            led["issues"].append({"id": _next_issue_id(led["issues"]), "title": title, "status": status, "raised_by": raised, "last_idx": last})
        elif old["status"] != status or _norm(old["title"]) != _norm(title):
            old.update(status=status, last_idx=last)
    for it in led["issues"]:  # the model lists every issue each time, so 'still open' says nothing: look at the lines
        if it["status"] == "open" and any(contained(it["title"], m.get("text", "")) >= TOUCH for m in pend):
            it["last_idx"] = last
        elif it["status"] == "open" and last - int(it.get("last_idx") or 0) >= STALE_MSGS:
            it.update(status="parked", last_idx=last)  # dropped from the conversation: no longer a live issue
    while len(led["issues"]) > MAX_ISSUES:  # drop the oldest settled issue first
        settled = [i for i in led["issues"] if i["status"] != "open"] or led["issues"]
        led["issues"].remove(min(settled, key=lambda i: i.get("last_idx") or 0))
    said = {m["idx"]: m for m in pend}
    for c in upd.get("new_commitments") or []:
        idx = c.get("idx") if c.get("idx") in idxs else next((m["idx"] for m in reversed(pend) if m.get("speaker") == c.get("who")), last)
        src = said.get(idx) or {}
        own = _DISCOURSE.sub("", src.get("text", ""))
        if c.get("who") in PERSONAS and not (src.get("speaker") == c.get("who") and _COMMIT.search(own)):
            continue  # a persona asking someone else is not a persona commitment
        _add_commitment(led, c.get("who"), _val(c.get("what")), _val(c.get("due")), idx)
    spoke = {m.get("speaker") for m in pend}
    for who in ("lead", "peer", "user"):
        p = upd.get(who) or {} if who in spoke else {}  # small models move one person's line onto another
        pos = led["positions"].setdefault(who, {"claim": None} if who == "user" else {"claim": None, "conceded": None})
        if _val(p.get("claim")):
            pos["claim"] = _val(p["claim"])[:160]
        if who != "user" and _val(p.get("conceded")):
            pos["conceded"] = _val(p["conceded"])[:160]
    led["upto_idx"] = last
    return led


def _add_commitment(led: dict, who, what, due, idx) -> None:
    what = (what or "").strip()[:120]
    if who not in ("user", "lead", "peer") or not what:
        return
    due = (due or "").strip()[:40] or None
    m = _DUE.search(what)
    if m and (not due or _norm(m.group(1)) not in _norm(due)):  # the time written in 'what' wins over a due from elsewhere
        due = m.group(1).strip()
    for c in led["commitments"]:
        same_due = bool(due) and _due_key(c.get("due")) == _due_key(due)
        if c["who"] == who and (similarity(c["what"], what) >= 0.45 or (same_due and contained(c["what"], what) >= 0.3)):
            if due and due != c.get("due"):
                c.update(due=due, idx=idx)
            return
    led["commitments"].append({"who": who, "what": what, "due": due, "idx": idx})
    del led["commitments"][:-MAX_COMMITMENTS]


def _due_key(due) -> str:
    return re.sub(r"(까지|중)$", "", _norm(due or ""))


def fallback_update(ledger: dict, pend: list[dict], names: dict) -> dict:
    """Ledger model failed: keep compaction moving with a rule digest and rule-detected candidate commitments."""
    led = copy.deepcopy(ledger)
    if pend:
        bits = context.digest(pend, names, k=len(pend), width=36)
        s = f"{led['summary']} / {bits}".strip(" /")
        led["summary"] = s if len(s) <= SUMMARY_MAX else "…" + s[-SUMMARY_MAX:]
        for m in pend:
            if m.get("speaker") == "user":
                for what, due in rule_commitments(m["text"]):
                    _add_commitment(led, "user", what, due, m["idx"])
        led["upto_idx"] = pend[-1]["idx"]
    return led


_DISCOURSE = re.compile(r"말씀\s?드리(겠습니다|ㄹ게요|릴게요)|여쭤\s?보(겠습니다|ㄹ게요|볼게요)")
_COMMIT = re.compile(r"(할게요|할께요|하겠습니다|드릴게요|드리겠습니다|볼게요|보겠습니다|낼게요|둘게요|올릴게요|보낼게요|맡을게요)")
_DUE = re.compile(r"((?:오늘|내일|모레|이번\s?주|다음\s?주)?\s?(?:[월화수목금토일]요일)?\s?(?:오전|오후)?\s?\d{1,2}\s?시(?:\s?\d{1,2}\s?분)?(?:\s?까지)?"
                  r"|(?:오늘|내일|모레|이번\s?주|다음\s?주)\s?(?:[월화수목금토일]요일)?\s?(?:오전|오후)?(?:\s?중)?(?:\s?까지)?"
                  r"|[월화수목금토일]요일(?:\s?(?:오전|오후))?(?:\s?까지)?)")


def rule_commitments(text: str) -> list[tuple[str, str | None]]:
    """First-person '…할게요' sentences with a time expression if any (MockLLM and the ledger fallback)."""
    out = []
    for sent in re.split(r"(?<=[.!?。])\s+|\n", text or ""):
        sent = sent.strip()
        if sent and _COMMIT.search(sent):
            m = _DUE.search(sent)
            out.append((sent[:120], m.group(1).strip() if m else None))
    return out


def rule_update(ledger: dict, msgs: list[dict], *, plan: list[dict] | None = None, known_docs=()) -> dict:
    """Per persona line, without a model: turn stats, cited clauses, the move each speaker made."""
    led = copy.deepcopy(ledger)
    moves = {i["persona"]: i for i in plan or []}
    for m in msgs:
        pid = m.get("speaker")
        if pid not in PERSONAS:
            continue
        t = led["turns"].setdefault(pid, {"last_idx": None, "count": 0})
        t["count"] = int(t.get("count") or 0) + 1
        t["last_idx"] = m["idx"]
        for key in citations(m["text"], m.get("sources"), known_docs):
            if key not in led["cited"]:
                led["cited"].append(key)
        if pid in moves:
            led["last_moves"].append({"persona": pid, "move": moves[pid].get("move"), "issue": moves[pid].get("issue"), "idx": m["idx"]})
    del led["cited"][:-MAX_CITED]
    del led["last_moves"][:-6]
    return led


def new_markups(session: dict, ledger: dict) -> list[dict]:
    seen = set(ledger.get("markups_seen") or [])
    return sorted((a for a in session.get("annotations") or [] if str(a["id"]) not in seen), key=lambda a: int(a["id"]))


def mark_seen(ledger: dict, marks: list[dict], answered=None) -> dict:
    """answered=None marks every markup; otherwise only the answered ones and 'ok' marks (they ask nothing), so the
    rest carry over and get their own answer next turn instead of being dropped."""
    led = copy.deepcopy(ledger)
    done = None if answered is None else {str(i) for i in answered if i}
    for a in marks:
        if done is not None and str(a["id"]) not in done and a.get("kind") != "ok":
            continue
        if str(a["id"]) not in led["markups_seen"]:
            led["markups_seen"].append(str(a["id"]))
    return led


def answered_markups(plan: list[dict]) -> list[str]:
    return [str(i["markup_id"]) for i in plan or [] if i.get("markup_id")]


def known_docs(history: list[dict], ledger: dict) -> list[str]:
    docs = [s.get("doc") for m in history for s in m.get("sources") or [] if s.get("doc")]
    docs += [c.rsplit(" §", 1)[0] for c in ledger.get("cited") or [] if " §" in c]
    return list(dict.fromkeys(d for d in docs if d))


# ---------- addressing + speaker policy (allowed transitions) ----------
# '두 분', '다들' name nobody, so a group address never counts as calling the avoiding persona.
_VOCATIVE = re.compile(r"\s?(?:님|씨|팀장님|아|야)?\s?[,!]")


def addressed(text: str, scn: dict, min_strength: int = 1) -> list[str]:
    """Personas the candidate addressed by name ('팀장님' counts for the lead; '서윤이는', '도현아' too), strongest first:
    a leading vocative ('도현님, …'), then a mention inside a question sentence, then any mention (later breaks ties).
    min_strength=2 drops plain third-person mentions ('서윤 팀장님이 말씀하신 대로')."""
    text = text or ""
    questions = [(m.start(), m.end()) for m in re.finditer(r"[^.?!\n]*\?", text)]
    best: dict[str, tuple[int, int]] = {}
    for pid in PERSONAS:
        full = scn["personas"][pid]["name"]
        pats = [re.escape(full), re.escape(full[1:]) + r"(?=\s?(?:님|씨|팀장|,|\s|$)|이[는가도랑]|[아야](?:[,\s?!]|$))"] + ([r"팀장님"] if pid == "lead" else [])
        for m in re.finditer("|".join(pats), text):
            pos = m.start()
            vocative = pos <= 2 and _VOCATIVE.match(text, m.end())
            strength = 3 if vocative else 2 if any(a <= pos < b for a, b in questions) else 1
            if strength >= min_strength and (pid not in best or (strength, pos) > best[pid]):
                best[pid] = (strength, pos)
    return sorted(best, key=lambda p: best[p], reverse=True)


def _move(pid: str, move: str, target: str = "user", **kw) -> dict:
    return {"persona": pid, "move": move, "target": target, "issue": kw.get("issue") or "지금 안건",
            "intent": kw.get("intent") or MOVES[move][1], "form": kw.get("form") or "plain", "markup_id": kw.get("markup_id")}


def _clean(m: dict) -> dict | None:
    pid = m.get("persona")
    if pid not in PERSONAS:
        return None
    move = m.get("move") if m.get("move") in MOVES else "answer"
    target = m.get("target") if m.get("target") in ("user", "lead", "peer") and m.get("target") != pid else "user"
    form = m.get("form") if m.get("form") in FORMS else "plain"
    return _move(pid, move, target, issue=(m.get("issue") or "").strip()[:60], intent=(m.get("point") or m.get("intent") or "").strip()[:160],
                 form=form, markup_id=str(m["markup_id"]) if m.get("markup_id") else None)


_LINES = re.compile(r"(?<![A-Za-z0-9])L(\d{1,4})(?:\s?[-~]\s?L?(\d{1,4}))?")


def cite_score(mark: dict, text: str, session: dict | None) -> int:
    """How clearly the candidate's line points at this markup: its artifact named ('[제목 L13-14]' from the
    '대화에 인용' button, the id 'a3', or the title) counts 2, an overlapping L-range 1."""
    text = text or ""
    art = next((a for a in (session or {}).get("artifacts") or [] if a["id"] == mark.get("artifact_id")), None)
    title = (art or {}).get("title") or ""
    named = bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(str(mark.get('artifact_id')))}(?![0-9])", text)) or \
        bool(title and (title[:19] in text or title in text))
    an = mark.get("anchor") or {}
    hit = False
    if an.get("line_start"):
        ls, le = int(an["line_start"]), int(an.get("line_end") or an["line_start"])
        hit = any(int(a) <= le and int(b or a) >= ls for a, b in _LINES.findall(text))
    return 2 * named + hit


def pick_markup(marks: list[dict], user_text: str = "", session: dict | None = None) -> dict:
    """The markup the candidate's line cites (artifact title/id, then L-range); otherwise the newest that asks for
    something (question/risk/suggest beat 'ok')."""
    asking = [a for a in marks if a.get("kind") != "ok"] or marks
    return max(asking, key=lambda a: (cite_score(a, user_text, session), int(a["id"])))


def owner_of(session: dict, artifact_id: str) -> str | None:
    art = next((a for a in session.get("artifacts") or [] if a["id"] == artifact_id), None)
    return art.get("owner") if art and art.get("owner") in PERSONAS else None


def _vary(item: dict, ledger: dict, mode: str) -> None:
    """No third identical move in a row from the same persona (the competing lead otherwise challenges forever)."""
    if item["move"] in ("answer", "address_markup", "summarize"):  # a question still gets an answer
        return
    mine = [m.get("move") for m in ledger.get("last_moves") or [] if m.get("persona") == item["persona"]][-2:]
    if len(mine) == 2 and all(m == item["move"] for m in mine):
        options = [m for m in [*PREFERRED_MOVES.get(mode, []), "propose", "ask_clarify", "concede"] if m not in mine]
        item["move"] = options[0]
        item["intent"] = MOVES[item["move"]][1]


_METRIC = re.compile(r"[가-힣](?:율|률)|비율|퍼센트|\d\s?%|계산|수치|지표|산식")  # metric talk -> form 'formula'
_QUESTION = re.compile(r"\?|(?:나요|까요|가요|는지|을지)\s*[.!]?\s*$")


def select(moves: list[dict], *, scn: dict, modes: dict, user_text: str, ledger: dict, session: dict | None = None,
           marks: list[dict] | None = None, max_lines: int = 2, next_speaker: str | None = None, tension: bool = True) -> list[dict]:
    """Speaker policy applied to the director's proposal. Returns plan items in speaking order:
    {persona, move, target, issue, intent, form, markup_id}. Code, not the model, has the last word on who speaks."""
    named = addressed(user_text, scn)
    called = addressed(user_text, scn, min_strength=2)  # an avoiding persona wakes only for a vocative or a question
    allowed = [p for p in PERSONAS if modes.get(p) != "avoiding" or p in called]
    items, seen = [], set()
    for m in moves or []:
        it = _clean(m)
        if it and it["persona"] not in seen:
            seen.add(it["persona"])
            items.append(it)
    items = [i for i in items if i["persona"] in allowed]  # avoiding persona: only when called by name
    first = named[0] if named and named[0] in allowed else None
    if first:  # addressed persona answers first
        if not any(i["persona"] == first for i in items):
            items.insert(0, _move(first, "answer"))
        items.sort(key=lambda i: i["persona"] != first)
        items[0]["target"] = "user"
    count = lambda p: int(((ledger.get("turns") or {}).get(p) or {}).get("count") or 0)
    if not items:
        pid = min(allowed, key=lambda p: (p == next_speaker, count(p)))
        items = [_move(pid, "answer")]
    if not first and len(allowed) == 2:  # balance: the persona who has been talking much more yields the floor
        lead_p = items[0]["persona"]
        if count(lead_p) - count(other(lead_p)) >= BALANCE_GAP:
            items = items[::-1] if len(items) == 2 else [{**items[0], "persona": other(lead_p), "target": "user"}]
    if max_lines == 1 and not first and items[0]["persona"] == next_speaker:  # the fixed beat/closing speaker talks next anyway
        alt = next((i for i in items[1:]), None)
        if alt is not None:
            items = [alt, items[0]]
        elif other(next_speaker) in allowed:
            items = [{**items[0], "persona": other(next_speaker), "target": "user"}]
    items = items[:max(1, max_lines)]
    chosen = next((i["markup_id"] for i in items if i["markup_id"]), None)
    for i in items:  # code decides who answers a markup (below); a move without one is a plain answer
        i["markup_id"] = None
        if i["move"] == "address_markup":
            i["move"] = "answer"
    if marks:  # one persona answers one new markup concretely, preferably the artifact owner
        mk = pick_markup(marks, user_text, session)
        if not cite_score(mk, user_text, session):  # nothing cited: the director's pick, else the newest asking one
            mk = next((a for a in marks if str(a["id"]) == chosen), None) or mk
        owner = owner_of(session or {}, mk["artifact_id"])
        if owner == next_speaker and max_lines == 1 and other(owner) in allowed:
            owner = other(owner)  # the owner speaks the fixed beat next; the other persona takes the markup
        holder = next((i for i in items if i["persona"] == owner), None)
        if owner in allowed and not first:  # nobody was called by name: the owner speaks first, about the markup
            items = [holder or _move(owner, "address_markup"), *[i for i in items if i["persona"] != owner]][:max(1, max_lines)]
            holder = items[0]
        elif owner in allowed and holder is None and len(items) < max_lines:  # the addressed persona answers, the owner adds
            holder = _move(owner, "address_markup")
            items.append(holder)
        holder = holder or items[0]
        holder["markup_id"] = str(mk["id"])
        if not (holder is items[0] and first == holder["persona"]):  # an addressed question still gets its answer
            holder["move"], holder["target"] = "address_markup", "user"
        rest = [a for a in marks if a is not mk and a.get("kind") != "ok"]
        free = next((i for i in items if i is not holder and not (i is items[0] and first == i["persona"])), None)
        if rest and free is not None:  # a second markup the other speaker owns or the candidate cited (the rest carry over)
            mine = [a for a in rest if owner_of(session or {}, a["artifact_id"]) == free["persona"] or cite_score(a, user_text, session)]
            if mine:
                m2 = max(mine, key=lambda a: (cite_score(a, user_text, session), int(a["id"])))
                free.update(markup_id=str(m2["id"]), move="address_markup", target="user")
    for i in items:
        _vary(i, ledger, modes.get(i["persona"], ""))
        if i["form"] == "plain" and _METRIC.search(user_text or ""):
            i["form"] = "formula"
    if first and items[0]["persona"] == first and items[0]["move"] not in ("answer", "address_markup", "summarize") \
            and _QUESTION.search(user_text or ""):  # a question put to someone by name is answered before anything else
        if items[0]["intent"] == MOVES[items[0]["move"]][1]:  # keep a concrete point the director wrote
            items[0]["intent"] = MOVES["answer"][1]
        items[0]["move"] = "answer"
    if items[0]["move"] != "address_markup":
        items[0]["target"] = "user"  # the first line reacts to the candidate; cross-talk is the second line's job
    if len(items) == 2:  # cross-talk: the second speaker answers the first one
        a, b = items
        if b["move"] != "address_markup":
            b["target"] = a["persona"]
            if tension and b["move"] in ("answer", "build_on", "summarize", "ask_clarify"):
                b["move"] = "concede" if modes.get(b["persona"]) == "accommodating" else "challenge"
    return items


# ---------- prompt assembly ----------
def _name(names: dict, who: str | None) -> str:
    return names.get(who, who or "")


def _issues_block(ledger: dict) -> str:
    rows = [f"- {i['id']} [{STATUS_LABEL[i['status']]}] {i['title']}" for i in ledger.get("issues") or [] if i.get("status") in STATUS_LABEL]
    return "[쟁점]\n" + "\n".join(rows) if rows else ""


def _recent_commitments(ledger: dict, n: int = 6) -> list[dict]:
    """Latest commitments, the candidate's first (책임 이행 is about what the candidate promised)."""
    cs = (ledger.get("commitments") or [])[-n * 2:]
    return sorted(cs, key=lambda c: (c["who"] != "user", -(c.get("idx") or 0)))[:n]


def _commitments_block(ledger: dict, names: dict) -> str:
    rows = [f"- {_name(names, c['who'])}: {c['what']}" + (f" ({c['due']})" if c.get("due") else "") for c in _recent_commitments(ledger)]
    return "[약속]\n" + "\n".join(rows) if rows else ""


def commitments_text(ledger: dict, names: dict) -> str:
    rows = [f"{_name(names, c['who'])} — {c['what']}" + (f" ({c['due']})" if c.get("due") else "") for c in _recent_commitments(ledger)]
    return "; ".join(rows) if rows else "(기록된 약속 없음)"


def _position(ledger: dict, who: str) -> dict:
    return (ledger.get("positions") or {}).get(who) or {}


def cited_text(ledger: dict) -> str:
    """Stored as 'doc §3' (contract); shown to models as 'doc 3조' so they do not copy the § notation into chat."""
    return ", ".join(re.sub(r" §(\d+)$", r" \1조", c) for c in ledger.get("cited") or [])


def ledger_brief(ledger: dict, names: dict, director: bool = True) -> str:
    """Director view of the notes; the ledger model gets it without the speaking stats."""
    parts = [f"[앞선 흐름 요약]\n{ledger.get('summary') or '(아직 없음)'}", _issues_block(ledger), _commitments_block(ledger, names)]
    pos = []
    for who in ("lead", "peer", "user"):
        p = _position(ledger, who)
        if p.get("claim") or p.get("conceded"):
            pos.append(f"- {_name(names, who)}: {p.get('claim') or '-'}" + (f" / 양보: {p['conceded']}" if p.get("conceded") else ""))
    if pos:
        parts.append("[입장]\n" + "\n".join(pos))
    turns = ledger.get("turns") or {}
    if not director:
        return "\n".join(p for p in parts if p)
    parts.append("[발화 수] " + " / ".join(f"{_name(names, p)} {(turns.get(p) or {}).get('count', 0)}회" for p in PERSONAS))
    if ledger.get("last_moves"):
        parts.append("[최근 수] " + ", ".join(f"{_name(names, m['persona'])}:{m.get('move')}" for m in ledger["last_moves"][-4:]))
    if ledger.get("cited"):
        parts.append("[이미 나온 근거] " + cited_text(ledger))
    return "\n".join(p for p in parts if p)


def anchor_label(mark: dict) -> str:
    an = mark.get("anchor") or {}
    if an.get("line_start"):
        ls, le = an["line_start"], an.get("line_end") or an["line_start"]
        return f"L{ls}" if ls == le else f"L{ls}-{le}"
    q = (an.get("quote") or "").strip()
    return f"“{q[:40]}{'…' if len(q) > 40 else ''}”" if q else ""


def mark_label(mark: dict) -> str:
    return getattr(artifacts, "MARK_LABEL", {}).get(mark.get("kind"), mark.get("kind") or "")


def anchored_text(session: dict, mark: dict) -> str:
    """The artifact line(s) a markup points at, so the move card can quote them without a tool call."""
    art = next((a for a in session.get("artifacts") or [] if a["id"] == mark.get("artifact_id")), None)
    if not art:
        return ""
    an = mark.get("anchor") or {}
    lines = (art.get("body") or "").split("\n")
    if an.get("line_start"):
        ls = max(1, int(an["line_start"]))
        le = min(len(lines), int(an.get("line_end") or ls), ls + 3)
        return "\n".join(f"L{n}: {lines[n - 1]}" for n in range(ls, le + 1) if n <= len(lines))
    return f"“{(an.get('quote') or '')[:120]}”"


def persona_context(*, pid: str, names: dict, ledger: dict, history: list[dict], session: dict, marks: list[dict],
                    prev: dict | None = None, window: int = WINDOW) -> str:
    """Everything a persona sees besides its card: compacted past, notes, its own stance so far, the other's last claim,
    the shared artifacts (new markups only), then the recent window verbatim."""
    o = other(pid)
    chat = [m for m in history if m.get("speaker") != "system"]
    older = chat[:-window]
    parts = []
    if ledger.get("summary"):
        parts.append(f"[앞선 흐름 요약]\n{ledger['summary']}")
    elif older:
        parts.append(f"[앞선 흐름 요약]\n{context.digest(older, names)}")
    parts += [_issues_block(ledger), _commitments_block(ledger, names)]
    mine = _position(ledger, pid)
    parts.append("[네가 이미 밝힌 입장 — 다시 설명하지 말고 여기서 한 걸음 나아간다] " + (mine.get("claim") or "아직 밝히지 않음 — 카드의 입장에서 출발") +
                 (f" / 이미 양보한 것: {mine['conceded']}" if mine.get("conceded") else ""))
    theirs = _position(ledger, o)
    if theirs.get("claim"):  # their last line itself is in the recent window below
        parts.append(f"[{_name(names, o)}의 주장] {theirs['claim']}" + (f" / 양보: {theirs['conceded']}" if theirs.get("conceded") else ""))
    own = [m["text"] for m in chat if m.get("speaker") == pid][-2:]
    if own:
        parts.append("[네가 최근에 한 말 — 같은 내용·같은 첫마디 금지]\n" + "\n".join(f"- {t[:100]}" for t in own))
    if ledger.get("cited"):
        parts.append("[이미 나온 근거 — 다시 인용하지 않는다] " + cited_text(ledger))
    block = artifacts.context_block(session, new_ids={str(a["id"]) for a in marks})
    if block:
        parts.append(block + "\n(과제 내용이나 마크업을 두고 말할 때는 먼저 open_shared_artifact로 열어 줄을 확인한다.)")
    parts.append("[최근 대화]\n" + context.window(chat, names, n=window))
    return "\n\n".join(p for p in parts if p)


DOC_HINT_MAX_CITED = 4  # just-in-time retrieval: nudge a lookup only while few clauses are on the table


def move_values(item: dict, names: dict, *, session: dict, marks: list[dict], prev: dict | None = None, ledger: dict | None = None,
                history: list[dict] | None = None) -> dict:
    """Values for prompts/dialogue_move.md (the move card)."""
    label, desc = MOVES.get(item.get("move"), MOVES["answer"])
    extra = []
    if prev and item.get("target") == prev.get("speaker"):
        given = _name(names, prev["speaker"])[1:]
        extra.append(f"바로 앞 {_name(names, prev['speaker'])}의 말 중 한 지점에 직접 답한다('{given}님'으로 부른다). 그 말을 되풀이하지 않는다.")
    mk = next((a for a in marks if str(a["id"]) == str(item.get("markup_id"))), None) if item.get("markup_id") else None
    if mk:
        quoted = anchored_text(session, mk)
        extra.append(f"지원자 마크업 #{mk['id']} ({mk['artifact_id']} {anchor_label(mk)}, {mark_label(mk)}): {mk['text']}" +
                     (f"\n  해당 부분:\n  " + quoted.replace("\n", "\n  ") if quoted else "") +
                     "\n  이 줄을 짚어 구체적으로 답한다(줄은 " + (anchor_label(mk) or "인용한 문구") + "로 말하고, 마크업 번호 #" + str(mk["id"]) + "는 줄 번호가 아니다)" + (" (질문에 답한 뒤 한 문장으로)." if item.get("move") != "address_markup" else "."))
    own_last = next((m for m in reversed(history or []) if m.get("speaker") == item.get("persona")), None)
    if item.get("move") in ("answer", "challenge", "propose", "build_on") and len((ledger or {}).get("cited") or []) < DOC_HINT_MAX_CITED \
            and not (own_last and citations(own_last["text"], own_last.get("sources"))):
        extra.append("근거: 규정·절차·수치를 말할 때는 search_company_docs로 찾아 아직 안 나온 조항만 문서 이름과 함께 쓴다.")
    if FORMS.get(item.get("form")):
        extra.append("형식: " + FORMS[item["form"]])
    target = "지원자" if item.get("target") in (None, "user") else _name(names, item["target"])
    point = item.get("intent") or desc
    if mk and item.get("move") == "address_markup":  # the policy may have handed this move over: the markup is the point
        point = f"마크업 #{mk['id']}에 대한 너의 판단(고칠지 그대로 둘지)과 이유 한 가지"
    return {"move": label, "move_desc": desc, "target": target, "issue": item.get("issue") or "지금 안건",
            "point": point, "extra": "".join(f"\n- {e}" for e in extra)}


def hints(scn: dict, modes: dict, user_text: str, names: dict, marks: list[dict], max_lines: int, next_speaker: str | None,
          session: dict | None = None) -> dict:
    """What code already knows before the director runs (also shown to it as text)."""
    named = addressed(user_text, scn)
    rows = ["지원자가 이름으로 부른 사람: " + (", ".join(f"{_name(names, p)}({p})" for p in named) or "없음")]
    avoid = [p for p in PERSONAS if modes.get(p) == "avoiding"]
    if avoid:
        rows.append("회피형: " + ", ".join(f"{_name(names, p)}({p})" for p in avoid) + " — 이름으로 불리지 않으면 이번 턴에 말하지 않는다")
    rows.append(f"이번 턴 최대 발화자 수: {max_lines}" + (f" (이어서 {_name(names, next_speaker)}의 새 안건 발화가 나온다)" if next_speaker else ""))
    for a in marks[-3:]:
        owner = owner_of(session or {}, a["artifact_id"])
        rows.append(f"새 마크업 #{a['id']} ({a['artifact_id']} {anchor_label(a)}, {mark_label(a)}, 담당 {_name(names, owner) if owner else '팀'}): {a['text']}")
    return {"addressed": named, "markups": marks, "max_lines": max_lines, "text": "\n".join(rows)}


# ---------- repetition / echo guard ----------
def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", s or "")


def _grams(s: str, n: int = 3) -> set[str]:
    t = _norm(s)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def similarity(a: str, b: str) -> float:
    """Character-trigram Jaccard (robust to Korean particles and spacing)."""
    x, y = _grams(a), _grams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def contained(part: str, whole: str) -> float:
    """Share of part's trigrams found in whole (a short title or claim inside a longer line)."""
    x = _grams(part)
    return len(x & _grams(whole)) / len(x) if x else 0.0


def shared_span(a: str, b: str) -> str:
    """Longest common run of a and b after dropping spaces/punctuation (catches a clause re-quoted without its number)."""
    x, y = _norm(a), _norm(b)
    m = SequenceMatcher(None, x, y, autojunk=False).find_longest_match(0, len(x), 0, len(y))
    return x[m.a:m.a + m.size]


def _original(text: str, span: str) -> str:
    """The span as written in text (with its spaces), for the rewrite feedback."""
    m = re.search(r"[\W_]*".join(map(re.escape, span)), text)
    return m.group(0) if m else span


_CLAUSE = re.compile(r"(\d{1,2})\s?조(?!원|건|각|금|정|치|합|사|직)|§\s?(\d{1,2})")
_DOCNAME = re.compile(r"([가-힣A-Za-z·]+(?:\s[가-힣A-Za-z·]+){0,3}?\s?(?:규정|정책|가이드|기준|SLA|회의록|현황|소개))")


def citations(text: str, sources=None, docs=()) -> list[str]:
    """Clause citations in a line as 'doc §n' (doc resolved from known document names, the line's sources, or the text)."""
    names = list(dict.fromkeys([*docs, *[s.get("doc") for s in sources or [] if s.get("doc")]]))
    out = []
    for m in _CLAUSE.finditer(text or ""):
        n, before = m.group(1) or m.group(2), text[:m.start()]
        doc, at = None, -1
        for d in names:
            p = before.rfind(d)
            if p > at:
                doc, at = d, p
        if doc is None:
            cands = {s["doc"] for s in sources or [] if str(s.get("section", "")).startswith(f"{n}조")}
            doc = cands.pop() if len(cands) == 1 else None
        if doc is None:
            found = list(_DOCNAME.finditer(before[-40:]))
            doc = found[-1].group(1).strip() if found else None
        key = f"{doc} §{n}" if doc else f"§{n}"
        if key not in out:
            out.append(key)
    return out


def cited_before(key: str, keys) -> bool:
    """'doc §3' was cited before; a bare '§3' (document not named in the line) matches any document's §3."""
    keys = set(keys)
    if key in keys:
        return True
    n = key.rsplit("§", 1)[-1]
    return any(k.rsplit("§", 1)[-1] == n for k in keys) if key.startswith("§") else f"§{n}" in keys


_PRAISE = re.compile(r"(매우|정말|아주|굉장히)\s?(긍정적|훌륭|인상적)|훌륭(합니다|해요|하네요|한\s?(계획|생각|제안))|"
                     r"(매우|정말|아주)?\s?좋은\s?(계획|생각|제안|의견|정리|방법|접근|질문)(이네요|입니다|이에요|이라고|이세요|같아요)|"
                     r"잘\s?(수립|짜\s?주|정리해\s?주)|(계획|정리|접근)[이은가]?\s?(매우\s?)?체계적")
_AGREE_OPEN = re.compile(r"^\s*(\S+님(의|께서)?\s?)?(말씀|의견|생각)?(에|처럼|대로|에\s?따르면)?\s?(전적으로\s?|충분히\s?)?(동의|공감)(합니다|해요|하는|이에요)|"
                         r"^\s*\S+님\s?(말씀|의견)(처럼|대로|에\s?따르면|을\s?들어\s?보니)")


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?。])\s+|\n", (text or "").strip(), maxsplit=1)[0]


def opener(text: str) -> str:
    toks = re.sub(r"^[-*>\s]+", "", (text or "").strip()).split()
    return _norm(" ".join(toks[:2]))


def sycophancy(text: str, mode: str = "") -> str | None:
    m = _PRAISE.search(text or "")
    if m:
        return m.group(0)
    if mode != "accommodating":  # agreeing first is the accommodating mode's job
        m = _AGREE_OPEN.search(_first_sentence(text))
        if m:
            return m.group(0).strip()
    return None


def check(text: str, pid: str, *, history: list[dict], ledger: dict, user_text: str = "", sources=None, docs=(),
          mode: str = "", kind: str = "react") -> list[dict]:
    """Violations of the no-repeat rules for one persona line (empty list = fine). kind='beat' skips similarity,
    because a fixed situation line must carry its content even when the topic was touched before."""
    out = []
    chat = [m for m in history if m.get("speaker") in PERSONAS]
    own = [m["text"] for m in chat if m["speaker"] == pid][-3:]
    theirs = [m["text"] for m in chat if m["speaker"] == other(pid)][-1:]
    if kind == "react":
        s, last = max(((similarity(text, t), t) for t in own), default=(0.0, ""))
        if s >= SELF_SIM:
            out.append({"rule": "self_repeat", "score": round(s, 2), "last": last[:80]})
        e = max((similarity(text, t) for t in theirs), default=0.0)
        if e >= ECHO_SIM:
            out.append({"rule": "echo", "score": round(e, 2)})
        claim = _position(ledger, pid).get("claim") or ""
        if len(_norm(claim)) >= 8 and not any(v["rule"] == "self_repeat" for v in out):  # the same stance reworded
            c = contained(claim, text)
            if c >= CLAIM_SIM:
                out.append({"rule": "restate_claim", "score": round(c, 2), "claim": claim[:80]})
        span = max((shared_span(text, m["text"]) for m in chat), key=len, default="")
        if len(span) >= QUOTE_SPAN:
            out.append({"rule": "re_quote", "span": _original(text, span)[:60]})
    already = set(ledger.get("cited") or [])
    for m in chat:
        already.update(citations(m["text"], m.get("sources"), docs))
    asked = {f"§{a or b}" for a, b in re.findall(r"(\d{1,2})\s?조|§\s?(\d{1,2})", user_text or "")}
    again = [c for c in citations(text, sources, docs) if cited_before(c, already) and not any(c.endswith(a) for a in asked)]
    if again:
        out.append({"rule": "re_cite", "keys": again})
    op = opener(text)
    if len(op) >= 4 and (any(op == opener(t) for t in own[-1:]) or any(op == opener(t) for t in theirs)):
        out.append({"rule": "same_opener", "opener": " ".join(text.split()[:2])})
    marker = sycophancy(text, mode)
    if marker:
        out.append({"rule": "sycophancy", "marker": marker})
    return out


def feedback(violations: list[dict], names: dict, pid: str, policy: bool = False) -> str:
    """Rewrite instruction for one non-streamed retry (also covers the output-policy guard)."""
    o = _name(names, other(pid))
    rows = []
    if policy:
        rows.append("평가·점수·시뮬레이션 관련 표현이 있었다. 그런 표현은 빼라.")
    for v in violations:
        r = v["rule"]
        if r == "self_repeat":
            rows.append("네 최근 발화" + (f"('{v['last'][:60]}…')" if v.get("last") else "") + "와 같은 주장을 되풀이하고 있다. 그 주장은 다시 말하지 말고, "
                        "지원자의 마지막 말에 대한 구체적 반응 하나(받아들일 조건, 되물을 것, 새 일정·담당 중 하나)로 바꿔라.")
        elif r == "restate_claim":
            rows.append(f"이미 밝힌 입장('{v['claim'][:60]}')을 표현만 바꿔 다시 말하고 있다. 입장은 다들 안다. 그 입장에서 나온 "
                        "새 조건·구체안·되물을 것 하나만 말하라.")
        elif r == "echo":
            rows.append(f"{o}의 직전 말을 되풀이하고 있다. 요약하거나 맞장구치지 말고 너의 입장에서 다른 점이나 새 조건을 말하라.")
        elif r == "re_cite":
            keys = ", ".join(re.sub(r" §(\d+)$", r" \1조", k) for k in v["keys"])
            rows.append(f"이미 대화에서 인용된 근거({keys})를 다시 들고 있다. 그 조항은 빼고 구체적인 실행안이나 다른 근거로 말하라.")
        elif r == "re_quote":
            rows.append(f"앞에서 이미 나온 내용('{v['span']}')을 다시 풀어 말하고 있다. 다들 아는 내용이니 빼고 새 내용만 말하라.")
        elif r == "same_opener":
            rows.append(f"직전 발화와 같은 말('{v['opener']}')로 시작한다. 다르게 시작하라.")
        elif r == "sycophancy":
            rows.append(f"칭찬·맞장구('{v['marker']}')가 있다. 빼고 바로 본론을 말하라.")
    return "방금 대사를 고쳐 써라.\n" + "\n".join(f"- {r}" for r in rows) + "\n같은 카드의 할 일과 형식은 지킨다. 대사만 출력:"
