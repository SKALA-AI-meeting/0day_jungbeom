import pytest
from app.config import get_settings
from app.services.context import AppContext

from tests.conftest import ALL_FIVE
from tests.routers.support import bearer, build_clients


@pytest.fixture
def ctx(db, engine, hub, publisher, locks, runner) -> AppContext:
    from app.db import make_session_factory

    return AppContext(
        settings=get_settings(),
        engine=engine,
        session_factory=make_session_factory(engine),
        hub=hub,
        locks=locks,
        publisher=publisher,
        runner=runner,
    )


@pytest.fixture
async def clients(ctx):
    public, internal = build_clients(ctx)
    yield public, internal
    await public.aclose()
    await internal.aclose()


@pytest.fixture
def api(clients):
    return clients[0]


@pytest.fixture
def internal(clients):
    return clients[1]


@pytest.fixture
async def signup(api):
    async def make(email: str, company: str = "회사") -> dict[str, str]:
        res = await api.post(
            "/admin/auth/signup",
            json={"email": email, "password": "pw-12345", "company_name": company},
        )
        assert res.status_code == 200, res.text
        return bearer(res.json()["token"])

    return make


@pytest.fixture
async def admin(signup):
    return await signup("a@example.com", "회사A")


@pytest.fixture
async def other_admin(signup):
    return await signup("b@example.com", "회사B")


@pytest.fixture
def new_position(api, admin):
    async def make(elements=tuple(ALL_FIVE), headers=None) -> dict:
        res = await api.post(
            "/admin/positions",
            json={"name": "프로덕트 기획", "elements": list(elements)},
            headers=headers or admin,
        )
        assert res.status_code == 200, res.text
        return res.json()

    return make


@pytest.fixture
def invite(api, admin):
    async def make(position_id: str, alias: str = "지원자A", headers=None) -> dict:
        res = await api.post(
            f"/admin/positions/{position_id}/invites",
            json={"alias": alias, "email": "cand@example.com"},
            headers=headers or admin,
        )
        assert res.status_code == 200, res.text
        return res.json()

    return make


@pytest.fixture
def start_invited(service):
    """초대된 세션을 consent·start까지 진행시킨다. (session_id) → in_progress."""
    import uuid

    async def make(session_id: str):
        sid = uuid.UUID(session_id)
        await service.consent(sid)
        await service.start(sid)
        return sid

    return make
