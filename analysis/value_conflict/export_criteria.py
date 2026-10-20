"""Export the chosen pairs as product-facing axes -> backend/app/data/criteria.json.

Only labels/descriptions are authored here; every number comes from out/selection.json + out/robustness.json.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEST = HERE.parents[1] / "backend/app/data/criteria.json"

# Product labels for the data-selected pairs. Pole order follows the analysis (a, b).
AXES = {
    frozenset(("HMode", "XSocB")): {
        "id": "V1", "name": "겸양 ↔ 주도",
        "question": "성과와 주도권을 앞에서 드러낼 것인가, 물러서서 남을 세울 것인가",
        "poles": {"HMode": ("겸양", "공을 내세우지 않고 동료를 앞세운다"), "XSocB": ("주도", "앞에 나서서 이끌고 성과를 분명히 드러낸다")},
        "maps_to": ["C02", "C01"],
    },
    frozenset(("HFair", "OUnco")): {
        "id": "V2", "name": "원칙 ↔ 파격",
        "question": "절차와 규칙을 지킬 것인가, 관행을 깨고 우회할 것인가",
        "poles": {"HFair": ("원칙", "정해진 규칙과 절차를 지킨다"), "OUnco": ("파격", "관행을 깨고 더 빠른 길로 우회한다")},
        "maps_to": ["C03", "C05"],
    },
    frozenset(("XExpr", "CPrud")): {
        "id": "V3", "name": "즉시 공유 ↔ 숙고",
        "question": "불확실해도 바로 말할 것인가, 확인한 뒤 신중하게 말할 것인가",
        "poles": {"XExpr": ("즉시 공유", "생각과 상황을 바로 말하고 반응한다"), "CPrud": ("숙고", "확인하고 결과를 따져 본 뒤 말한다")},
        "maps_to": ["C01", "C03"],
    },
    frozenset(("AGent", "CPerf")): {
        "id": "V4", "name": "관용 ↔ 기준",
        "question": "동료의 사정과 관계를 배려할 것인가, 품질 기준을 끝까지 지킬 것인가",
        "poles": {"AGent": ("관용", "사정을 이해하고 너그럽게 넘어간다"), "CPerf": ("기준", "품질 기준에 못 미치면 고친다")},
        "maps_to": ["C02", "C05"],
    },
}


def main():
    sel = json.loads((HERE / "out/selection.json").read_text())
    rob = {r["pair"]: r for r in json.loads((HERE / "out/robustness.json").read_text())}
    res = json.loads((HERE / "out/results.json").read_text())
    axes = []
    for c in sel["chosen"]:
        meta = AXES[frozenset((c["a"], c["b"]))]
        poles = [{"side": s, "facet": c[s], "facet_ko": c[f"{s}_ko"], "label": meta["poles"][c[s]][0], "desc": meta["poles"][c[s]][1]} for s in ("a", "b")]
        axes.append({
            "id": meta["id"], "name": meta["name"], "question": meta["question"], "maps_to": meta["maps_to"],
            "poles": poles, "relation": c["relation"], "controls": c["controls"], "score": c["score"], "max_score": sel["pool"]["max_score"],
            "stats": {
                "r": c["r"], "r_ci": c["r_ci"], "r_ipsative": c["r_ipsative"], "r_east_asia": c["invariance_r_ea"],
                "prefer_a": c["prefer_a"], "prefer_b": c["prefer_b"], "tie": c["tie"], "balance": c["balance"],
                "split_half": [rob[f"{c['a']}-{c['b']}"]["half1"], rob[f"{c['a']}-{c['b']}"]["half2"]],
            },
        })
    axes.sort(key=lambda a: a["id"])
    meta = {
        "source": "openpsychometrics.org IPIP-HEXACO (240 items)",
        "n": res["hexaco"]["cleaning"]["longstring<50%"],
        "n_east_asia": res["hexaco"]["invariance"]["n_east_asia"],
        "pref_gap": res["thresholds"]["pref_gap"],
        "note": "공개 온라인 표본 기준의 '사람 간 선호 분포'이며 한국 지원자 규준이 아님. 점수화에 쓰지 않는다.",
    }
    DEST.write_text(json.dumps({"meta": meta, "axes": axes}, ensure_ascii=False, indent=1))
    print(f"wrote {DEST} ({len(axes)} axes)")


if __name__ == "__main__":
    main()
