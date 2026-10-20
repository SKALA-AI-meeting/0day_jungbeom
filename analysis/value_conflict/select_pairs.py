"""Apply exclusion rules + scoring table (docs/criteria/00-selection-process.md §4) to analyze.py output.

Outputs out/selection.json, out/selection.md and figures. Run after analyze.py:
  uv run --python 3.12 python -I value_conflict/select_pairs.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "out"
plt.rcParams["font.family"] = ["AppleGothic"]
plt.rcParams["axes.unicode_minus"] = False

# Rule X1 (ethics/fairness): Emotionality facets (anxiety, fearfulness, dependence, sentimentality) are close to
# affective / clinical states and show large gender gaps -> never used as a hiring dilemma pole.
EXCLUDED_DOMAINS = {"E"}
MIN_SCORE_FRAC = 0.60  # Rule X3: a chosen pair must reach 60% of the maximum score
WEIGHTS = {"reliability": 1, "dispersion": 2, "balance": 2, "job": 2, "observability": 1, "fairness": 1}

# Literature-based job relevance (0 weak, 1 theoretical/indirect, 2 meta-analytic evidence) and
# text-chat observability (0 hardly, 1 indirect, 2 visible in choices/arguments). Sources in REFS.
FACET_META = {
    "HSinc": (2, 2, "P19"), "HFair": (2, 2, "P20"), "HGree": (1, 1, "P19"), "HMode": (1, 2, "P19"),
    "XExpr": (1, 2, "BM91"), "XSocB": (1, 2, "BM91"), "XSoci": (1, 1, "BM91"), "XLive": (0, 1, "-"),
    "AForg": (1, 2, "P19"), "AGent": (1, 2, "MBS98"), "AFlex": (2, 2, "MBS98"), "APati": (1, 2, "MBS98"),
    "COrga": (2, 1, "BM91,J13"), "CDili": (2, 2, "BM91,J13"), "CPerf": (1, 2, "J13"), "CPrud": (2, 2, "BM91,J13"),
    "OAesA": (0, 0, "-"), "OInqu": (1, 1, "BM91"), "OCrea": (1, 2, "-"), "OUnco": (1, 2, "-"),
}
REFS = {
    "BM91": "Barrick & Mount (1991), Personnel Psychology 44(1) — 성실성이 직군 전반의 성과를 일관되게 예측",
    "J13": "Judge et al. (2013), J. Applied Psychology 98(6), 875–925 — 측면(facet) 수준이 성과 예측에 중요",
    "MBS98": "Mount, Barrick & Stewart (1998), Human Performance 11 — 대인 상호작용·팀 직무에서 원만성·정서안정성",
    "P19": "Pletzer et al. (2019), J. Vocational Behavior 112, 369–383 — 정직-겸손이 직장 일탈 최강 예측요인",
    "P20": "Pletzer et al. (2020), Personality and Individual Differences 152 — 공정성 측면의 일탈 설명력이 6요인 전체에 근접",
}


def pt_rel(o):
    return 2 if o >= 0.80 else 1 if o >= 0.70 else None


def pt_bal(b):
    return 2 if b >= 0.40 else 1 if b >= 0.30 else 0


def pt_fair(d):
    if d is None or (isinstance(d, float) and np.isnan(d)):
        return 1  # no Big5 proxy for Honesty-Humility -> unknown, scored conservatively
    return 2 if d < 0.2 else 1 if d < 0.5 else 0


def main():
    res = json.loads((OUT / "results.json").read_text())
    P = pd.DataFrame(res["pairs"])
    P["excluded_x1"] = P.a.str[0].isin(EXCLUDED_DOMAINS) | P.b.str[0].isin(EXCLUDED_DOMAINS)
    # Rule X2: an ipsative-only trade-off must not be positively associated on raw scores (avoids
    # centring artefacts where two unrelated traits look opposed only after within-person centring).
    pool = P[(P.type == "conflict") | (P.tradeoff & (P.r_ci.str[1] < 0))].copy()
    pool["relation"] = np.where(pool.type == "conflict", "대립(원점수)", "상대적 우선순위 대립(ipsative)")
    n_pool_all = len(pool)
    n_x1 = int(pool.excluded_x1.sum())
    pool = pool[~pool.excluded_x1]

    t1, t2 = pool.sd_zdiff.quantile([1 / 3, 2 / 3])
    rows = []
    for _, p in pool.iterrows():
        rel = pt_rel(p.min_omega)
        if rel is None:
            continue
        ja, oa, _ = FACET_META[p.a]
        jb, ob, _ = FACET_META[p.b]
        s = {
            "reliability": rel,
            "dispersion": 2 if p.sd_zdiff >= t2 else 1 if p.sd_zdiff >= t1 else 0,
            "balance": pt_bal(p.balance),
            "job": round((ja + jb) / 2, 1),
            "observability": round((oa + ob) / 2, 1),
            "fairness": pt_fair(p.fair_gender_d_max),
        }
        total = sum(WEIGHTS[k] * v for k, v in s.items())
        rows.append({**p.to_dict(), **{f"pt_{k}": v for k, v in s.items()}, "score": round(total, 1)})
    S = pd.DataFrame(rows).sort_values(["score", "pt_balance", "r_ipsative"], ascending=[False, False, True])
    max_score = 2 * sum(WEIGHTS.values())

    # controls: facets independent (CI within ±.10) from both poles of a selected pair
    indep = P[P.type == "independent"]
    ind_set = {frozenset((r.a, r.b)) for r in indep.itertuples()}
    facets = list(res["mds"])

    def controls(a, b):
        return [f for f in facets if f[0] not in EXCLUDED_DOMAINS and f not in (a, b)
                and frozenset((a, f)) in ind_set and frozenset((b, f)) in ind_set]

    # Pick top pairs without reusing the same facet twice (keeps concepts distinct).
    chosen, used = [], set()
    for _, r in S.iterrows():
        if r.score < MIN_SCORE_FRAC * max_score:
            break
        if r.a in used or r.b in used:
            continue
        chosen.append({**r.to_dict(), "controls": controls(r.a, r.b)})
        used |= {r.a, r.b}
        if len(chosen) == 6:
            break

    comp = P[(P.type == "complement") & ~P.excluded_x1].sort_values("r", ascending=False).head(10)
    out = {
        "rules": {"X1": "정서성(E) 측면은 딜레마 극으로 쓰지 않음", "X2": "ipsative 대립만 있는 쌍은 원점수 r 95% CI 상한 < 0", "X3": f"점수 ≥ 만점의 {int(MIN_SCORE_FRAC*100)}%", "X4": "한 측면은 한 쌍에만 사용"},
        "pool": {"candidates_before_x1": n_pool_all, "excluded_by_x1": n_x1, "scored": len(S), "max_score": max_score},
        "weights": WEIGHTS, "facet_meta": FACET_META, "refs": REFS,
        "chosen": chosen,
        "top_scored": S.head(20)[["a_ko", "b_ko", "relation", "r", "r_ipsative", "balance", "sd_zdiff", "score"]].to_dict("records"),
        "complements": comp[["a_ko", "b_ko", "r"]].to_dict("records"),
    }
    (OUT / "selection.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
    S.to_csv(OUT / "scored_pairs.csv", index=False)
    figures(res, chosen)
    print(out["pool"])
    print(S.head(15)[["a_ko", "b_ko", "relation", "r", "r_ipsative", "balance", "pt_job", "pt_fairness", "score"]].to_string())
    for c in chosen:
        print(f"{c['a_ko']}↔{c['b_ko']} score={c['score']} {c['relation']} r={c['r']} ips={c['r_ipsative']} bal={c['balance']} A={c['prefer_a']} B={c['prefer_b']} controls={c['controls']}")


def figures(res, chosen):
    facets = list(res["mds"])
    from analyze import FACET_KO  # noqa: E402  (same folder)

    R = pd.read_csv(OUT / "facet_corr_raw.csv", index_col=0)
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(R.to_numpy(), cmap="RdBu_r", vmin=-0.7, vmax=0.7)
    labels = [f"{f[0]}·{FACET_KO[f]}" for f in R.index]
    ax.set_xticks(range(24), labels, rotation=90, fontsize=8)
    ax.set_yticks(range(24), labels, fontsize=8)
    fig.colorbar(im, shrink=0.7, label="r")
    ax.set_title("HEXACO 24측면 상관 (N=21,270)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_corr.png", dpi=150)
    plt.close(fig)

    colors = {"H": "#2563eb", "E": "#94a3b8", "X": "#ea580c", "A": "#16a34a", "C": "#7c3aed", "O": "#db2777"}
    fig, ax = plt.subplots(figsize=(8, 7))
    for f in facets:
        x, y = res["mds"][f]
        ax.scatter(x, y, s=60, color=colors[f[0]], alpha=0.35 if f[0] == "E" else 1)
        ax.annotate(FACET_KO[f], (x, y), fontsize=9, xytext=(4, 3), textcoords="offset points")
    for c in chosen:
        (x1, y1), (x2, y2) = res["mds"][c["a"]], res["mds"][c["b"]]
        ax.plot([x1, x2], [y1, y2], color="#dc2626", lw=1.5, alpha=0.7)
    ax.set_title("상대적 우선순위 지도 (ipsative MDS) — 빨간 선: 선정된 대립 쌍, 회색: 제외(정서성)")
    ax.set_xticks([]), ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(OUT / "fig_mds.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
