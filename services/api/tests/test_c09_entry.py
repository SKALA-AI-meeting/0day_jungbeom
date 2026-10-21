"""C9 입장·재입장, 이름·아바타(design.md "이름·입장")."""

import uuid

from kit import Sess


async def test_entry_consent_prestart_state_start_resume_and_debrief(api, ctx, clock):
    admin = await api.admin()
    position_id = await api.position(admin, 15)
    invite = await api.invite(admin, position_id, alias="지원자A")
    token = invite["invite_url"].rsplit("/", 1)[1]

    entry = (await api.public.get(f"/s/{token}")).json()
    assert entry["session_id"] == invite["session_id"]
    assert entry["default_display_name"] == "지원자A"

    consent = (
        await api.public.post(f"/s/{token}/consent", json={"display_name": " 김  지원 "})
    ).json()
    assert consent["session_id"] == invite["session_id"]
    sess = Sess(
        uuid.UUID(consent["session_id"]), token, consent["session_token"], position_id, admin
    )

    before = await api.state(sess)
    assert before["session"]["status"] == "invited" and before["session"]["started_at"] is None
    names = {p["id"]: p for p in before["participants"]}
    assert names["candidate"] == {"id": "candidate", "display_name": "김 지원"}
    assert names["p1"]["display_name"] == "강한결" and names["p1"]["avatar_url"].endswith(".png")
    assert [o["option_key"] for o in before["keyword_options"]] == ["water", "fire", "tree", "wind"]
    assert before["messages"] == [] and before["slots"][0]["status"] == "empty"
    avatar = await api.public.get(names["p1"]["avatar_url"])
    assert avatar.status_code == 200

    started = await api.public.post(f"/s/{token}/start", headers=sess.auth)
    assert started.json()["phase"] == "keyword"
    resumed = (await api.public.post(f"/s/{token}/resume")).json()
    assert resumed["session_id"] == invite["session_id"] and resumed["session_token"]

    await api.say(sess, "물이 좋겠어요. 생활과 가장 가까워요.")
    clock.advance(minutes=16)  # 15분 세션 종료 → 자동 제출
    from app.scheduler import tick

    await tick(ctx)
    ended = (await api.public.get(f"/s/{token}")).json()
    assert ended["status"] == "completed" and ended["session_id"] == invite["session_id"]
    debrief = await api.public.get(
        f"/sessions/{ended['session_id']}/debrief",
        headers={"Authorization": f"Bearer {ended['debrief_token']}"},
    )
    assert debrief.status_code == 200, debrief.text
    body = debrief.json()
    assert body["intro_notice"].startswith("같은 채용 건의 모든 지원자가 같은 장면을 겪었고")
    assert 1 <= len(body["my_messages"]) <= 3 and body["appeal_contact"]
    assert body["seats"][0] == {"seat": "candidate", "display_name": "김 지원"}


async def test_start_refused_when_position_scenario_copy_lacks_catalog(api, ctx):
    """복사본(catalog)이 없는 채용 건은 현재 파일로 채우지 않고 시작을 409로 막는다."""
    from app.models import Position
    from app.services.session import POSITION_OUTDATED

    admin = await api.admin()
    position_id = await api.position(admin, 15)
    async with ctx.session_factory() as db:
        position = await db.get(Position, uuid.UUID(position_id))
        position.scenario = {k: v for k, v in position.scenario.items() if k != "catalog"}
        await db.commit()
    invite = await api.invite(admin, position_id)
    token = invite["invite_url"].rsplit("/", 1)[1]
    consent = (await api.public.post(f"/s/{token}/consent", json={})).json()
    headers = {"Authorization": f"Bearer {consent['session_token']}"}

    started = await api.public.post(f"/s/{token}/start", headers=headers)

    assert started.status_code == 409
    assert started.json()["error"]["code"] == "position_outdated"
    assert started.json()["error"]["message"] == POSITION_OUTDATED
    entry = (await api.public.get(f"/s/{token}")).json()
    assert entry["status"] == "invited"
