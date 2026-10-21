"""러너 단위 테스트(mock) 픽스처: 가짜 api(fake_stack)에 러너를 그대로 붙인다.

실 스택·DB·LLM은 없다.
"""

import pytest

from e2e.client import Target
from e2e.fake_stack import INTERNAL_TOKEN, SECRET, FakeStack


@pytest.fixture
def fake() -> FakeStack:
    return FakeStack()


@pytest.fixture
def target() -> Target:
    return Target(
        public_url="http://fake-public",
        internal_url="http://fake-internal",
        internal_token=INTERNAL_TOKEN,
        jwt_secret=SECRET,
    )
