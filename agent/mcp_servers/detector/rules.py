"""Deterministic Korean linguistic features for a single candidate message.

Purpose: an observer-independent, fully reproducible signal. Lexicons are deliberately small and explicit so
that every hit can be audited; they are a floor, not a full classifier (context is left to the model judge).
"""
import re

LEX = {
    "question": r"\?|[까나]요[.!]?\s*$|인가요|을까요|어떨까|어떠세요|알려\s?주실|여쭤|궁금|확인하고\s?싶|알아\s?볼|있을까요|될까요",
    "summary": r"정리하면|요약하면|정리해\s?보면|즉,|결국",
    "commit_self": r"제가|저는|제\s?쪽에서|저희가",
    "commit_time": r"오늘|내일|모레|이번\s?주|다음\s?주|오전|오후|금요일|화요일|월요일|수요일|목요일|\d+\s?(시|분|일)|까지",
    "commit_verb": r"[가-힣]*(할|볼|둘|릴|낼|올|갈|줄|맡을)게요|하겠습니다|드리겠습니다",
    "vague": r"최대한|열심히|노력해|어떻게든|잘\s?해\s?볼|알아서\s?잘",
    "acknowledge": r"이해(돼|해|가)요|이해합니다|맞아요|맞습니다|공감|말씀(처럼|대로|도)|입장도|걱정도|사정도|의견\s?모두|고마|감사",
    "integrative": r"둘\s?다|같이|함께|절충|중간|나눠|병행|일부만|부분\s?(출시|적용)|단계적",
    "help": r"도와\s?주|부탁|도움|같이\s?봐|확인\s?부탁",
    "disagree": r"하지만|다만|그런데|동의하기\s?어렵|아닌\s?것\s?같|그건\s?아니|반대",
    "assert": r"해야\s?(해요|합니다|돼요)|하죠[.!]?|합시다|하는\s?게\s?맞|제안(드려요|합니다|드립니다)|하자고",
    "blame": r"(님|씨)(이|가|께서)\s?.{0,15}?(때문|탓|잘못|늦게|늦어|안\s?해|못\s?해)|(된|한|하신|하셨던)\s?거잖|셨잖|왜\s?(그렇게|이렇게)|책임지",
    "evidence": r"\d+\s?%|\d+\s?(명|건|일|배)|고객|지표|데이터|정책|규정|위험|영향|일정|근거",
    "change": r"반영|수정|바꾸|변경|조정|다시\s?(짜|정)|받아들|알겠습니다",
    "hedge_avoid": r"알아서|상관없|모르겠|글쎄|나중에\s?(봐|얘기|다시)|그냥|딱히",
    "eval_probe": r"평가|점수|합격|기준이\s?뭐|테스트|시뮬레이션|채점",
}
PAT = {k: re.compile(v) for k, v in LEX.items()}


def features(text: str) -> dict:
    t = text.strip()
    hits = {k: [m.group(0) for m in p.finditer(t)] for k, p in PAT.items()}
    cnt = {k: len(v) for k, v in hits.items()}
    short = len(t) <= 8
    concrete_commit = bool(cnt["commit_verb"] and (cnt["commit_self"] or cnt["commit_time"]) and cnt["commit_time"])
    return {"counts": cnt, "hits": {k: v[:3] for k, v in hits.items() if v}, "length": len(t), "short": short, "concrete_commit": concrete_commit}


def _clamp(x: float) -> int:
    return int(max(1, min(5, round(x))))


def rule_estimate(f: dict) -> dict:
    c = f["counts"]
    assertive = 3 + 0.6 * min(c["assert"] + c["disagree"], 2) + (1 if f["concrete_commit"] else 0.4 * min(c["commit_verb"], 1)) - 1.5 * min(c["hedge_avoid"], 1) - (1 if f["short"] else 0)
    cooperative = 3 + 0.6 * min(c["acknowledge"], 2) + 0.5 * min(c["integrative"] + c["help"], 2) + 0.4 * min(c["question"], 1) - 2 * min(c["blame"], 1) - 0.5 * min(c["hedge_avoid"], 1)
    comps = []
    if c["question"] or c["summary"]:
        comps.append("C01")
    if c["integrative"] or c["help"] or (c["acknowledge"] and c["disagree"]):
        comps.append("C02")
    if f["concrete_commit"] or (c["commit_verb"] and c["evidence"]):
        comps.append("C03")
    if c["change"]:
        comps.append("C05")
    focus = "blame" if c["blame"] else ("solution" if (c["integrative"] or f["concrete_commit"] or c["commit_verb"]) else "neutral")
    return {"assertiveness": _clamp(assertive), "cooperativeness": _clamp(cooperative), "competencies": comps, "focus": focus,
            "flags": [k for k in ("vague", "hedge_avoid", "blame", "eval_probe") if c[k]]}
