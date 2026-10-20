"""Value-dilemma scenarios built from (job, industry) -> data-selected axis.

Scenario id: "dl.<job>.<industry>". The axis is derived deterministically (criteria.pick_axis), so every
candidate with the same job/industry meets the same hidden dilemma at the same milestone (PRD 5.5 rule 2).
Each axis has one template; job/industry only change nouns (role, artifact, company, regulation, metric).
"""
from functools import lru_cache

from .criteria import AXES, INDUSTRIES, JOBS, pick_axis, rank_axes
from .scenarios import PERSONAS_BASE

# pole_of[persona] says which pole each persona argues for; options map to poles a / b / both.
TEMPLATES = {
    "V1": {
        "title": "성과 발표, 누가 앞에 설까요?",
        "background": (
            "{company}({service})는 이번 분기 핵심 과제를 마쳤다. 지원자({role})와 도현({peer_role})이 함께 만든 {artifact} 작업이 좋은 반응을 얻었고, "
            "내일 전사 회의에서 결과를 발표하고 다음 분기 후속 과제를 이끌 사람을 정해야 한다. 아이디어는 지원자가 처음 냈고, 마지막 2주의 실무는 도현이 가장 많이 했다."
        ),
        "brief": "결과가 좋았던 프로젝트의 마무리 단계입니다. 팀 채널에서 팀장·동료와 이야기를 이어가 주세요.",
        "pole_of": {"lead": "b", "peer": "a"},
        "stance": {
            "lead": "성과를 낸 사람이 앞에 나서서 분명히 말해야 조직이 기억한다고 본다. 아이디어를 낸 지원자가 발표하고 후속 과제도 주도하길 바란다.",
            "peer": "마지막 2주 실무를 거의 혼자 했는데 그게 묻힐까 서운하다. 먼저 나서서 말하긴 어렵고, 기여가 제대로 나뉘어 알려지길 바란다.",
        },
        "beats": {
            "communicate": ("lead", "프로젝트 결과가 좋았다고 축하하고, 내일 전사 회의 발표자와 후속 과제 리드를 정해야 한다며 지원자가 보기엔 각자 어떤 기여를 했는지 정리해 달라고 한다.",
                            "각자의 기여를 사실에 근거해 정리·공유하는지, 발표 목적과 기준을 질문해 확인하는지"),
            "coordinate": ("peer", "마지막 2주 동안 자신이 거의 모든 실무를 했다는 점을 조심스럽게 꺼내며 서운함을 살짝 드러낸다. 팀장은 아이디어 낸 사람이 발표해야 한다고 보고 있어 두 사람 생각이 엇갈린다.",
                           "동료의 서운함을 인정하고 다루는지, 기여 인정과 역할 분담을 조율하려 하는지"),
            "compromise": ("lead", "이제 정해야 한다며, 지원자에게 발표와 후속 과제 리드를 어떻게 할지 선택해 달라고 요청한다.",
                           "선택의 근거를 기여·목적에 비추어 설명하는지, 상대 입장을 함께 고려하는지"),
        },
        "options": {
            "a": "도현님이 발표하고 후속 과제도 이끌도록 하고, 저는 뒤에서 지원할게요.",
            "b": "제가 발표하고 후속 과제를 주도할게요. 도현님 기여는 발표에서 언급할게요.",
            "both": "공동 발표로 하고, 각자 기여한 부분을 나눠 설명해요. 후속 리드는 따로 정해요.",
        },
    },
    "V2": {
        "title": "검토가 밀렸는데 마감은 금요일이에요",
        "background": (
            "{company}({service})에서 지원자({role})는 {artifact} 작업을 금요일까지 내야 한다. {note}. 사내 절차상 '{gate}'를 거쳐야 하는데 검토팀 일정이 밀려 다음 주 화요일에야 가능하다. "
            "도현({peer_role})은 지난 분기에도 검토 전에 먼저 내고 일주일 안에 보완한 적이 있고 그때 문제가 없었다고 말한다."
        ),
        "brief": "마감을 앞두고 사내 검토 일정이 밀린 상황입니다. 팀 채널에서 이야기를 이어가 주세요.",
        "pole_of": {"lead": "a", "peer": "b"},
        "stance": {
            "lead": "{gate}는 생략하면 안 되는 절차라고 본다. 일정이 밀리더라도 순서를 지키는 게 맞다고 생각하지만, 대안이 있으면 듣는다.",
            "peer": "고객이 금요일을 기다리고 있고 지난번 우회해도 문제가 없었다. 먼저 내고 검토는 병행·사후 보완하자는 입장이다.",
        },
        "beats": {
            "communicate": ("lead", "금요일 마감은 그대로인데 '{gate}'가 다음 주 화요일로 밀렸다는 소식을 전하고, 지원자에게 현재 준비 상황과 영향 범위를 정리해 달라고 한다.",
                            "준비 상황과 지연의 영향(고객·일정)을 정리해 공유하는지, 검토가 꼭 필요한 범위를 질문해 확인하는지"),
            "coordinate": ("peer", "지난 분기처럼 먼저 내고 검토는 나중에 보완하자고 제안한다. 팀장은 절차를 지키자는 입장이라 두 사람 의견이 엇갈린다.",
                           "두 의견의 근거를 확인하고 조율하는지, 검토팀·고객 등 필요한 사람에게 도움이나 확인을 요청하는지"),
            "compromise": ("lead", "이제 방향을 정하자며, 지원자에게 어떻게 할지 선택해 달라고 한다.",
                           "선택의 근거(위험·고객 영향·절차의 목적)를 설명하는지, 바뀐 일정이나 범위를 정리하는지"),
        },
        "options": {
            "a": "검토가 끝날 때까지 출시를 미루고, 고객사에 바뀐 일정을 먼저 알릴게요.",
            "b": "금요일에 먼저 내고, 검토는 병행해서 다음 주에 보완할게요.",
            "both": "검토팀에 필수 항목만 먼저 봐 달라고 요청하고, 통과한 범위만 금요일에 낼게요.",
        },
    },
    "V3": {
        "title": "지표가 이상한데, 지금 알릴까요?",
        "background": (
            "{company}({service})에서 지원자({role})가 {artifact} 작업 중에 어제 배포 이후 '{metric}'이 평소보다 크게 떨어진 것을 발견했다. "
            "원인은 아직 확실하지 않고, 데이터 수집 오류일 가능성도 있다. 도현({peer_role})과 팀장이 채널에 있다."
        ),
        "brief": "확실하지 않은 이상 징후를 발견한 상황입니다. 팀 채널에서 이야기를 이어가 주세요.",
        "pole_of": {"lead": "a", "peer": "b"},
        "stance": {
            "lead": "불확실해도 이상 징후는 빨리 공유해야 대응 시간을 번다고 본다. 틀리면 정정하면 된다고 생각한다.",
            "peer": "확인 안 된 경보는 팀을 불필요하게 흔들고 신뢰를 깎는다고 본다. 30분만 원인을 더 확인하고 정리해서 알리자는 입장이다.",
        },
        "beats": {
            "communicate": ("peer", "지원자가 말한 지표 이야기를 듣고 자기도 이상하다고 느꼈다며, 정확히 언제부터 얼마나 떨어졌는지, 수집 오류 가능성은 없는지 묻는다.",
                            "확인된 사실과 모르는 점을 구분해 정리하는지, 필요한 정보를 질문해 확인하는지"),
            "coordinate": ("lead", "이런 건 바로 전체 채널과 담당 조직에 알려야 한다고 말한다. 도현은 확인 후 알리자는 입장이라 두 사람 의견이 엇갈린다.",
                           "공유 시점에 대한 두 의견을 조율하는지, 역할(누가 확인, 누가 공유)을 나누자고 제안하는지"),
            "compromise": ("lead", "지금 정하자며, 지원자에게 어떻게 공유할지 선택해 달라고 한다.",
                           "선택의 근거(위험의 크기·오탐 비용)를 설명하는지, 공유 내용과 후속 확인 일정을 구체적으로 정하는지"),
        },
        "options": {
            "a": "지금 바로 전체에 알리고, 확인된 것과 아직 모르는 것을 나눠서 공유할게요.",
            "b": "30분 더 원인을 확인하고, 정리된 내용으로 공유할게요.",
            "both": "담당자에게만 먼저 알려 확인을 시작하고, 30분 뒤 전체에 정리해서 공유할게요.",
        },
    },
    "V4": {
        "title": "동료 결과물, 이대로 승인할까요?",
        "background": (
            "{company}({service})에서 도현({peer_role})이 맡은 {peer_artifact} 작업이 오늘 마감이다. 리뷰를 맡은 지원자({role})가 보니 품질 기준에 못 미치는 부분이 몇 군데 있다. "
            "도현은 이번 주 개인 사정으로 야근이 어려웠다고 미리 말했다. 이대로 내면 일정은 지키지만 다음 단계에서 다시 손봐야 할 수 있다."
        ),
        "brief": "동료 결과물을 리뷰하는 상황입니다. 팀 채널에서 이야기를 이어가 주세요.",
        "pole_of": {"lead": "b", "peer": "a"},
        "stance": {
            "lead": "기준 미달을 그냥 넘기면 다음 단계에서 비용이 더 커진다고 본다. 마감보다 품질 기준을 지키는 걸 우선한다.",
            "peer": "사정이 있어 시간이 부족했다. 이번엔 승인받고 다음 스프린트에서 꼭 보완하겠다는 입장이다. 지적이 쌓이면 위축된다.",
        },
        "beats": {
            "communicate": ("peer", "리뷰 결과가 어떤지 조심스럽게 묻고, 이번 주 사정 때문에 시간이 부족했다고 다시 한 번 말한다.",
                            "리뷰 결과를 구체적 사실로 전달하는지, 상대 사정을 확인하고 기준을 명확히 공유하는지"),
            "coordinate": ("lead", "기준에 못 미치는 부분이 있다면 고쳐서 내는 게 맞다고 말한다. 도현은 이번엔 승인받고 싶어 해서 두 사람 의견이 엇갈린다.",
                           "관계를 해치지 않으면서 의견 차이를 조율하는지, 함께 고칠 방법이나 도움을 제안하는지"),
            "compromise": ("lead", "이제 결정하자며, 지원자에게 리뷰 결론을 선택해 달라고 한다.",
                           "선택의 근거(결함의 영향·일정)를 설명하는지, 결정에 따라 바뀐 계획을 정리하는지"),
        },
        "options": {
            "a": "이번엔 승인하고, 보완할 목록을 정리해서 다음 스프린트에 넣을게요.",
            "b": "기준에 못 미치는 부분은 고친 뒤에 내요. 마감은 하루 늦추자고 공유할게요.",
            "both": "핵심 결함만 오늘 같이 고쳐서 내고, 나머지는 목록으로 남겨 둘게요.",
        },
    },
}

PERSUADE = {
    "a": "지원자가 고른 방향(%s)에 아쉬움을 표하고, 네 입장(%s)에서 다시 생각해 달라고 근거를 들어 설득하려 한다.",
    "both": "지원자가 낸 절충안(%s)의 실행 부담을 짚는다. 누가, 언제, 무엇을 하는지 구체적으로 묻고 우려 한 가지를 제기한다.",
    "none": "아직 결정이 안 됐다며, 하나를 정하고 이유를 말해 달라고 다시 요청한다.",
}


def _fmt(text: str, ctx: dict) -> str:
    return text.format(**ctx)


def build(scenario_id: str) -> dict:
    _, job, industry = scenario_id.split(".")
    ax_id = pick_axis(job, industry)
    t = TEMPLATES[ax_id]
    ctx = {**JOBS[job], **INDUSTRIES[industry]}
    ax = AXES[ax_id]
    poles = {p["side"]: p for p in ax["poles"]}
    personas = {}
    for pid in ("lead", "peer"):
        base = dict(PERSONAS_BASE[pid])
        if pid == "peer":
            base["role"] = ctx["peer_role"]
        side = t["pole_of"][pid]
        base["character"] = "자기 입장이 분명하지만 상대를 존중한다. 지원자가 근거를 들면 조금씩 받아들인다."
        base["stance"] = f"{_fmt(t['stance'][pid], ctx)} (네가 대변하는 가치: {poles[side]['label']} — {poles[side]['desc']})"
        personas[pid] = base
    beats = {}
    for key, (speaker, convey, look) in t["beats"].items():
        beats[key] = {"speaker": speaker, "must_convey": _fmt(convey, ctx), "look_for": look}
    beats["persuade"] = {"speaker": "lead", "must_convey": PERSUADE["none"], "look_for": "선택을 근거로 설득하는지, 상대 입장을 인정하면서 실행 순서를 제시하는지"}
    return {
        "id": scenario_id,
        "kind": "dilemma",
        "category": f"{JOBS[job]['label']} · {INDUSTRIES[industry]['label']}",
        "tagline": "직무·산업 맞춤 상황",
        "title": t["title"],
        "painpoint_key": None,
        "company": f"{ctx['company']}는 리모트로 일하는 스타트업이고 서비스는 '{ctx['service']}'이다. {ctx['note']}. 모든 소통은 메신저 텍스트로 한다.",
        "background": _fmt(t["background"], ctx),
        "brief": t["brief"],
        "personas": personas,
        "beats": beats,
        "job": job,
        "industry": industry,
        "axis": ax_id,
        "axis_ranking": rank_axes(job, industry),
        "dilemma": {
            "prompt": "어떻게 하시겠어요? 하나를 고르고, 이유를 함께 적어 주세요.",
            "options": [{"id": k, "label": v, "pole": k} for k, v in t["options"].items()],
            "pole_of": t["pole_of"],
        },
    }


@lru_cache(maxsize=64)
def build_cached(scenario_id: str) -> dict:
    parts = scenario_id.split(".")
    if len(parts) != 3 or parts[1] not in JOBS or parts[2] not in INDUSTRIES:
        raise KeyError(scenario_id)
    return build(scenario_id)


def persuade_beat(scn: dict, choice: dict | None) -> dict:
    """The persuade milestone depends on what the candidate chose (opposite-pole persona pushes back)."""
    base = dict(scn["beats"]["persuade"])
    if not choice:
        return base
    poles = {p["side"]: p for p in AXES[scn["axis"]]["poles"]}
    label = next(o["label"] for o in scn["dilemma"]["options"] if o["id"] == choice["option"])
    if choice["pole"] == "both":
        base.update(speaker="lead", must_convey=PERSUADE["both"] % label)
        return base
    opposite = "b" if choice["pole"] == "a" else "a"
    speaker = next(pid for pid, side in scn["dilemma"]["pole_of"].items() if side == opposite)
    base.update(speaker=speaker, must_convey=PERSUADE["a"] % (label, poles[opposite]["label"]))
    return base


def public_options() -> dict:
    return {
        "jobs": [{"id": k, "label": v["label"], "role": v["role"]} for k, v in JOBS.items()],
        "industries": [{"id": k, "label": v["label"], "service": v["service"]} for k, v in INDUSTRIES.items()],
    }
