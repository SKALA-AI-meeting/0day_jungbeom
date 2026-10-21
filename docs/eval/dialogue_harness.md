# Dialogue harness — before/after evaluation

Design: `docs/architecture/dialogue-harness.md`. Raw data (every turn, plan, line, trace): `docs/eval/dialogue_harness.json`.
Reproduce: `cd agent && uv run --python 3.12 --env-file ../.env python ../scripts/dialogue_eval.py --reps 2 --max-tokens 850000`
(recompute the metrics without model calls: `... dialogue_eval.py --rescore`).

## Method

- **System under test.** The turn graph (`app/graph.py`) runs in-process with the real model: `gpt-4o-mini`, personas at
  temperature 0.8, structured calls at 0.1. RAG runs through in-process rag-mcp on a fresh `text-embedding-3-small`
  index. business-mcp is replaced by a stub that serves only `get_artifact`. Sessions are built by the script (no
  Spring, no `tests/fake_backend.py`). Every session carries the same three shared artifacts (design doc, schedule
  table, notification code), as START would seed them.
- **Arms.** `DIALOGUE_HARNESS=0` (previous flow, byte-identical prompts) vs `=1`. The observer is switched off in
  both arms; it does not affect persona lines, and this saves spend.
- **Scenario.** `dl.pm.fintech` (V2: review delayed vs Friday deadline). Each session opens with the fixed opening line
  of the baseline run, so both arms start from an identical state.
- **Scripts.** Candidate line 1 of `scripts/e2e.py` is played once per (arm, condition, rep); three scripts then
  branch from that state (a paired design):
  - `base`: e2e lines 2–8, the full 소통→조율→타협→설득 arc plus the closing
  - `markup`: e2e line 2 *unchanged*, but the candidate has left a risk markup on the code artifact (L3–4, "계좌번호 전체가
    알림 본문과 로그에 그대로 들어가요"). The chat never mentions it.
  - `avoid`: e2e line 2 addressed to the avoiding persona by name ("서윤님은/도현님은 … 어떻게 보세요?")
- **Conditions** (TKI). A = lead avoiding / peer collaborating (the condition of the baseline run); B = lead competing / peer avoiding.
- **Repetitions.** A × 2, B × 1. The script spends whole (legacy + harness) pairs and stops when the next pair would
  pass the token cap. Each pair cost about 280k tokens (legacy about 14.9k/turn), so the second repetition of B (`B/rep1`, 0-indexed) was skipped to stay under
  1M. Both arms were dropped together, so every comparison remains paired.
- **Spend.** 842,610 tokens in the measured run (378 s). Development smoke runs used about 300k more; they are not part of the results.

### Metrics

All metrics are computed by rules over persona lines. The thresholds come from `app/harness/dialogue.py`, calibrated on
`docs/eval/baseline_e2e_transcript.txt` before this run.

| metric | definition |
|---|---|
| self-repetition | max char-trigram Jaccard with the same persona's last 3 lines (mean; rate ≥ 0.30) |
| cross-persona echo | Jaccard with the other persona's last line (mean; rate ≥ 0.28) |
| repeated-citation rate | share of lines citing a clause number (`n조`) already cited earlier in the session |
| re-quote rate | share of lines sharing a ≥ 20-char run (spaces and punctuation removed) with an earlier persona line |
| sycophancy-marker rate | regex for praise and agreement markers ("매우 긍정적", "좋은 계획", "동의합니다", "공감", "체계적", …). It is *broader* than the guard's list but overlaps with it |
| addressed-first | the first reactive line comes from the persona the candidate addressed (labels written into the script, not detected) |
| avoiding compliance | among turns where the avoiding persona was not addressed, the share where it did not speak reactively; among turns where it was addressed, the share where it did. Beats are excluded (they are fixed scenario lines) |
| cross-talk | among turns with ≥ 2 reactive lines, the share where the second line calls the first speaker by name |
| markup uptake | on markup turns, a reactive line names the place (`#id`, `L3`, `3번째 줄`) or reuses the marked line or the markup's wording |
| distinct-2 | unique word bigrams / all word bigrams, per session, averaged |

## Results

All runs: legacy n = 75 persona lines, harness n = 51 (30 turns in each arm).

| metric | legacy (`DIALOGUE_HARNESS=0`) | harness (`=1`) |
|---|---|---|
| self-repetition, mean max sim ↓ | 0.197 | **0.094** |
| self-repetition rate (≥0.30) ↓ | 0.125 | **0.0** |
| cross-persona echo, mean sim ↓ | 0.160 | **0.060** |
| echo rate (≥0.28) ↓ | 0.139 | **0.0** |
| repeated-citation rate (same clause no.) ↓ | 0.587 | **0.0** |
| re-quote rate (≥20-char span) ↓ | 0.667 | **0.020** |
| lines citing a clause at all | 0.733 | 0.059 |
| sycophancy-marker rate ↓ | 0.280 | **0.0** |
| addressed-first compliance ↑ | 1.0 (n=9) | 1.0 (n=9) |
| avoiding persona quiet when unaddressed ↑ | 0.042 (n=24) | **1.0** (n=24) |
| avoiding persona answers when addressed ↑ | 1.0 (n=6) | 1.0 (n=6) |
| cross-talk rate ↑ | 0.296 (n=27) | 1.0 (n=3) |
| markup uptake ↑ | 0.0 (n=3) | **1.0** (n=3) |
| artifact opened on markup turns | 0.0 (n=3) | 0.667 (n=3) |
| distinct-2 ↑ | 0.813 | **0.927** |
| mean line length (chars) | 190 | 141 |
| lines with Markdown/LaTeX | 0.0 | 0.255 |
| persona lines per turn | 2.5 | 1.7 |
| LLM calls per turn | 6.0 | 5.2 |
| tokens per turn (in+out) | 14,882 | 13,205 |
| tokens per persona line | 5,953 | 7,768 |
| repetition-guard rewrites | – | 17 (of 51 lines) |
| failed turns | 0 | 0 |

The direction is the same in both conditions. Per condition (legacy → harness):

| | A (avoiding lead / collaborating peer) | B (competing lead / avoiding peer) |
|---|---|---|
| self-repetition mean | 0.192 → 0.096 | 0.206 → 0.091 |
| echo mean | 0.150 → 0.061 | 0.180 → 0.059 |
| re-quote rate | 0.633 → 0.0 | 0.731 → 0.059 |
| sycophancy rate | 0.286 → 0.0 | 0.269 → 0.0 |
| avoiding quiet when unaddressed | 0.062 → 1.0 (n=16) | 0.0 → 1.0 (n=8) |
| tokens per turn | 14,526 → 13,497 | 15,595 → 12,621 |

The same final candidate line ("정리하면 오늘 검토 요청, 금요일 부분 출시, 다음 주 나머지 출시예요.", condition A, rep 0):

- **legacy:** both personas start with "말씀하신 대로 …는 (매우) 좋은 계획입니다", both cite 2조 "영업일 기준 3일" again, and the peer ends with "언제든지 도움을 드릴 수 있습니다".
  The closing is one generic sentence.
- **harness:** one peer line that keeps its point ("어떤 항목을 포함할지 명확히 하지 않으면 고객 약속을 지키기 어렵습니다"). The closing lists the
  candidate's commitments from the ledger as bullets (요청 오늘 3시까지, 통과 범위 목요일 확정, 부분 출시 범위 오늘 오후 공유, …).

On the markup turns, the harness persona answered at the marked line in 3/3 cases ("L3에서 계좌번호가 전체 포함되는 것은 … 뒤
4자리만 표시하도록 수정해야"). In 2/3 it opened the artifact first; in the third it used the quoted line in the move card.
The legacy arm cannot see artifacts, so its 0/3 is by construction.

## Discussion

**What clearly improved.** The failure patterns of the baseline transcript largely disappear:

- re-citing the same clause (0.59 → 0)
- restating it in other words (re-quote 0.67 → 0.02)
- echoing the other persona (mean similarity 0.16 → 0.06, no line over threshold)
- praise and agreement openers (0.28 → 0)

Lexical diversity rose (distinct-2 0.81 → 0.93) and lines became shorter (190 → 141 chars). The avoiding-mode rule
moved from "almost never respected" (1 of 24 unaddressed turns) to enforced by code, while the avoiding persona still
answered every time it was called by name. Markdown now appears in a quarter of the lines (mostly bold key terms and
bullet lists in the closing). The turn costs 11% fewer tokens and 0.8 fewer calls despite the extra ledger call, but this is **mostly a volume
effect**: the harness produces fewer persona lines (1.7 vs 2.5 per turn). Per persona line it costs about 30% *more*
(7,768 vs 5,953 tokens), because each line carries the director's move card, the ledger slice and, for 17 of 51 lines,
a guard rewrite. The shorter context (summary plus 6 messages instead of the transcript) and unforced retrieval save
tokens per call, but not enough to offset that; the cost claim should be read as "same budget per turn", not "cheaper".

**Where it did not help, or the numbers flatter it.**

- **Grounding dropped sharply.** Only 6% of harness lines cite a clause (legacy 73%). "0 repeated citations" is
  mostly an artefact of citing less: the ledger's `cited` list ends empty in most sessions, so the re-cite rule and the
  "already cited" hint rarely fire, and the personas often say "규정에 따르면" without saying which one. The just-in-time doc hint is
  too weak. A better rule would be to cite each relevant clause once, when it first matters (e.g. 3조 when the
  candidate proposes a partial review).
- **The lexical metrics overlap with the guard.** The guard rewrote 17 of 51 lines using similar rules (trigram
  similarity, spans, praise regex). The guard/metric thresholds and the eval regex are not identical, but part of the
  gain is by construction. Semantic repetition passes both. In condition A rep 0 the peer asked "어떤 항목을 포함할지"
  in five consecutive turns, with different words each time; an LLM judge or an embedding-based check would be needed to
  measure and prevent that.
- **Less conversation, and cross-talk is rare.** Persona lines per turn fell from 2.5 to 1.7. In both conditions one
  persona is avoiding, so on unaddressed turns only one persona may speak, and on beat turns the budget is one reactive
  line. Cross-talk is 1.0 but on only n = 3 two-line turns; legacy had 27 two-line turns at 0.30. The harness trades
  "two personas talk past each other" for "one persona speaks, the other stays silent as its mode says". Whether
  candidates now get enough coordination pressure is not answered by these metrics. In condition B the competing lead
  carries almost every turn.
- **Addressed-first did not change.** Both arms score 1.0 (n = 9); the legacy director already respected explicit
  names in these scripts. The code rule matters for robustness, not for this sample.
- **Ledger quality is mixed.** Commitments are captured with their due times and drive a useful closing. However:
  - the candidate's commitments are duplicated when restated ("오늘 검토 요청" and "요청을 오늘 3시까지 보낼 것"), which
    shows in the closing list
  - issues stay mostly stale after turn 2 (two open issues for the whole session)
  - before the provenance rules were added, positions were attributed to the wrong speaker; the rules fix that
    structurally, but issue tracking still needs work
- **Small n, one scenario.** There are 3 sessions per arm for the full arc, 3 markup turns and 3 avoid turns per arm,
  one value-dilemma scenario, and one model. The rates are descriptive. No significance testing was done, and the
  per-condition numbers rest on 1–2 sessions.

**Next steps suggested by the data.**

- A per-clause "cite once" policy, to restore grounding.
- A semantic-repetition check (embedding similarity of the persona's *claims* in the ledger) for the "same question,
  new words" case.
- Merging near-duplicate commitments in the ledger.
- Letting an addressed avoiding persona be followed by a short reaction from the other persona when tension is high,
  to restore some cross-talk without breaking the avoiding rule.
- An LLM-judge rubric (realism, pressure on the candidate, groundedness) on a held-out set of sessions.

## After this run (not re-measured)

The numbers above describe the harness as measured. Changes made afterwards from review findings, which a re-run with the
same command would need to confirm: the guard also flags a line that restates the persona's own ledger claim in other
words (`restate_claim`, trigram containment ≥ 0.5), open issues that no line touches for 12 messages are parked, user
commitments with the same due date merge, a markup the candidate cites in chat is answered first and unanswered markups
carry over to the next turn, and the persona/director prompts ask for LaTeX on every metric and lists/tables for two or
more options. Semantic repetition is still measured only lexically; an LLM-judge or embedding measure remains open.
