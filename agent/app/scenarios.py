"""Scenario catalogue for the personality (collaboration) assessment, PR1.

All scenarios share the fictional company 루프랩 / 모아런 from the common PRD (§6.1).
Every candidate in a scenario meets the same four milestones, with the same beat content,
in the same order. Only the wording of the personas varies (PRD §5.5 rule 2).
"""

COMPETENCIES = [
    {"id": "C01", "name": "의사소통·요구 파악", "desc": "모호한 요구를 질문하고 핵심 정보를 정리·공유"},
    {"id": "C02", "name": "협업·갈등 조율", "desc": "역할과 의견 차이를 조율하고 필요한 도움을 요청"},
    {"id": "C03", "name": "책임 이행·일정 관리", "desc": "진행·지연·미해결 사항을 공유하고 일정과 맡은 일 관리"},
    {"id": "C05", "name": "변화 대응·피드백 수용", "desc": "변경 조건과 피드백을 확인하고 계획·결과물 수정"},
]

MILESTONES = [
    {"key": "communicate", "label": "소통", "desc": "상황을 파악하고 정보를 맞춘다"},
    {"key": "coordinate", "label": "조율", "desc": "엇갈리는 요구와 역할을 조정한다"},
    {"key": "compromise", "label": "타협", "desc": "서로 양보할 지점을 찾는다"},
    {"key": "persuade", "label": "설득", "desc": "근거를 들어 결정을 이끈다"},
]

COMPANY = (
    "루프랩은 전원 리모트로 일하는 12명 규모 스타트업이다. 서비스 '모아런'은 동네 러닝 모임을 찾아 "
    "함께 뛰는 앱(출시 1년, 월 사용자 3만 명)이다. 첫 모임 참여자 중 두 번째 모임에도 나오는 비율이 22%라 "
    "재참여율 개선이 이번 분기 최우선 과제다. 모든 소통은 메신저 텍스트로 한다."
)

PERSONAS_BASE = {
    "lead": {"id": "lead", "name": "한서윤", "role": "프로덕트 팀장", "emoji": "🧭"},
    "peer": {"id": "peer", "name": "이도현", "role": "입사 2년 차 개발자", "emoji": "🛠️"},
}

# category -> scenario. One scenario per category in PR1.
SCENARIOS = [
    {
        "id": "delay",
        "category": "일정 지연",
        "tagline": "먼저 알릴까, 조용히 넘길까",
        "title": "금요일 베타, 알림 기능이 늦어지고 있어요",
        "painpoint_key": "delay",
        "background": (
            "'모임 리마인드 알림' 기능을 이번 주 금요일 베타로 내기로 했고, 대외 공지도 이미 나갔다. "
            "지원자는 같은 팀 기획자로, 화면 흐름과 알림 문구 기획을 70% 정도 진행한 상태다. "
            "개발자 도현은 알림 서버(API) 작업이 예상보다 이틀 늦어지고 있다."
        ),
        "brief": "금요일 베타를 앞두고 기획 70%가 진행된 상태입니다. 팀 채널에서 팀장·개발자와 이야기를 이어가 주세요.",
        "personas": {
            "lead": {
                **PERSONAS_BASE["lead"],
                "character": "결과 중심이고 말이 짧다. 일정 약속을 중시하지만 근거가 분명하면 받아들인다. 압박을 주려는 게 아니라 상황을 정확히 알고 싶어 한다.",
                "stance": "베타 일정은 이미 공지돼서 가급적 지키고 싶다. 범위를 줄이는 건 괜찮다.",
            },
            "peer": {
                **PERSONAS_BASE["peer"],
                "character": "성실하지만 부담을 혼자 끌어안는 편이다. 솔직하게 말하되 먼저 나서서 문제를 꺼내는 건 서툴다.",
                "stance": "알림 API가 이틀 늦다. 푸시 알림 품질을 포기하고 싶지 않고, 기획 스펙 확정이 필요하다.",
            },
        },
        "beats": {
            "communicate": {
                "speaker": "lead",
                "must_convey": "금요일 베타 공지가 이미 나갔다는 점을 상기시키며, 지금 기획이 어디까지 됐고 막힌 부분이 있는지 정리해서 공유해 달라고 요청한다. 개발 쪽 지연 사실은 아직 말하지 않는다.",
                "look_for": "현재 진행 상황과 막힌 부분을 정리해 공유하는지, 모호한 부분(개발 상황 등)을 질문해 확인하는지",
            },
            "coordinate": {
                "speaker": "peer",
                "must_convey": "알림 서버 작업이 이틀 늦어질 것 같다고 털어놓고, 그러려면 오늘 안에 알림 문구와 발송 조건 스펙을 확정해 줘야 한다고 말한다. 팀장은 일정을 못 미룬다는 입장이라 두 사람의 요구가 엇갈린다.",
                "look_for": "지연 사실을 팀장에게 투명하게 공유하는지, 두 사람의 요구(일정 유지 vs 스펙 확정)를 조율하려 하는지, 필요한 도움을 요청하는지",
            },
            "compromise": {
                "speaker": "lead",
                "must_convey": "푸시 알림은 빼고 앱 내 배너로 먼저 내는 축소안을 제안한다. 도현은 푸시를 포기하기 아쉽다는 입장이라는 점이 드러난다.",
                "look_for": "축소안을 수용·보완하는지, 양쪽이 받아들일 중간안(우선순위·후속 일정)을 제시하는지, 바뀐 범위를 정리해 공유하는지",
            },
            "persuade": {
                "speaker": "peer",
                "must_convey": "축소안이면 푸시 알림은 다음 배포에 밀리는데, 그러면 재참여율 개선 효과를 못 본다며 팀장에게 '이틀만 미루자'고 지원자가 말해 주길 조심스럽게 기대한다.",
                "look_for": "근거(지표·사용자 영향)를 들어 결정을 설득하는지, 상대 입장을 인정하면서 대안과 실행 순서를 제시하는지",
            },
        },
    },
    {
        "id": "scope",
        "category": "범위 변경",
        "tagline": "막판 방향이 바뀌었을 때",
        "title": "대상 사용자가 갑자기 바뀌었어요",
        "painpoint_key": "scope",
        "background": (
            "재참여율 개선 기획안(2~3쪽)을 오늘 오후까지 팀장에게 내기로 했다. "
            "지원자는 '첫 모임 참여자'를 대상으로 문제 정의와 기능 제안을 80% 작성했다. "
            "동료 도현은 같은 문서의 성공 지표와 출시 일정 파트를 맡고 있다."
        ),
        "brief": "오늘 오후 마감인 기획안이 80% 완성된 상태입니다. 팀 채널의 대화를 이어가 주세요.",
        "personas": {
            "lead": {
                **PERSONAS_BASE["lead"],
                "character": "방향을 빠르게 정리하는 리더. 대표의 결정을 전달하는 입장이라 미안해하면서도 마감은 그대로라고 못 박는다.",
                "stance": "대상은 바꿔야 하고 마감은 그대로다. 단, 범위를 줄이는 건 협의할 수 있다.",
            },
            "peer": {
                **PERSONAS_BASE["peer"],
                "character": "자기 파트가 다시 쓰이는 게 부담스러워 불만을 숨기지 않지만 협조적이다.",
                "stance": "성공 지표 파트를 처음부터 다시 써야 해서 마감이 빠듯하다고 느낀다.",
            },
        },
        "beats": {
            "communicate": {
                "speaker": "lead",
                "must_convey": "대표와 이야기해 보니 기획 대상을 '첫 참여자'에서 '3개월 넘게 모임에 안 나온 사용자'로 바꿔야 한다고 알린다. 마감은 그대로다. 이유는 간단히만 설명한다.",
                "look_for": "바뀐 조건(대상, 마감)을 되물어 정확히 확인하는지, 변경 이유와 영향 범위를 정리하는지",
            },
            "coordinate": {
                "speaker": "peer",
                "must_convey": "자기 성공 지표 파트가 대상이 바뀌면 전부 다시 써야 한다며, 지원자의 문제 정의가 언제 나오는지 물어본다. 문서 순서가 꼬일까 걱정한다.",
                "look_for": "역할과 순서를 다시 나누자고 제안하는지, 의존 관계와 마감을 고려해 필요한 도움을 요청하는지",
            },
            "compromise": {
                "speaker": "lead",
                "must_convey": "이번 마감에는 문제 정의와 핵심 기능 1개까지만 새 대상으로 쓰고, 지표·출시 일정은 초안 수준으로 두자는 범위 축소안을 낸다. 지원자의 의견을 묻는다.",
                "look_for": "범위 축소안을 검토해 수용·보완하는지, 불만을 표현하는 방식, 바뀐 방향을 계획에 반영하는지",
            },
            "persuade": {
                "speaker": "peer",
                "must_convey": "그래도 지표 파트까지 같이 가야 대표 설명이 가능하다고 주장하며, 팀장에게 한 가지만 더 요청해 보자고 지원자를 설득하려 한다.",
                "look_for": "상대 입장을 인정하며 근거로 설득하는지, 수정된 계획(산출물·시간 배분)을 명확히 제시하는지",
            },
        },
    },
    {
        "id": "conflict",
        "category": "의견 충돌",
        "tagline": "두 사람의 방향이 다를 때",
        "title": "재참여 기능, 팀장과 개발자의 방향이 달라요",
        "painpoint_key": "conflict",
        "background": (
            "재참여율을 올릴 핵심 기능을 하나 정해야 한다. 팀장은 '다음 모임 자동 추천'을, "
            "도현은 '모임 후 참가자 간 간단 채팅'을 밀고 있다. "
            "지원자는 두 안의 자료를 모두 본 같은 팀 기획자이며, 오늘 안에 하나로 정리해야 한다."
        ),
        "brief": "핵심 기능 방향이 둘로 갈린 상태입니다. 팀 채널에서 두 사람과 이야기해 주세요.",
        "personas": {
            "lead": {
                **PERSONAS_BASE["lead"],
                "character": "데이터를 근거로 말하는 리더. 자기 안에 자신이 있지만 다른 근거가 있으면 듣는다.",
                "stance": "다음 모임 자동 추천이 구현 부담이 작고 지표에 직접 닿는다고 본다.",
            },
            "peer": {
                **PERSONAS_BASE["peer"],
                "character": "사용자 인터뷰를 인용하며 열정적으로 주장한다. 반박당하면 잠깐 방어적이 되지만 합리적이다.",
                "stance": "첫 참여자는 '아는 사람이 없어 어색했다'는 의견이 많으니 참가자 간 채팅이 먼저라고 본다.",
            },
        },
        "beats": {
            "communicate": {
                "speaker": "lead",
                "must_convey": "지원자에게 두 안(다음 모임 자동 추천 / 참가자 간 채팅) 중 오늘 하나로 정리해야 한다고 말하고, 지원자는 어느 쪽이 맞다고 보는지 먼저 묻는다.",
                "look_for": "두 안의 근거와 기준을 질문해 파악하는지, 핵심 쟁점을 정리해 양쪽에 공유하는지",
            },
            "coordinate": {
                "speaker": "peer",
                "must_convey": "인터뷰에서 어색함이 가장 큰 이탈 이유였다며 자신의 안이 맞다고 주장하고, 팀장이 자기 안을 너무 빨리 정한 것 같다는 서운함을 살짝 드러낸다.",
                "look_for": "감정이 섞인 의견 차이를 중립적으로 풀어 가는지, 각자의 근거를 인정하며 조율 방식을 제안하는지",
            },
            "compromise": {
                "speaker": "lead",
                "must_convey": "구현 부담 때문에 두 기능을 다 하기는 어렵다며, 이번 분기에 한 개만, 나머지는 다음 분기에 검토하자고 말한다. 지원자에게 절충안이 있는지 묻는다.",
                "look_for": "단계적 적용·검증 방법 등 절충안을 내는지, 양쪽이 받아들일 기준(지표·기간)을 제시하는지",
            },
            "persuade": {
                "speaker": "peer",
                "must_convey": "그래도 채팅이 빠지면 첫 참여자 문제가 안 풀린다며 지원자가 자기 편에 서 줄 수 있는지 직접 묻는다.",
                "look_for": "한쪽 편들기를 피하면서 근거로 입장을 밝히는지, 관계를 해치지 않고 설득하는지",
            },
        },
    },
    {
        "id": "workload",
        "category": "업무 분담",
        "tagline": "도움 요청과 우선순위 사이",
        "title": "내 일도 바쁜데 도움 요청이 들어왔어요",
        "painpoint_key": "workload",
        "background": (
            "내일 아침 팀 리뷰 전까지 '사용자 인터뷰 요약 정리'가 필요하다. 지원자는 이 업무의 담당이고 60% 진행했다. "
            "그런데 도현이 '비슷한 서비스 사례 정리'를 하다가 기준이 헷갈린다며 도움을 청해 온다. "
            "팀장은 두 업무 모두 내일 리뷰에 필요하다고 한다."
        ),
        "brief": "내일 리뷰를 앞두고 본인 업무가 60% 진행된 상태입니다. 팀 채널에서 이어가 주세요.",
        "personas": {
            "lead": {
                **PERSONAS_BASE["lead"],
                "character": "바쁘지만 팀원의 부담을 살피는 리더. 사람들이 알아서 조율하길 기대하고 직접 지시하기를 꺼린다.",
                "stance": "두 업무 모두 내일 필요하고, 누가 무엇을 할지는 팀원이 정리해 알려 주길 원한다.",
            },
            "peer": {
                **PERSONAS_BASE["peer"],
                "character": "후배로서 도움을 청하는 게 미안하지만 막힌 상태다. 상대가 거절해도 이해하려 한다.",
                "stance": "사례 정리의 비교 기준을 몰라 혼자서는 진도가 안 나간다.",
            },
        },
        "beats": {
            "communicate": {
                "speaker": "peer",
                "must_convey": "비슷한 서비스 사례를 정리하는데 비교 기준이 헷갈린다며, 10분만 같이 봐줄 수 있는지 조심스럽게 묻는다.",
                "look_for": "도움 요청의 범위·시급성을 되묻는지, 자신의 상황(진행률, 마감)을 공유하는지",
            },
            "coordinate": {
                "speaker": "lead",
                "must_convey": "두 업무 모두 내일 리뷰에 필요하니 서로 알아서 우선순위를 정리해서 알려 달라고 한다. 누구 일이 더 중요한지는 말해 주지 않는다.",
                "look_for": "우선순위·시간 배분을 제안하는지, 팀장에게 필요한 판단을 요청하는지, 진행 상황을 투명하게 공유하는지",
            },
            "compromise": {
                "speaker": "peer",
                "must_convey": "그럼 자기가 기준 초안을 만들어 보고 지원자는 확인만 해 주면 안 되냐고 제안한다. 대신 자기 마감도 빠듯하다고 덧붙인다.",
                "look_for": "제안을 검토해 수용·보완하는지, 서로의 일정을 고려한 구체적 분담(시간, 산출물)을 정하는지",
            },
            "persuade": {
                "speaker": "lead",
                "must_convey": "인터뷰 요약이 먼저 필요하니 사례 정리는 오전으로 미뤄도 되지 않겠냐고 지원자가 도현을 설득해 줄 수 있는지 부탁한다.",
                "look_for": "상대의 부담을 인정하면서 대안과 실행 순서를 제시하는지, 약속한 내용을 정리해 확인하는지",
            },
        },
    },
]

SCENARIO_BY_ID = {s["id"]: s for s in SCENARIOS}
COMPETENCY_IDS = [c["id"] for c in COMPETENCIES]
MILESTONE_KEYS = [m["key"] for m in MILESTONES]
MIN_TURNS_PER_MILESTONE = 2


for _s in SCENARIOS:
    _s.setdefault("company_name", "루프랩")


def get_scenario(scenario_id: str) -> dict:
    """PR1 category scenarios by id, or value-dilemma scenarios 'dl.<job>.<industry>' built on demand."""
    if scenario_id in SCENARIO_BY_ID:
        return SCENARIO_BY_ID[scenario_id]
    if scenario_id.startswith("dl."):
        from .dilemmas import build_cached

        return build_cached(scenario_id)
    raise KeyError(scenario_id)


def public_scenario(s: dict) -> dict:
    """What the candidate may see: no beats, no persona stances (PRD: format is disclosed, situations are not)."""
    return {
        "id": s["id"],
        "kind": s.get("kind", "category"),
        "category": s["category"],
        "tagline": s["tagline"],
        "title": s["title"],
        "background": s["background"],
        "brief": s["brief"],
        "personas": [
            {k: p[k] for k in ("id", "name", "role", "emoji")} for p in s["personas"].values()
        ],
    }
