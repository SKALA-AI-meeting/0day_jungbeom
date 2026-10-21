"""C8 페르소나 유형 비노출: 지원자 응답·WS 프레임에 유형 문자열 0건, 관리자 리포트·디브리핑에는
있음."""

import json
import re
import uuid

from kit import Sess, bearer, draft_content, finish

TYPES = re.compile(r"stubborn|quiet|critic|agreeable|divergent")


async def test_candidate_responses_and_frames_hide_persona_type(api, ctx):
    admin = await api.admin()
    position_id = await api.position(admin)
    invite = await api.invite(admin, position_id)
    token = invite["invite_url"].rsplit("/", 1)[1]
    seen = [(await api.public.get(f"/s/{token}")).json()]
    consent = (await api.public.post(f"/s/{token}/consent", json={})).json()
    seen.append(consent)
    auth = {"Authorization": f"Bearer {consent['session_token']}"}
    sid = consent["session_id"]
    seen.append((await api.public.get(f"/sessions/{sid}/state", headers=auth)).json())
    seen.append((await api.public.post(f"/s/{token}/start", headers=auth)).json())
    sess = Sess(uuid.UUID(sid), token, consent["session_token"], position_id, admin)
    await api.say(sess, "물이 좋겠어요")
    await api.confirm(sess, "keyword", value="물", option_key="water")
    seen.append(await api.state(sess))
    seen.append((await api.public.get(f"/sessions/{sid}/materials", headers=auth)).json())
    seen.append(api.frames(sess))

    assert TYPES.findall(json.dumps(seen, ensure_ascii=False)) == []

    await finish(api, sess)
    content = await draft_content(api, sess, [])
    for d in content["dimensions"]:
        d.update(level=None, no_record_reason="no_activity", confidence=None)
    await api.internal.post(f"/internal/sessions/{sid}/report/draft", json={"content": content})
    report = (await api.public.get(f"/admin/sessions/{sid}/report", headers=bearer(admin))).json()
    assert {s.get("persona_type") for s in report["seats"][1:]} == {"stubborn", "quiet", "critic"}
    debrief = (await api.public.get(f"/sessions/{sid}/debrief", headers=auth)).json()
    assert [s.get("persona_type") for s in debrief["seats"]] == [
        None,
        "stubborn",
        "quiet",
        "critic",
    ]
