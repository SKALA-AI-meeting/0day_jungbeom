"""Data-driven selection of conflict / complementary / independent trait pairs.

Data (openpsychometrics.org/_rawdata, not committed; put under data/raw/):
  D1 HEXACO  : IPIP HEXACO-equivalent, 240 items, 24 facets, 7-pt, N=22,786
  D2 BIG5    : IPIP Big-Five 50 items, 5-pt, N=19,719 (has gender / age -> fairness)

Pre-registered rules live in docs/criteria/00-selection-process.md; thresholds are constants below.
Run:  uv run --python 3.12 python -I value_conflict/analyze.py ../data/raw   (from analysis/)
"""
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from factor_analyzer import FactorAnalyzer
from scipy.optimize import linear_sum_assignment
from sklearn.manifold import MDS

RNG = np.random.default_rng(20261020)
R_CONFLICT, R_COMPLEMENT, R_INDEP = -0.20, 0.30, 0.10
OMEGA_MIN = 0.70
LONGSTRING_FRAC = 0.50
PREF_GAP = 0.5  # raw scale points: "clearly prefers A over B"
N_BOOT = 1000

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

FACET_KO = {
    "HSinc": "진실성", "HFair": "공정성", "HGree": "탐욕 회피", "HMode": "겸손",
    "EFear": "두려움", "EAnxi": "불안", "EDepe": "의존성", "ESent": "감상성",
    "XExpr": "사회적 표현", "XSocB": "사회적 대담성", "XSoci": "사교성", "XLive": "활력",
    "AForg": "용서", "AGent": "온화함", "AFlex": "유연성", "APati": "인내",
    "COrga": "조직화", "CDili": "근면", "CPerf": "완벽주의", "CPrud": "신중함",
    "OAesA": "심미성", "OInqu": "탐구심", "OCrea": "창의성", "OUnco": "비관습성",
}
DOMAIN_KO = {"H": "정직-겸손", "E": "정서성", "X": "외향성", "A": "원만성", "C": "성실성", "O": "개방성"}
BIG5_KEY = {  # standard IPIP-50 scoring key, used ONLY to validate empirical keying
    "E": [1, -1, 1, -1, 1, -1, 1, -1, 1, -1],
    "N": [1, -1, 1, -1, 1, 1, 1, 1, 1, 1],
    "A": [-1, 1, -1, 1, -1, 1, -1, 1, 1, 1],
    "C": [1, -1, 1, -1, 1, -1, 1, -1, 1, 1],
    "O": [1, -1, 1, -1, 1, -1, 1, 1, 1, 1],
}


def longstring(arr: np.ndarray) -> np.ndarray:
    """Max run of identical consecutive answers per row."""
    same = arr[:, 1:] == arr[:, :-1]
    best = np.zeros(len(arr), int)
    cur = np.zeros(len(arr), int)
    for j in range(same.shape[1]):
        cur = np.where(same[:, j], cur + 1, 0)
        best = np.maximum(best, cur)
    return best + 1


def empirical_keys(df: pd.DataFrame, cols: list[str], anchor: str) -> dict[str, int]:
    """Sign of first principal component loading, oriented so the anchor item is +."""
    c = np.corrcoef(df[cols].to_numpy(float), rowvar=False)
    w, v = np.linalg.eigh(c)
    pc = v[:, -1]
    if pc[cols.index(anchor)] < 0:
        pc = -pc
    return {col: (1 if pc[i] >= 0 else -1) for i, col in enumerate(cols)}


def score(df, cols, keys, top):
    x = df[cols].to_numpy(float)
    k = np.array([keys[c] for c in cols])
    x = np.where(k > 0, x, top + 1 - x)
    return x


def alpha(x: np.ndarray) -> float:
    k = x.shape[1]
    return float(k / (k - 1) * (1 - x.var(axis=0, ddof=1).sum() / x.sum(axis=1).var(ddof=1)))


def omega(x: np.ndarray) -> float:
    fa = FactorAnalyzer(n_factors=1, rotation=None, method="minres")
    fa.fit(x)
    lam = np.abs(fa.loadings_[:, 0])
    psi = 1 - lam**2
    return float(lam.sum() ** 2 / (lam.sum() ** 2 + psi.sum()))


def parallel_analysis(x: np.ndarray, iters: int = 50) -> tuple[int, list[float]]:
    n, p = x.shape
    real = np.sort(np.linalg.eigvalsh(np.corrcoef(x, rowvar=False)))[::-1]
    sims = np.array([np.sort(np.linalg.eigvalsh(np.corrcoef(RNG.standard_normal((n, p)), rowvar=False)))[::-1] for _ in range(iters)])
    thr = np.percentile(sims, 95, axis=0)
    k = int(np.argmax(real <= thr)) if (real <= thr).any() else p
    return k, real[:10].round(3).tolist()


def tucker(loadings: np.ndarray, target: np.ndarray) -> tuple[list[float], list[int]]:
    """Congruence per target column after optimal factor matching (sign-free)."""
    num = loadings.T @ target
    den = np.sqrt((loadings**2).sum(0))[:, None] * np.sqrt((target**2).sum(0))[None, :]
    phi = num / den
    r, c = linear_sum_assignment(-np.abs(phi))
    order = np.argsort(c)
    return [float(abs(phi[r[i], c[i]])) for i in order], [int(r[i]) for i in order]


def boot_corr(z: np.ndarray, n_boot: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(z)
    lo_hi = np.empty((n_boot, z.shape[1], z.shape[1]))
    for b in range(n_boot):
        idx = RNG.integers(0, n, n)
        lo_hi[b] = np.corrcoef(z[idx], rowvar=False)
    return np.percentile(lo_hi, 2.5, axis=0), np.percentile(lo_hi, 97.5, axis=0)


def cohen_d(a, b):
    sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    return float((a.mean() - b.mean()) / sp)


def main(raw: Path) -> None:
    report: dict = {"thresholds": dict(r_conflict=R_CONFLICT, r_complement=R_COMPLEMENT, r_indep=R_INDEP, omega_min=OMEGA_MIN, longstring_frac=LONGSTRING_FRAC, pref_gap=PREF_GAP, n_boot=N_BOOT)}

    # ---------------- D2 BIG5: cleaning + keying validation + fairness ----------------
    b5 = pd.read_csv(raw / "big5/BIG5/data.csv", sep="\t")
    b5_items = [f"{d}{i}" for d in "ENACO" for i in range(1, 11)]
    n0 = len(b5)
    b5 = b5[(b5[b5_items] > 0).all(axis=1)]
    order = [f"{d}{i}" for i in range(1, 11) for d in "ENACO"]  # presentation order per codebook
    b5 = b5[longstring(b5[order].to_numpy()) < LONGSTRING_FRAC * 50]
    b5 = b5[(b5.age >= 13) & (b5.age <= 90)]
    anchors = {"E": "E1", "N": "N1", "A": "A2", "C": "C1", "O": "O1"}
    agree, total, b5_scores = 0, 0, {}
    for d in "ENACO":
        cols = [f"{d}{i}" for i in range(1, 11)]
        k = empirical_keys(b5, cols, anchors[d])
        agree += sum(k[c] == BIG5_KEY[d][i] for i, c in enumerate(cols))
        total += 10
        b5_scores[d] = score(b5, cols, {c: BIG5_KEY[d][i] for i, c in enumerate(cols)}, 5).mean(axis=1)
    b5s = pd.DataFrame(b5_scores, index=b5.index)
    fair = {}
    for d in "ENACO":
        m, f = b5s[d][b5.gender == 1], b5s[d][b5.gender == 2]
        fair[d] = {"gender_d": round(cohen_d(f.to_numpy(), m.to_numpy()), 3), "age_r": round(float(np.corrcoef(b5s[d], b5.age)[0, 1]), 3)}
    pa_k, _ = parallel_analysis(score(b5, b5_items, {c: BIG5_KEY[c[0]][int(c[1:]) - 1] for c in b5_items}, 5))
    fa5 = FactorAnalyzer(n_factors=5, rotation="oblimin", method="minres").fit(b5[b5_items].to_numpy(float))
    target5 = np.zeros((50, 5))
    for i, c in enumerate(b5_items):
        target5[i, "ENACO".index(c[0])] = BIG5_KEY[c[0]][int(c[1:]) - 1]
    phi5, _ = tucker(fa5.loadings_, target5)
    report["big5"] = {
        "n_raw": n0, "n_clean": len(b5), "keying_agreement": f"{agree}/{total}",
        "parallel_analysis_factors": pa_k, "tucker_phi": dict(zip("ENACO", np.round(phi5, 3).tolist())),
        "fairness": fair, "domain_corr": b5s.corr().round(3).to_dict(),
    }

    # ---------------- D1 HEXACO ----------------
    hx = pd.read_csv(raw / "hexaco/HEXACO/data.csv", sep="\t", low_memory=False)
    items = [c for c in hx.columns if c not in ("V1", "V2", "country", "elapse")]
    n0 = len(hx)
    steps = {"raw": n0}
    hx = hx[(hx[items] > 0).all(axis=1)]
    steps["complete"] = len(hx)
    hx = hx[(hx.V1 >= 5) & (hx.V2 >= 5)]
    steps["validity_items>=5"] = len(hx)
    hx["elapse"] = pd.to_numeric(hx.elapse, errors="coerce")
    hx = hx[hx.elapse > 0]
    hx = hx[hx.elapse >= hx.elapse.quantile(0.01)]
    steps["elapse>=p1"] = len(hx)
    codebook_order = [ln.split()[0] for ln in (raw / "hexaco/HEXACO/codebook.txt").read_text().splitlines() if ln[:1].isupper() and ln.split()[0] in items]
    hx = hx[longstring(hx[codebook_order].to_numpy()) < LONGSTRING_FRAC * 240]
    steps["longstring<50%"] = len(hx)

    facets = list(FACET_KO)
    keys, fscore, rel = {}, {}, {}
    for f in facets:
        cols = [f"{f}{i}" for i in range(1, 11)]
        keys.update(empirical_keys(hx, cols, f"{f}1"))
        x = score(hx, cols, keys, 7)
        fscore[f] = x.mean(axis=1)
        rel[f] = {"alpha": round(alpha(x), 3), "omega": round(omega(x), 3), "n_reversed": int(sum(keys[c] < 0 for c in cols))}
    F = pd.DataFrame(fscore, index=hx.index)
    Z = (F - F.mean()) / F.std(ddof=1)

    pa_k, eig = parallel_analysis(Z.to_numpy())
    fa6 = FactorAnalyzer(n_factors=6, rotation="oblimin", method="minres").fit(Z.to_numpy())
    target6 = np.zeros((24, 6))
    dom_order = list("HEXACO")
    for i, f in enumerate(facets):
        target6[i, dom_order.index(f[0])] = 1
    phi6, match = tucker(fa6.loadings_, target6)

    # facet relations: raw and ipsative (within-person centred z-profile = relative priority)
    R = Z.corr().to_numpy()
    lo, hi = boot_corr(Z.to_numpy(), N_BOOT)
    Zi = Z.sub(Z.mean(axis=1), axis=0)
    Ri = Zi.corr().to_numpy()
    lo_i, hi_i = boot_corr(Zi.to_numpy(), N_BOOT)
    ips_baseline = -1 / (len(facets) - 1)

    # cultural invariance: East Asia vs US facet-correlation patterns
    ea = {"KR", "JP", "CN", "TW", "HK", "SG", "MY", "TH", "VN", "PH", "ID"}
    cty = hx.country.astype(str)
    inv = {"n_us": int((cty == "US").sum()), "n_east_asia": int(cty.isin(ea).sum()), "n_kr": int((cty == "KR").sum())}
    tri = np.triu_indices(24, 1)
    if inv["n_east_asia"] >= 300:
        r_us = Z[cty == "US"].corr().to_numpy()[tri]
        r_ea = Z[cty.isin(ea)].corr().to_numpy()[tri]
        inv["pattern_r_us_vs_ea"] = round(float(np.corrcoef(r_us, r_ea)[0, 1]), 3)
        inv["mean_abs_diff"] = round(float(np.abs(r_us - r_ea).mean()), 3)
        inv["_r_ea"] = r_ea

    # MDS map on ipsative correlations
    dist = np.clip(1 - Ri, 0, None)
    np.fill_diagonal(dist, 0)
    xy = MDS(n_components=2, dissimilarity="precomputed", random_state=0, n_init=8).fit_transform(dist)

    # fairness proxy: HEXACO domain -> closest Big5 domain (H has no Big5 counterpart -> unknown)
    proxy = {"H": None, "E": "N", "X": "E", "A": "A", "C": "C", "O": "O"}

    pairs = []
    for i, j in combinations(range(24), 2):
        a, b = facets[i], facets[j]
        r, r_lo, r_hi = R[i, j], lo[i, j], hi[i, j]
        ri, ri_lo, ri_hi = Ri[i, j], lo_i[i, j], hi_i[i, j]
        if r_hi <= R_CONFLICT:
            rel_type = "conflict"
        elif r_lo >= R_COMPLEMENT:
            rel_type = "complement"
        elif r_lo > -R_INDEP and r_hi < R_INDEP:
            rel_type = "independent"
        else:
            rel_type = "weak"
        tradeoff = ri_hi <= R_CONFLICT  # relative-priority conflict, beyond ipsative artefact
        diff = F[a].to_numpy() - F[b].to_numpy()
        pa_, pb_ = float((diff > PREF_GAP).mean()), float((diff < -PREF_GAP).mean())
        fd = [abs(fair[proxy[x[0]]]["gender_d"]) if proxy[x[0]] else None for x in (a, b)]
        pairs.append({
            "a": a, "b": b, "a_ko": FACET_KO[a], "b_ko": FACET_KO[b],
            "same_domain": a[0] == b[0],
            "r": round(float(r), 3), "r_ci": [round(float(r_lo), 3), round(float(r_hi), 3)],
            "r_ipsative": round(float(ri), 3), "r_ipsative_ci": [round(float(ri_lo), 3), round(float(ri_hi), 3)],
            "type": rel_type, "tradeoff": bool(tradeoff),
            "sd_zdiff": round(float(np.sqrt(2 - 2 * r)), 3),
            "prefer_a": round(pa_, 3), "prefer_b": round(pb_, 3), "tie": round(1 - pa_ - pb_, 3),
            "balance": round(min(pa_, pb_) / max(pa_ + pb_, 1e-9), 3),
            "fair_gender_d_max": None if None in fd else round(max(fd), 3),
            "min_omega": min(rel[a]["omega"], rel[b]["omega"]),
            "invariance_r_ea": round(float(inv["_r_ea"][list(zip(*tri)).index((i, j))]), 3) if "_r_ea" in inv else None,
        })
    inv.pop("_r_ea", None)

    report["hexaco"] = {
        "cleaning": steps, "reliability": rel, "parallel_analysis_factors": pa_k, "top_eigenvalues": eig,
        "tucker_phi": dict(zip(dom_order, np.round(phi6, 3).tolist())),
        "domain_scores_corr": pd.DataFrame({d: F[[f for f in facets if f[0] == d]].mean(axis=1) for d in dom_order}).corr().round(3).to_dict(),
        "invariance": inv, "ipsative_baseline": round(ips_baseline, 3),
        "counts": pd.Series([p["type"] for p in pairs]).value_counts().to_dict(),
        "n_tradeoff": sum(p["tradeoff"] for p in pairs),
    }
    report["mds"] = {f: [round(float(x), 3), round(float(y), 3)] for f, (x, y) in zip(facets, xy)}
    report["pairs"] = pairs
    pd.DataFrame(R, index=facets, columns=facets).round(3).to_csv(OUT / "facet_corr_raw.csv")
    pd.DataFrame(Ri, index=facets, columns=facets).round(3).to_csv(OUT / "facet_corr_ipsative.csv")
    pd.DataFrame(pairs).to_csv(OUT / "pairs.csv", index=False)
    (OUT / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k not in ("pairs", "mds")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "data/raw")
