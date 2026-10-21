# Dialogue harness (item 6)

The 3-party chat (candidate, 팀장 lead, 동료 peer) is driven by LLM personas. The baseline run
(`docs/eval/baseline_e2e_transcript.txt`) shows the failures this harness targets:

- both personas cite the same clause turn after turn: 3조 appears in 8 of the 20 reactive persona lines, and 14 of 20 cite some clause (21 counting the opening line)
- they echo each other ("도현님 말씀에 동의합니다") and copy whole sentences from the previous speaker
- they drift into praise ("매우 긍정적입니다", "매우 체계적") near the end
- the avoiding-mode (회피형) lead speaks without being addressed
- the tension that should make the candidate coordinate collapses into agreement

The cause is mostly in the context, not the model. Every persona call saw the whole transcript, a forced RAG lookup
that returns the same three chunks every time, and an intent of one line. Nothing recorded what had already been
said, agreed, promised or cited, and nothing in code decided who may speak. The harness adds those pieces, behind a flag.

## What we borrowed

| source | idea | how it shows up here |
|---|---|---|
| AG2 / AutoGen GroupChat — [group chat](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/groupchat/groupchat/), [FSM transitions](https://docs.ag2.ai/latest/docs/use-cases/notebooks/notebooks/agentchat_groupchat_finite_state_machine/), [custom speaker selection](https://docs.ag2.ai/docs/topics/groupchat/customized_speaker_selection) | `allowed_or_disallowed_speaker_transitions` and a custom `speaker_selection_method`: the LLM proposes a speaker, the graph of allowed transitions constrains it | `dialogue.select()`: the director (LLM) proposes moves, then code enforces the transitions (addressed persona first, avoiding persona only when called by name, ≤2 persona lines per candidate turn, balance, owner answers a markup) |
| Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | context is a finite budget; *compaction* (summarise old turns, keep recent ones), *structured note-taking* outside the window, *just-in-time retrieval* through tools, tool-result clearing | the ledger (notes persisted per session), rolling summary + a 6-message verbatim window instead of the whole transcript, the artifact tool and a conditional doc-lookup hint instead of a forced search, RAG results shown to the model as `[doc · section] text` without index metadata |
| Wang et al. 2023, [Recursively summarizing enables long-term dialogue memory](https://arxiv.org/abs/2308.15022) | memory = previous summary + new segment, summarised again | the ledger model gets the previous summary and only the not-yet-folded messages (`upto_idx`) |
| Park et al. 2023, [Generative Agents](https://arxiv.org/abs/2304.03442) | memory stream plus *reflection*: higher-level statements derived from raw observations | positions (claim / conceded), issues and commitments are reflections over the raw messages. We skip the retrieval scoring (recency × importance × relevance), because a session is 20–30 messages and the window plus summary covers it |
| Hong et al. 2023, [MetaGPT](https://arxiv.org/abs/2308.00352) | a shared message pool of *structured* outputs; roles subscribe to what they need | the ledger is the shared structured pool. Each persona gets its own slice (own position, the other's claim, cited clauses, open issues, commitments), not the raw log |
| Qian et al., ACL 2024, [ChatDev](https://arxiv.org/abs/2307.07924) | chat chain with explicit sub-tasks; *communicative dehallucination* (ask for specifics before answering) | the `ask_clarify` move; the `address_markup` card quotes the exact artifact line, so the persona answers about L3, not "the code" |
| Penzo et al., EMNLP 2024, [Multi-party hangover](https://arxiv.org/abs/2409.18602); Inoue et al. 2025, [addressee recognition benchmark](https://arxiv.org/abs/2501.16643) | LLMs are weak at addressee recognition in multi-party chat (GPT-4o near chance on triadic dialogue) | the addressee is detected in code (`dialogue.addressed()`: vocative > name in a question > any mention), shown to the director as a fact, and enforced after it |
| Liang et al. 2023, [Multi-agent debate / degeneration-of-thought](https://arxiv.org/abs/2305.19118); Wynn et al. 2025, [Talk isn't always cheap](https://arxiv.org/abs/2509.05396); Yao et al. 2025, [inter-agent sycophancy](https://arxiv.org/abs/2509.23055) | agents converge too early, conform to each other and stop adding information | tension-preserving cross-talk (with conflicting positions the second speaker must `challenge`/`propose`/`concede` *at the first*), a move-variation rule, and the sycophancy/echo guard |

## Design

```
            session (Spring /internal state: messages, artifacts, annotations, dialogue)
                │
   START ───────┼──────────────► observe   (unchanged: evidence for C01/C02/C03/C05)
     │          │
     ├────► ledger  ── 1 structured call (LedgerUpdate) ─ fold messages idx > upto_idx into:
     │          │       summary (compaction), issues, commitments, positions;  failure -> rule digest
     │          │
     └────► plan:  hints (code)  ─────────────►  director v3 (LLM)  ─────►  speaker policy (code)
                   addressed persona, avoiding,   moves per speaker:          addressed first · avoiding only
                   max lines (beat next?),        answer | ask_clarify |      when named · ≤2 lines/turn ·
                   new markups                    challenge | propose |       balance · owner answers markup ·
                                                  concede | build_on |        no 3rd identical move ·
                                                  address_markup | summarize  2nd speaker answers the 1st
                                                  + target, issue, point, form
                │
                ▼
             react: for each plan item
                 context = summary + issues + commitments + own position + other's claim
                         + own last lines + cited clauses + artifacts.context_block(new markups) + last 6 messages
                 card    = prompts/dialogue_move.md (move, target, issue, point, markup line, form, doc hint)
                 speak() = persona_dialogue.md + tools [search_company_docs, open_shared_artifact] ≤ 2 rounds
                 guard   = self-repeat · echo · re-quote · re-cite · same opener · sycophancy (+ output policy)
                           └─ violation -> one non-streamed rewrite, TOKEN reset with the new text
                 rules   = turn stats, cited clauses, last moves, markups_seen
                │
             gate ─┬─ stay ──────────────────────────────► END   (final state carries `dialogue`)
                   ├─ next ── beat (fixed situation, same context + guard without similarity) ─► END
                   └─ finish ─ closing (lists the ledger's commitments) ─► END
```

### Ledger (structured note-taking)

`session["dialogue"]` comes in from `/internal/sessions/{id}/state`, and the turn graph returns `dialogue` in its
final state. The shape is api-contract §2 v1, plus two extra keys: `upto_idx` (the last message folded in) and `last_moves`.

- **One cheap call per turn.** The `ledger` node runs in parallel with the observer and the director, so it adds no latency.
  It folds in the previous turn's persona lines and this candidate line. The director therefore sees notes that are
  one candidate line behind, but it gets that line verbatim anyway. The personas run after the join and see the updated notes.
- **Fail-safe.** If the model call fails, the turn goes on: the summary gets a rule digest, candidate commitments come
  from a `…할게요` regex with a time expression, and `upto_idx` advances (traced as `ledger_failed`).
- **Rules over model output.** Small models make predictable mistakes, so code checks:
  - an issue id used as a title maps back to that issue; an invented id is dropped
  - a persona commitment is kept only if that persona's own message has a first-person promise
    (`말씀드리겠습니다` does not count)
  - a position changes only for someone who spoke in the batch
  - a time written in the commitment text ("목요일에 확정") wins over a different or empty `due`; a commitment by the same
    person with the same due and overlapping wording merges into the earlier one
  - the model re-lists every issue each turn, so "still open" carries no information: an open issue whose title shows up
    in the new lines (trigram containment ≥ 0.35) is touched; one nobody touched for 12 messages is set to `parked`
  - `"null"` strings become null
- Turn stats, cited clauses (`doc §n`), last moves and `markups_seen` are updated by rules after each persona line, without a model.

### Speaker policy

`dialogue.select()` takes the director's moves and returns plan items `{persona, move, target, issue, intent, form, markup_id}`.
Code has the last word on who speaks:

1. **Avoiding persona:** speaks only when called by name. "두 분", "다들" name nobody.
2. **Addressed persona** (vocative > name in a question > any mention; "팀장님" = lead): speaks first, answering the candidate, even if the director left it out.
3. **Nobody left after filtering:** one line from the less-heard allowed persona.
4. **Balance:** when nobody is addressed, a persona that spoke ≥3 more lines than the other yields the floor.
5. **Line budget:** at most 2 persona lines per candidate turn. When a fixed beat or the closing follows, there is one reactive line, preferably not from the beat speaker.
6. **New markups** (annotation ids not in `markups_seen`): one persona answers one of them: the one the candidate's line cites (artifact title as in the `[제목 L13-14]` the 대화에 인용 button writes, or its id, then an overlapping L-range), else the director's pick, else the newest non-`ok`. This is the artifact owner if allowed, otherwise the other persona. If someone was addressed, they still answer first and the owner adds the markup answer as the second line. When two lines are planned and another unanswered markup belongs to the second speaker (or is cited), that speaker answers it. Only answered markups (and `ok` marks, which ask nothing) go into `markups_seen`; the rest carry over to the next turn.
7. **Addressed question:** when the addressed persona's first move is not an answer and the candidate asked a question, it becomes `answer`. Metric talk in the candidate's line (…율/률, 비율, %, 계산, 지표) turns a `plain` form into `formula`.
8. **No third identical move in a row** from the same persona. The next preferred move of its conflict mode is used instead (`personas.PREFERRED_MOVES`).
9. **Cross-talk:** the first line reacts to the candidate. With two lines the second targets the first. If the director reports `tension`, an agreeing second move (`answer`/`build_on`/`summarize`/`ask_clarify`) becomes `challenge`, or `concede` for the accommodating mode.

### Persona context and move card

`dialogue.persona_context()` assembles the context in a fixed order: compacted past, then notes, then the persona's
own stance so far, then the other's claim, then the persona's last lines, then cited clauses, then shared artifacts
(only new markups listed), then the last 6 messages verbatim. The move card (`prompts/dialogue_move.md`) gives:

- the move and its description, the target, the issue, and the point to add
- for a markup: the marked line(s) quoted from the artifact body
- a form hint (list / table / formula)
- a doc-lookup hint, only while fewer than 4 clauses are cited and the persona did not just cite one
  (just-in-time instead of the old forced search)

`open_shared_artifact` is bound next to `search_company_docs` when the session has artifacts. It runs
`tools.call_for_model("business", "get_artifact", …)`, and the model sees `artifacts.render_for_model(result)`.
There are at most 2 tool rounds, and every tool-call id gets a ToolMessage.

### Repetition / echo guard

`dialogue.check()` runs on every persona line, using char-trigram Jaccard and normalised spans. The thresholds were
calibrated on the baseline transcript, where they flag the known-bad lines and pass the others
(`tests/test_dialogue.py::test_guard_flags_the_baseline_failures`).

| rule | trigger |
|---|---|
| `self_repeat` | similarity ≥ 0.30 with one of the persona's last 3 lines |
| `restate_claim` | ≥ 50% of the trigrams of the persona's own ledger claim appear in the line (the same stance reworded) |
| `echo` | similarity ≥ 0.28 with the other persona's last line |
| `re_quote` | a ≥ 20-char (no spaces/punctuation) run shared with any earlier persona line: a clause restated without its number |
| `re_cite` | a clause (`n조` / `§n`, document resolved from sources or text) already cited, unless the candidate asked about it |
| `same_opener` | the first two words equal the persona's or the other's last line |
| `sycophancy` | praise anywhere ("매우 긍정적", "좋은 계획이네요", "체계적") or an agreeing/echo opener ("…님 말씀에 동의합니다"); agreeing openers are allowed for the accommodating mode |

On a violation, the persona gets one non-streamed rewrite with rule-specific feedback. This is merged with the
existing output-policy guard, so a line gets at most one rewrite, and a single `TOKEN {reset: true}` replaces the
streamed draft. Each trigger is traced as `repetition_guard` and `repetition_guard.<rule>` notes. Beats and the
closing skip the similarity rules, because they must deliver fixed content.

### Rendering (item 3, LLM side)

The persona, director and closing prompts ask for Markdown and LaTeX only where they help:

- bullets for options and steps
- a small table to compare options or schedules
- **bold** for one key term
- `$…$` / `$$…$$` for metrics and formulas

The director can ask for this per move (`form`). `clean_line()` / `strip_boilerplate()` now keep line breaks: only
trailing offer-to-help sentences on the last line are removed. In prompt templates, a literal `$` is written as `$$`
(string.Template).

## Flag

`DIALOGUE_HARNESS` is read on every call, default `"1"`.

`"0"` reproduces the previous behaviour, with three exceptions:

- the `ledger` node is a no-op, so an extra empty node span appears in traces
- the final state has no `dialogue`
- `clean_line()` keeps line breaks in both modes (a contract fix: api-contract §4)

Otherwise `"0"` runs the previous flow exactly:

- `plan` uses `director.md` / `TurnPlan`
- `react` uses `directive_react*.md`
- `speak()` runs `_speak_legacy` (`persona.md`, `persona_turn.md`, one forced RAG round, streamed output-guard rewrite)
- beat and closing use their previous directives
- personas get no shared-artifact context and no `open_shared_artifact` tool, so candidate markups go unanswered
  (the UI still says teammates can see them); the markup feature is a harness feature

`tests/test_dialogue.py::test_flag_off_is_the_legacy_path` pins this.

## Limits and cost

- **Graph:** `observe ‖ ledger ‖ plan → react → gate → beat|closing` is 4 supersteps, within `max_graph_steps = 8`.
- **Model calls, worst case per turn:** 3 (observer, director, ledger) + 2 persona lines × (2 tool rounds + answer + rewrite) = 11.
  That is the same as the legacy worst case and within `max_model_calls = 16`, so `loop.py` is unchanged. Two persona
  lines per turn is the cap even when a beat follows.
- **RAG:** `rag.search_docs` stays under the per-task cap of 3 (`max_same_tool`), because the tool is no longer bound
  once the cap is reached. `business.get_artifact` is exempt, like every `business.*` tool.
- **Prompt size:** the persona prompt carries the summary and a 6-message window instead of up to 6000 transcript
  characters. See `docs/eval/dialogue_harness.md` for measured calls and tokens per turn.

## Files

`agent/app/harness/dialogue.py` (ledger, policy, context, guard), `agent/app/graph.py` (ledger node, harness branches),
`agent/app/llm.py` (director v3 `direct()`, `update_ledger()`, `_speak_dialogue()`, MockLLM paths),
`agent/app/personas.py` (`SPEECH_DIALOGUE`, `PREFERRED_MOVES`), `agent/app/harness/context.py` (`window()`, `numbered()`, `digest()`),
prompts `persona_dialogue.md`, `persona_turn_dialogue.md`, `dialogue_move.md`, `director_dialogue*.md`, `ledger*.md`,
`directive_closing_dialogue.md`, tests `agent/tests/test_dialogue.py`, evaluation `scripts/dialogue_eval.py` → `docs/eval/dialogue_harness.{md,json}`.

## Known limitations

- **Avoiding persona never addressed:** the other persona is then the only reactive speaker, so "balance" is not possible
  by design. In condition B (peer avoiding) the lead carries most turns.
- **Guard is lexical:** `restate_claim` catches a stance restated with the claim's words; a paraphrase with different
  words still passes. The move-variation rule and the "own position" block address this indirectly.
- **Notes lag the director:** the director reads notes one candidate line behind (the price of running the ledger in parallel).
- **Ledger quality:** it is bounded by a small model; the code checks above remove the most common errors, not all of them.
