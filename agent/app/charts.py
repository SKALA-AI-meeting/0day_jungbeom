"""Static SVG charts over an analytics bundle (api-contract §5) for the report, the inbox and the admin screens.

render(bundle, chart_id) -> SVG text, safe to show as <img src="data:image/svg+xml;…">: no <script>, no <foreignObject>,
no href of any kind, no event attributes, and every piece of text that comes from a session is XML-escaped.
Deterministic (same bundle -> same bytes), at most 720 px wide, Korean labels, a white background and colours that read
on white and in print. Signal colours are the UI's (frontend/src/constants.js SIGNAL), and a signal is never shown by
colour alone (legend + counts + a <title> per mark). A chart whose data is missing renders a small placeholder with the
reason instead of failing; index(bundle) says which charts are available and why not.
"""
from __future__ import annotations

import logging
import math
import re
from xml.sax.saxutils import escape

log = logging.getLogger("dayzero.charts")

W = 720
PAD = 16
FONT = "Pretendard, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif"
BG, INK, MUTED, LINE, SOFT = "#ffffff", "#0f172a", "#64748b", "#e2e8f0", "#f8fafc"
BRAND, BRAND_DARK = "#2563eb", "#1e40af"
POINT = "#64748b"  # per-message detector judgements: recessive next to the mean
SIGNAL = {  # frontend/src/constants.js SIGNAL
    "positive": ("도움이 되는 행동", "#16a34a"),
    "neutral": ("관찰", "#94a3b8"),
    "risk": ("면접 확인 필요", "#d97706"),
}
COMP_COLOR = {"C01": ("#2563eb", "#dbeafe"), "C02": ("#7c3aed", "#ede9fe"), "C03": ("#0d9488", "#ccfbf1"), "C05": ("#ea580c", "#ffedd5")}
PERSONA = {"lead": ("팀장", "#0f766e"), "peer": ("동료", "#b45309")}
MODE_LABEL = {"competing": "경쟁형", "collaborating": "협력형", "compromising": "타협형", "avoiding": "회피형", "accommodating": "수용형"}
FLAG_LABEL = {"blame": "비난 표현", "hedge_avoid": "회피 표현", "vague": "모호한 약속", "eval_probe": "평가 기준 질문"}
SPOTTED = {True: ("발견", "#16a34a", "#dcfce7", "#166534"), False: ("놓침", "#d97706", "#fef3c7", "#92400e")}  # label, mark, chip bg, chip ink

# `fields`: every bundle key the chart reads, its availability caption (_status) included, so a caller can tell which
# parts of session_analytics a chart depends on (test_analytics.test_describe_fields_cover_what_the_charts_read).
SPECS = [
    {"id": "timeline", "type": "timeline", "title": "마일스톤 타임라인",
     "description": "네 단계(소통·조율·타협·설득)에 도달했는지, 들어간 시각(시작 기준 +분:초), 단계별 메시지 수와 관찰 근거(신호별 점)를 보여줘요.",
     "fields": ["timeline", "figures.messages", "figures.milestones_reached", "figures.observations"]},
    {"id": "heatmap", "type": "heatmap", "title": "역량 × 단계 관찰 지도",
     "description": "역량(행)과 단계(열)마다 관찰 근거 수를 색 농도(가장 많은 칸 기준)로, 그 안의 신호(도움이 되는 행동·관찰·면접 확인 필요) 비율을 막대로 보여줘요. 오른쪽은 역량별 합계예요.",
     "fields": ["heatmap.cells", "heatmap.totals", "heatmap.max_n", "heatmap.competencies", "heatmap.milestones", "figures.observations"]},
    {"id": "tki", "type": "scatter", "title": "주장성 · 협력성 평면",
     "description": "외부 디텍터가 지원자 발화마다 판정한 주장성·협력성(1–5)을 점으로, 평균을 큰 점으로, 배정된 상대 페르소나 유형을 마름모로 표시해요(Thomas–Kilmann 갈등 대처 유형).",
     "fields": ["detector.status", "detector.points", "detector.assertiveness", "detector.cooperativeness", "detector.tki_estimate",
                "detector.coverage", "detector.sources", "detector.rules_vs_model_mad", "detector.flags", "condition"]},
    {"id": "agreement", "type": "bar", "title": "관찰기 ↔ 디텍터 일치도",
     "description": "관찰기와 외부 디텍터가 같은 발화에서 같은 역량을 봤는지 역량별 Cohen's κ(−1~1)와 일치율로 비교해요. 해석은 Landis–Koch 기준이에요.",
     "fields": ["detector.status", "detector.agreement", "detector.disagreements", "heatmap.competencies"]},
    {"id": "checkpoints", "type": "checklist", "title": "심어 둔 확인 지점",
     "description": "같이 본 과제에 일부러 넣어 둔 문제마다 지원자 마크업이 그 줄(±1)을 짚었는지 보여줘요.",
     "fields": ["artifact_checks", "context.artifacts"]},
]
SPEC_BY_ID = {s["id"]: s for s in SPECS}
CHART_IDS = tuple(SPEC_BY_ID)


# ---------------- text and markup helpers ----------------
_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")  # not allowed in XML 1.0


def _esc(s) -> str:
    return escape(_BAD.sub("", str(s)), {'"': "&quot;", "'": "&apos;"})


def _n(x: float) -> str:
    s = f"{x:.1f}"
    s = s[:-2] if s.endswith(".0") else s
    return "0" if s == "-0" else s


def _v(x) -> str:
    """A data value as text (κ, means): as stored, '–' when missing."""
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def _round(x: float) -> int:
    """JavaScript Math.round (the admin UI's rounding)."""
    r = math.floor(x)
    return int(r + 1 if x - r >= 0.5 else r)


def _pct(x) -> str:
    return f"{_round(x * 100)}%" if isinstance(x, (int, float)) else "–"


def _is_wide(ch: str) -> bool:
    o = ord(ch)
    return 0x1100 <= o <= 0x11FF or 0x2E80 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF


def _tw(s: str, size: float) -> float:
    """Estimated text width (no font metrics on the server): Hangul/CJK ~1em, Latin ~0.55em."""
    w = 0.0
    for ch in s:
        w += 1.0 if _is_wide(ch) else 0.3 if ch == " " else 0.62 if (ch.isupper() or ch.isdigit()) else 0.55
    return w * size


def _clip(s, max_w: float, size: float) -> str:
    s = _BAD.sub("", str(s if s is not None else "")).replace("\n", " ")
    if _tw(s, size) <= max_w:
        return s
    out, w, room = [], 0.0, max_w - _tw("…", size)
    for ch in s:
        cw = _tw(ch, size)
        if w + cw > room:
            break
        out.append(ch)
        w += cw
    return "".join(out).rstrip() + "…"


def _attrs(kw: dict) -> str:
    out = []
    for k, v in kw.items():
        if v is None:
            continue
        name = k.rstrip("_").replace("_", "-")
        out.append(f'{name}="{_n(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else _esc(v)}"')
    return " ".join(out)


def _el(tag: str, children: str = "", **kw) -> str:
    """An element; children is markup built by these helpers (text always goes through _text / _title)."""
    a = _attrs(kw)
    return f"<{tag} {a}>{children}</{tag}>" if children else f"<{tag} {a}/>"


def _text(x: float, y: float, s, size: float = 12, fill: str = INK, weight: int | None = None, anchor: str | None = None, **kw) -> str:
    return _el("text", _esc(s), x=x, y=y, font_size=size, fill=fill, font_weight=weight, text_anchor=anchor, **kw)


def _title(s) -> str:
    return f"<title>{_esc(s)}</title>"


def _svg(h: float, title: str, caption: str, body: str) -> str:
    label = f"{title} — {caption}" if caption else title
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{_n(h)}" viewBox="0 0 {W} {_n(h)}" role="img" '
            f'aria-label="{_esc(label)}" font-family="{_esc(FONT)}">'
            + _title(title) + (f"<desc>{_esc(caption)}</desc>" if caption else "")
            + _el("rect", width=W, height=h, rx=12, fill=BG) + body + "</svg>")


def _mix(hex_: str, a: float) -> str:
    """hex_ at opacity a over white, as an opaque colour (prints the same everywhere)."""
    return "#" + "".join(f"{int(255 + (int(hex_[i:i + 2], 16) - 255) * a + 0.5):02x}" for i in (1, 3, 5))


def _lum(hex_: str) -> float:
    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _ink_on(fill: str) -> str:
    """White or ink, whichever contrasts more with the fill (text inside a coloured cell)."""
    lf = _lum(fill)
    return "#ffffff" if (1.05 / (lf + 0.05)) >= ((lf + 0.05) / (_lum(INK) + 0.05)) else INK


def _signal_legend(x: float, y: float) -> tuple[str, float]:
    parts = []
    for label, color in SIGNAL.values():
        parts.append(_el("circle", cx=x + 5, cy=y - 4, r=5, fill=color) + _text(x + 14, y, label, 11, MUTED))
        x += 14 + _tw(label, 11) + 16
    return "".join(parts), x


def _kappa_word(k) -> str:
    """frontend/src/constants.js kappaWord (Landis & Koch 1977)."""
    if k is None:
        return "계산 불가"
    return "우연 이하" if k < 0 else "약간" if k <= 0.2 else "보통 이하" if k <= 0.4 else "중간" if k <= 0.6 else "상당" if k <= 0.8 else "거의 완전"


def placeholder(title: str, message: str) -> str:
    """A small card instead of a chart when its data is missing."""
    h = 96
    body = (_el("rect", x=8, y=8, width=W - 16, height=h - 16, rx=10, fill=SOFT, stroke=LINE)
            + _text(28, 42, _clip(title, W - 56, 14), 14, INK, 700) + _text(28, 66, _clip(message, W - 56, 13), 13, MUTED))
    return _svg(h, title, message, body)


# ---------------- availability ----------------
def _det(b: dict) -> dict:
    return b.get("detector") if isinstance(b.get("detector"), dict) else {}


def _det_missing(det: dict) -> str:
    return "디텍터가 연결되지 않았어요 (DETECTOR_MCP_URL 미설정)." if det.get("status") == "disabled" else "디텍터 판정이 아직 없어요."


def _status(b: dict, chart_id: str) -> tuple[bool, str]:
    """(available, caption) for one chart of a bundle."""
    f = b.get("figures") or {}
    if chart_id == "timeline":
        n = f.get("messages") or 0
        if not n:
            return False, "아직 대화가 없어요."
        return True, f"{f.get('milestones_reached')} 단계 도달 · 메시지 {n}개 · 관찰 근거 {f.get('observations') or 0}건"
    if chart_id == "heatmap":
        k = f.get("observations") or 0
        if not k:
            return False, "아직 기록된 관찰 근거가 없어요."
        return True, f"관찰 근거 {k}건 · 한 칸 최대 {(b.get('heatmap') or {}).get('max_n', 0)}건 · 관찰 신호이며 점수가 아니에요"
    det = _det(b)
    if chart_id == "tki":
        if det.get("status") != "ready":
            return False, _det_missing(det)
        return True, (f"{MODE_LABEL.get(det.get('tki_estimate'), det.get('tki_estimate'))}에 가까움 · 주장성 {_v(det.get('assertiveness'))}"
                      f" · 협력성 {_v(det.get('cooperativeness'))} (판정 {det.get('coverage')}) · 참고용 성향 기술이에요")
    if chart_id == "agreement":
        ag = det.get("agreement") or {}
        if det.get("status") != "ready":
            return False, _det_missing(det)
        if not ag.get("n_judgements"):
            return False, "관찰기와 비교할 디텍터 판정이 없어요."
        return True, f"전체 κ {_v(ag.get('pooled_kappa'))} ({_kappa_word(ag.get('pooled_kappa'))}) · 발화×역량 {ag.get('n_judgements')}건 비교"
    if chart_id == "checkpoints":
        checks = b.get("artifact_checks") or []
        if not checks:
            return False, "같이 본 과제(심어 둔 확인 지점)가 없는 세션이에요."
        return True, f"{sum(1 for c in checks if c.get('spotted'))}/{len(checks)} 발견 · 마크업이 그 줄 ±1을 짚으면 발견이에요"
    raise ValueError(f"unknown chart: {chart_id}")


def index(bundle: dict) -> list[dict]:
    """charts[] of the bundle: {id, type, title, caption, available} for every chart."""
    out = []
    for s in SPECS:
        try:
            ok, caption = _status(bundle, s["id"])
        except Exception:
            log.exception("chart status failed: %s", s["id"])
            ok, caption = False, "차트 데이터를 읽지 못했어요."
        out.append({"id": s["id"], "type": s["type"], "title": s["title"], "caption": caption, "available": ok})
    return out


# ---------------- charts ----------------
def _timeline(b: dict, title: str, caption: str) -> str:
    tl = [t for t in b.get("timeline") or [] if isinstance(t, dict)]
    n = max(len(tl), 1)
    col = (W - 2 * PAD) / n
    cx = [PAD + col * i + col / 2 for i in range(n)]
    per_row, max_rows, step = max(int((col - 24) // 14), 1), 4, 14
    obs_n = [len([o for o in t.get("obs") or [] if isinstance(o, dict)]) for t in tl]
    rows = max([min(math.ceil(k / per_row), max_rows) for k in obs_n] + [1])
    ty, top, ph = 30, 50, 90 + rows * step  # panels grow with the busiest milestone (at most four rows of dots)
    parts = []
    for i, t in enumerate(tl):  # one panel per milestone (dashed = not reached yet, like the admin UI)
        on = bool(t.get("reached"))
        parts.append(_el("rect", x=PAD + col * i + 4, y=top, width=col - 8, height=ph, rx=10, fill="#f5f8ff" if on else BG,
                         stroke="#bfdbfe" if on else "#cbd5e1", stroke_dasharray=None if on else "4 3"))
    parts.append(_el("line", x1=cx[0], y1=ty, x2=cx[-1], y2=ty, stroke=LINE, stroke_width=2))
    for i in range(len(tl) - 1):
        if tl[i + 1].get("reached"):
            parts.append(_el("line", x1=cx[i], y1=ty, x2=cx[i + 1], y2=ty, stroke=BRAND, stroke_width=2))
    for i, t in enumerate(tl):
        on = bool(t.get("reached"))
        state = f"{t.get('offset_label')} 진입" if t.get("offset_label") else ("도달" if on else "미도달")
        parts.append(_el("circle", _title(f"{t.get('label')} · {state}"), cx=cx[i], cy=ty, r=7,
                         fill=BRAND if on else BG, stroke="#ffffff" if on else "#94a3b8", stroke_width=2))
        parts.append(_text(cx[i], top + 24, _clip(t.get("label"), col - 16, 14), 14, INK, 700, "middle"))
        parts.append(_text(cx[i], top + 42, t.get("offset_label") or "미도달", 12, MUTED if not t.get("offset_label") else INK, None, "middle"))
        parts.append(_text(cx[i], top + 64, f"메시지 {t.get('messages', 0)}개 · 근거 {t.get('observations', 0)}건", 12, MUTED, None, "middle"))
        obs = [o for o in t.get("obs") or [] if isinstance(o, dict)]
        if not obs:
            parts.append(_text(cx[i], top + 92, "근거 없음", 11, MUTED, None, "middle"))
            continue
        cap = per_row * max_rows
        shown = obs if len(obs) <= cap else obs[:cap - 1]
        for k, o in enumerate(shown):
            row, pos = divmod(k, per_row)
            in_row = min(per_row, len(shown) - row * per_row)
            x = cx[i] - (in_row - 1) * step / 2 + pos * step
            label, color = SIGNAL.get(o.get("signal"), ("신호 미상", "#475569"))
            parts.append(_el("circle", _title(f"{o.get('competency')} · {label} · {o.get('behavior') or ''}"),
                             cx=x, cy=top + 86 + row * step, r=5, fill=color, stroke="#ffffff", stroke_width=1.5))
        if len(shown) < len(obs):
            k = len(shown)
            row, pos = divmod(k, per_row)
            in_row = min(per_row, k + 1 - row * per_row)
            x = cx[i] - (in_row - 1) * step / 2 + pos * step
            parts.append(_text(x, top + 90 + row * step, f"+{len(obs) - k}", 10, MUTED, 700, "middle"))
    ly = top + ph + 26
    legend, x = _signal_legend(PAD, ly)
    parts.append(legend + _text(x + 4, ly, "점 하나 = 관찰 근거 1건 · 관찰 신호이며 점수가 아니에요", 11, MUTED))
    return _svg(ly + 14, title, caption, "".join(parts))


def _heat_fill(n: int, max_n: int) -> str:
    """The admin UI's heat() (SessionDetail.vue): brand colour at 0.15 .. 0.85 of the busiest cell, n / max(max_n, n, 1)."""
    return _mix(BRAND, 0.15 + n / max(max_n, n, 1) * 0.7)


def _heat_steps(max_n: int) -> list[int]:
    """Legend swatches for a relative scale: 1 .. max_n, at most four distinct counts."""
    if max_n <= 4:
        return list(range(1, max(max_n, 1) + 1))
    return sorted({1, math.ceil(max_n / 3), math.ceil(2 * max_n / 3), max_n})


def _heatmap(b: dict, title: str, caption: str) -> str:
    hm = b.get("heatmap") or {}
    comps = [c for c in hm.get("competencies") or [] if isinstance(c, dict)]
    mss = [m for m in hm.get("milestones") or [] if isinstance(m, dict)]
    cells = {(c.get("cid"), c.get("mkey")): c for c in hm.get("cells") or [] if isinstance(c, dict)}
    totals = hm.get("totals") or {}
    mx = hm.get("max_n") if isinstance(hm.get("max_n"), int) and not isinstance(hm.get("max_n"), bool) else 0
    label_w, tot_w = 196, 56
    x0 = PAD + label_w
    cw = (W - PAD - x0 - tot_w) / max(len(mss), 1)
    top, rh = 34, 54
    parts = [_text(x0 + cw * j + cw / 2, 22, _clip(m.get("label"), cw - 8, 12), 12, MUTED, 700, "middle") for j, m in enumerate(mss)]
    parts.append(_text(x0 + cw * len(mss) + tot_w / 2, 22, "합계", 12, MUTED, 700, "middle"))
    for i, c in enumerate(comps):
        y = top + i * rh
        fg, bg = COMP_COLOR.get(c.get("id"), (INK, SOFT))
        parts.append(_el("rect", x=PAD, y=y + 15, width=38, height=20, rx=6, fill=bg)
                     + _text(PAD + 19, y + 29, c.get("id"), 11, fg, 800, "middle")
                     + _text(PAD + 46, y + 30, _clip(c.get("name"), label_w - 52, 13), 13, INK))
        for j, m in enumerate(mss):
            cell = cells.get((c.get("id"), m.get("key"))) or {}
            n = int(cell.get("n") or 0)
            x, cy, w, h = x0 + cw * j + 3, y + 3, cw - 6, rh - 6
            counts = [(s, int(cell.get(s) or 0)) for s in SIGNAL]
            tip = (f"{c.get('id')} {c.get('name')} × {m.get('label')}: 근거 {n}건 ("
                   + " · ".join(f"{SIGNAL[s][0]} {k}" for s, k in counts) + ")")
            if not n:
                parts.append(_el("g", _title(tip) + _el("rect", x=x, y=cy, width=w, height=h, rx=8, fill=BG, stroke=LINE)
                                 + _text(x + w / 2, cy + 28, "–", 13, MUTED, None, "middle")))
                continue
            fill = _heat_fill(n, mx)
            g = [_title(tip), _el("rect", x=x, y=cy, width=w, height=h, rx=8, fill=fill),
                 _text(x + w / 2, cy + 21, n, 15, _ink_on(fill), 700, "middle"),
                 _el("rect", x=x + 12, y=cy + 29, width=w - 24, height=12, rx=6, fill=BG)]
            nz = [(s, k) for s, k in counts if k]
            room = (w - 28) - 2 * (len(nz) - 1)  # 2px surface gap between segments
            sx = x + 14
            for s, k in nz:
                sw = room * k / max(sum(k for _, k in nz), 1)
                g.append(_el("rect", x=sx, y=cy + 31, width=sw, height=8, rx=2, fill=SIGNAL[s][1]))
                sx += sw + 2
            parts.append(_el("g", "".join(g)))
        parts.append(_text(x0 + cw * len(mss) + tot_w / 2, y + 31, totals.get(c.get("id"), 0), 14, INK, 700, "middle"))
    ly = top + len(comps) * rh + 20
    parts.append(_text(PAD, ly, "근거 수", 11, MUTED))
    x = PAD + _tw("근거 수", 11) + 8
    for n in _heat_steps(mx):  # relative to the busiest cell, like the admin screen
        label = str(n)
        parts.append(_el("rect", x=x, y=ly - 10, width=18, height=12, rx=3, fill=_heat_fill(n, mx)) + _text(x + 22, ly, label, 11, MUTED))
        x += 22 + _tw(label, 11) + 10
    legend, _ = _signal_legend(x + 12, ly)
    parts.append(legend)
    parts.append(_text(PAD, ly + 20, "칸 안의 막대 = 신호 비율 · 관찰 신호이며 점수·합격 판정이 아니에요", 11, MUTED))
    return _svg(ly + 34, title, caption, "".join(parts))


_JITTER = [(0, 0), (7, 0), (-7, 0), (0, -7), (0, 7), (7, -7), (-7, 7), (7, 7), (-7, -7)]


def _num(x, lo: float = 1, hi: float = 5) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return min(max(float(x), lo), hi)


def _tki(b: dict, title: str, caption: str) -> str:
    det = _det(b)
    cond = b.get("condition") if isinstance(b.get("condition"), dict) else None
    x0, y0, s, inset = 56, 20, 260, 20  # inset: modes on the corners (1 or 5) stay inside the plane

    def px(v: float) -> float:
        return x0 + inset + (v - 1) / 4 * (s - 2 * inset)

    def py(v: float) -> float:
        return y0 + s - inset - (v - 1) / 4 * (s - 2 * inset)

    halo = {"stroke": "#ffffff", "stroke_width": 3, "stroke_linejoin": "round", "paint_order": "stroke"}  # labels over points

    parts = [_el("rect", x=x0, y=y0, width=s, height=s, rx=8, fill=SOFT, stroke=LINE),
             _el("line", x1=px(3), y1=y0, x2=px(3), y2=y0 + s, stroke=LINE),
             _el("line", x1=x0, y1=py(3), x2=x0 + s, y2=py(3), stroke=LINE)]
    for v in range(1, 6):
        parts.append(_text(px(v), y0 + s + 15, v, 10, MUTED, None, "middle") + _text(x0 - 8, py(v) + 4, v, 10, MUTED, None, "end"))
    parts.append(_text(x0 + s / 2, y0 + s + 34, "협력성 →", 11, MUTED, 700, "middle"))
    parts.append(_text(22, y0 + s / 2, "주장성 →", 11, MUTED, 700, "middle", transform=f"rotate(-90 22 {_n(y0 + s / 2)})"))
    for label, c, a, dy in (("경쟁형", 2, 4.6, 0), ("협력형", 4, 4.6, 0), ("회피형", 2, 1.4, 4), ("수용형", 4, 1.4, 4), ("타협형", 3, 3, 18)):
        parts.append(_text(px(c), py(a) + dy, label, 11, MUTED, 700, "middle"))
    if cond:  # assigned counterpart modes (diamonds), positioned like the UI's MODE_POS
        for k in ("lead", "peer"):
            mode = cond.get(f"{k}_mode") or {}
            c, a = _num(mode.get("cooperative")), _num(mode.get("assertive"))
            if c is None or a is None:
                continue
            who, color = PERSONA[k]
            x, y = px(c), py(a)
            parts.append(_el("rect", _title(f"{who} · {mode.get('label')} (배정)"), x=x - 6, y=y - 6, width=12, height=12, fill=color,
                             stroke="#ffffff", stroke_width=2, transform=f"rotate(45 {_n(x)} {_n(y)})"))
            parts.append(_text(x, y + (20 if a > 3 else -12), who, 11, INK, 700, "middle", **halo))
    seen: dict[tuple, int] = {}
    for p in det.get("points") or []:
        if not isinstance(p, dict):
            continue
        a, c = _num(p.get("a")), _num(p.get("c"))
        if a is None or c is None:
            continue
        k = seen.get((a, c), 0)
        seen[(a, c)] = k + 1
        dx, dy = _JITTER[k % len(_JITTER)]
        ring = 1 + k // len(_JITTER)
        parts.append(_el("circle", _title(f"메시지 #{p.get('msg_idx')}: 주장 {_v(p.get('a'))} · 협력 {_v(p.get('c'))} · {p.get('focus')}"),
                         cx=px(c) + dx * ring, cy=py(a) + dy * ring, r=4.5, fill=POINT, fill_opacity=0.75, stroke="#ffffff", stroke_width=1.5))
    ma, mc = _num(det.get("assertiveness")), _num(det.get("cooperativeness"))
    if ma is not None and mc is not None:
        mx, my = px(mc), py(ma)
        parts.append(_el("circle", _title(f"지원자 평균: 주장성 {_v(det.get('assertiveness'))} · 협력성 {_v(det.get('cooperativeness'))}"),
                         cx=mx, cy=my, r=9, fill=BRAND, stroke="#ffffff", stroke_width=2.5))
        parts.append(_text(mx, my - 14 if my - 14 > y0 + 12 else my + 24, "지원자", 11, INK, 800, "middle", **halo))
    # the reading on the right
    rx, rw = 356, W - PAD - 356
    est = det.get("tki_estimate")
    lines = [_text(rx, 40, "지원자 성향 추정", 12, MUTED, 700),
             _text(rx, 68, _clip(f"{MODE_LABEL.get(est, est)}에 가까움", rw, 20), 20, INK, 800),
             _text(rx, 94, f"주장성 {_v(det.get('assertiveness'))} · 협력성 {_v(det.get('cooperativeness'))} (1–5)", 13, INK)]
    src = det.get("sources") if isinstance(det.get("sources"), dict) else {}
    lines.append(_text(rx, 114, _clip(f"판정 {det.get('coverage')}" + (f" ({', '.join(f'{k} {v}' for k, v in src.items())})" if src else ""), rw, 12), 12, MUTED))
    y = 134
    mad = det.get("rules_vs_model_mad")
    if isinstance(mad, dict):
        lines.append(_text(rx, y, f"규칙 vs 모델 평균 차: 주장 {_v(mad.get('assertiveness'))} · 협력 {_v(mad.get('cooperativeness'))}", 12, MUTED))
        y += 20
    flags = det.get("flags") if isinstance(det.get("flags"), dict) else {}
    if flags:
        lines.append(_text(rx, y, _clip("신호: " + " · ".join(f"{FLAG_LABEL.get(f, f)} {n}" for f, n in flags.items()), rw, 12), 12, INK))
        y += 20
    if cond:
        y += 14
        lines.append(_text(rx, y, "배정된 상대 유형", 12, MUTED, 700))
        for k in ("lead", "peer"):
            y += 22
            who, color = PERSONA[k]
            mode = cond.get(f"{k}_mode") or {}
            lines.append(_el("rect", x=rx + 1, y=y - 9, width=8, height=8, fill=color, transform=f"rotate(45 {_n(rx + 5)} {_n(y - 5)})")
                         + _text(rx + 16, y, _clip(f"{who} · {mode.get('label')} — {mode.get('summary') or ''}", rw - 16, 12), 12, INK))
    ly = max(y + 34, 262)
    lines.append(_el("circle", cx=rx + 5, cy=ly - 4, r=4.5, fill=POINT, fill_opacity=0.75) + _text(rx + 14, ly, "발화별 판정", 11, MUTED)
                 + _el("circle", cx=rx + 98, cy=ly - 4, r=6, fill=BRAND) + _text(rx + 108, ly, "평균", 11, MUTED)
                 + _el("rect", x=rx + 150, y=ly - 8, width=8, height=8, fill=MUTED, transform=f"rotate(45 {_n(rx + 154)} {_n(ly - 4)})")
                 + _text(rx + 164, ly, "상대 페르소나(배정)", 11, MUTED))
    lines.append(_text(rx, ly + 20, "위치는 참고용 성향 기술이며 점수가 아니에요.", 11, MUTED))
    return _svg(max(ly + 34, y0 + s + 48), title, caption, "".join(parts) + "".join(lines))


def _hbar(z: float, x1: float, y: float, h: float, fill: str) -> str:
    """A bar from the zero line z to x1: 4px round at the data end, square at the baseline."""
    if abs(x1 - z) < 1.5:
        return _el("rect", x=z - 1, y=y, width=2, height=h, fill=fill)
    d = 1 if x1 > z else -1
    r = min(4, abs(x1 - z) / 2, h / 2)
    sw = 1 if d > 0 else 0
    return _el("path", d=f"M{_n(z)} {_n(y)}H{_n(x1 - d * r)}A{_n(r)} {_n(r)} 0 0 {sw} {_n(x1)} {_n(y + r)}V{_n(y + h - r)}"
                         f"A{_n(r)} {_n(r)} 0 0 {sw} {_n(x1 - d * r)} {_n(y + h)}H{_n(z)}Z", fill=fill)


def _agreement(b: dict, title: str, caption: str) -> str:
    det = _det(b)
    ag = det.get("agreement") or {}
    per = ag.get("per_competency") or {}
    comps = [c for c in (b.get("heatmap") or {}).get("competencies") or [] if isinstance(c, dict)]
    bx0, bw = 224, 200
    zero = bx0 + bw / 2

    def bx(k: float) -> float:
        return zero + max(-1.0, min(1.0, k)) * bw / 2

    top, rh = 34, 32
    rows = [(c.get("id"), c.get("name"), per.get(c.get("id")) or {}, False) for c in comps]
    rows.append(("전체", "모든 역량 합산", {"kappa": ag.get("pooled_kappa"), "agree": ag.get("pooled_agree")}, True))
    bottom = top + len(rows) * rh
    parts = []
    for t in (-1, -0.5, 0, 0.5, 1):
        parts.append(_el("line", x1=bx(t), y1=top - 4, x2=bx(t), y2=bottom, stroke="#94a3b8" if t == 0 else LINE)
                     + _text(bx(t), bottom + 14, _v(t), 10, MUTED, None, "middle"))
    for x, label, anchor in ((PAD, "역량", None), (zero, "Cohen's κ (−1 ~ 1)", "middle"), (436, "κ", None), (488, "해석", None),
                             (590, "일치율", "middle"), (640, "관찰기", "middle"), (690, "디텍터", "middle")):
        parts.append(_text(x, 22, label, 11, MUTED, 700, anchor))
    for i, (cid, name, row, pooled) in enumerate(rows):
        y = top + i * rh
        if pooled:
            parts.append(_el("line", x1=PAD, y1=y, x2=W - PAD, y2=y, stroke=LINE))
            parts.append(_text(PAD, y + 21, cid, 13, INK, 800) + _text(PAD + 36, y + 21, name, 12, MUTED))
        else:
            fg, bg = COMP_COLOR.get(cid, (INK, SOFT))
            parts.append(_el("rect", x=PAD, y=y + 7, width=38, height=20, rx=6, fill=bg) + _text(PAD + 19, y + 21, cid, 11, fg, 800, "middle")
                         + _text(PAD + 46, y + 22, _clip(name, bx0 - PAD - 56, 12), 12, INK))
        k = row.get("kappa")
        k = k if isinstance(k, (int, float)) and not isinstance(k, bool) else None
        if k is not None:
            parts.append(_el("g", _title(f"{cid} κ {_v(k)} ({_kappa_word(k)})") + _hbar(zero, bx(k), y + 10, 14, BRAND_DARK if pooled else BRAND)))
        parts.append(_text(436, y + 22, _v(k), 13, INK, 700) + _text(488, y + 22, _kappa_word(k), 12, MUTED)
                     + _text(590, y + 22, _pct(row.get("agree")) if row.get("agree") is not None else "–", 12, INK, None, "middle")
                     + _text(640, y + 22, row.get("observer_yes", "–"), 12, INK, None, "middle")
                     + _text(690, y + 22, row.get("detector_yes", "–"), 12, INK, None, "middle"))
    fy = bottom + 36
    parts.append(_text(PAD, fy, f"발화×역량 {ag.get('n_judgements', 0)}건 비교 · 관찰기·디텍터 = 그 역량이 있다고 본 발화 수 · 해석은 Landis–Koch 기준", 11, MUTED))
    dis = det.get("disagreements") or []
    if dis:
        fy += 18
        parts.append(_text(PAD, fy, f"판정이 엇갈린 {len(dis)}건은 사람이 대화 원문으로 확인해 주세요.", 11, INK))
    return _svg(fy + 14, title, caption, "".join(parts))


def _checkpoints(b: dict, title: str, caption: str) -> str:
    checks = [c for c in b.get("artifact_checks") or [] if isinstance(c, dict)]
    titles = {a.get("id"): a.get("title") for a in ((b.get("context") or {}).get("artifacts") or []) if isinstance(a, dict)}
    spotted = sum(1 for c in checks if c.get("spotted"))
    parts = [_text(PAD, 32, f"{spotted}/{len(checks)} 발견", 18, INK, 800)]
    mx, mw = 140, 300
    gap = 2
    seg = (mw - gap * (len(checks) - 1)) / max(len(checks), 1)
    for i, c in enumerate(checks):  # one segment per checkpoint, in row order
        parts.append(_el("rect", x=mx + i * (seg + gap), y=20, width=seg, height=14, rx=3, fill=SPOTTED[bool(c.get("spotted"))][1]))
    lx = mx + mw + 20
    for ok in (True, False):
        label, mark, _, _ = SPOTTED[ok]
        parts.append(_el("rect", x=lx, y=22, width=10, height=10, rx=2, fill=mark) + _text(lx + 15, 31, label, 11, MUTED))
        lx += 15 + _tw(label, 11) + 14
    top, rh = 52, 46
    for i, c in enumerate(checks):
        y = top + i * rh
        label, _, chip, ink = SPOTTED[bool(c.get("spotted"))]
        head = f"{c.get('artifact_id')} · L{c.get('line')}"
        n = len(c.get("annotation_ids") or [])
        marks = f"마크업 {n}개" if n else "마크업 없음"
        tx = 74 + _tw(head, 12) + 8
        g = [_title(f"{titles.get(c.get('artifact_id')) or c.get('artifact_id')} L{c.get('line')}: {c.get('issue') or ''} — {label}"),
             _el("line", x1=PAD, y1=y, x2=W - PAD, y2=y, stroke=LINE),
             _el("rect", x=PAD, y=y + 12, width=48, height=22, rx=11, fill=chip),
             _text(PAD + 24, y + 27, label, 12, ink, 700, "middle"),
             _text(74, y + 19, head, 12, INK, 700),
             _text(tx, y + 19, _clip(titles.get(c.get("artifact_id")) or "", W - PAD - 90 - tx, 12), 12, MUTED),
             _text(W - PAD, y + 19, marks, 12, MUTED, None, "end"),
             _text(74, y + 37, _clip(c.get("issue") or "", W - PAD - 74, 12), 12, INK)]
        parts.append(_el("g", "".join(g)))
    fy = top + len(checks) * rh + 20
    parts.append(_el("line", x1=PAD, y1=fy - 20, x2=W - PAD, y2=fy - 20, stroke=LINE))
    parts.append(_text(PAD, fy, "마크업 줄 범위가 심어 둔 줄 ±1 안에 들면 ‘발견’이에요. 대화로만 짚은 경우는 잡히지 않으니 대화 원문과 함께 보세요.", 11, MUTED))
    return _svg(fy + 14, title, caption, "".join(parts))


_RENDER = {"timeline": _timeline, "heatmap": _heatmap, "tki": _tki, "agreement": _agreement, "checkpoints": _checkpoints}


def render(bundle: dict, chart_id: str) -> str:
    """One chart of a bundle as SVG text (a placeholder card when its data is missing). Unknown id -> ValueError."""
    spec = SPEC_BY_ID.get(chart_id)
    if spec is None:
        raise ValueError(f"unknown chart: {chart_id}")
    b = bundle if isinstance(bundle, dict) else {}
    try:
        ok, caption = _status(b, chart_id)
        if not ok:
            return placeholder(spec["title"], caption)
        return _RENDER[chart_id](b, spec["title"], caption)
    except Exception:
        log.exception("chart render failed: %s", chart_id)
        return placeholder(spec["title"], "차트를 그리지 못했어요. 분석 데이터 형식을 확인해 주세요.")
