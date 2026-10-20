"""완료 기준(오케스트레이터 추가): 역할별 모델·키 선택 규칙(decisions.md 역할별 모델)."""

import pytest
from app.agent.llm import make_llm, model_for
from app.agent.llm.roles import GEMINI_BASE_URL, key_for

ENV = {
    "OPENAI_MODEL": "gpt-4o-mini",
    "OPENAI_API_KEY": "limited",
    "OPENAI_API_KEY_PERSONAL": "personal",
    "GEMINI_API_KEY": "gemini",
    "MODEL_OBSERVE": "gpt-6-mini",
    "MODEL_MANAGER": "gemini-2.5-flash",
}


def test_role_model_and_key_rule():
    assert model_for("colleague", ENV) == "gpt-4o-mini"  # 비면 OPENAI_MODEL
    assert key_for("gpt-4o-mini", ENV) == ("limited", None)
    assert key_for(model_for("observe", ENV), ENV) == ("personal", None)
    assert key_for(model_for("manager", ENV), ENV) == ("gemini", GEMINI_BASE_URL)
    llm = make_llm("manager", ENV)
    assert llm.model == "gemini-2.5-flash" and llm.retry_delays == (1.0, 3.0)
    with pytest.raises(ValueError):
        key_for("gpt-6-mini", {"OPENAI_API_KEY": "limited"})  # 개인 키 없이 상향 모델 금지
