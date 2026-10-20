"""Split-half stability + East-Asia direction check for the chosen pairs (run after select_pairs.py)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402

raw = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1] / "data/raw"
sel = json.loads((HERE / "out/selection.json").read_text())
hx = pd.read_csv(raw / "hexaco/HEXACO/data.csv", sep="\t", low_memory=False)
items = [c for c in hx.columns if c not in ("V1", "V2", "country", "elapse")]
hx = hx[(hx[items] > 0).all(axis=1) & (hx.V1 >= 5) & (hx.V2 >= 5)]
hx["elapse"] = pd.to_numeric(hx.elapse, errors="coerce")
hx = hx[hx.elapse > 0]
hx = hx[hx.elapse >= hx.elapse.quantile(0.01)]
keys, F = {}, {}
for f in A.FACET_KO:
    cols = [f"{f}{i}" for i in range(1, 11)]
    keys.update(A.empirical_keys(hx, cols, f"{f}1"))
    F[f] = A.score(hx, cols, keys, 7).mean(1)
F = pd.DataFrame(F, index=hx.index)
mask = np.random.default_rng(7).random(len(F)) < 0.5
out = []
for c in sel["chosen"]:
    halves = []
    for h in (F[mask], F[~mask]):
        d = h[c["a"]] - h[c["b"]]
        pa, pb = (d > A.PREF_GAP).mean(), (d < -A.PREF_GAP).mean()
        halves.append({"r": round(float(np.corrcoef(h[c["a"]], h[c["b"]])[0, 1]), 3), "balance": round(float(min(pa, pb) / (pa + pb)), 3)})
    out.append({"pair": f"{c['a']}-{c['b']}", "r_all": c["r"], "r_east_asia": c["invariance_r_ea"], "half1": halves[0], "half2": halves[1]})
(HERE / "out/robustness.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
