"""Run one scripted candidate through a scenario with the real LLM and print transcript + evidence."""
import json, sys
import httpx

BASE = "http://127.0.0.1:8765"
c = httpx.Client(base_url=BASE, timeout=120)
sid = sys.argv[1] if len(sys.argv) > 1 else "delay"
lines = [
 "안녕하세요! 현재 화면 흐름은 70% 정도 끝났고 알림 문구가 남아 있어요. 혹시 개발 쪽 진행 상황도 같이 공유받을 수 있을까요?",
 "도현님, 알림 서버 쪽에 지연이 있는지 먼저 알려주셔서 감사해요. 정확히 언제까지 필요한지 알려주실래요?",
 "그럼 오늘 안에 문구/발송 조건 스펙은 제가 먼저 확정해서 드릴게요. 서윤님, 일정은 유지하되 범위 조정이 가능한지 확인하고 싶어요.",
 "제안드려요. 푸시는 다음 배포로 넘기고 이번엔 앱 내 배너로 먼저 내고, 푸시 일정은 문서에 같이 적어둘게요.",
 "재참여율 22%를 올리려면 푸시가 핵심이니, 배너 베타 후 푸시를 이틀 뒤 추가 배포하는 순서로 가는 건 어떨까요? 서윤님께 일정 공지 문구도 제가 정리해 둘게요.",
 "도현님 입장도 이해해요. 이틀 늦춘 일정으로 대표님께 먼저 공유하는 건 제가 정리해서 올릴게요.",
 "정리하면 배너 우선 배포, 푸시는 이틀 뒤입니다. 변경 사항은 오늘 안에 기획서에 반영할게요.",
 "네, 마지막으로 공지 문구 수정본 공유드리겠습니다.",
]
s = c.post("/api/sessions", json={"alias": "테스터", "scenario_id": sid}).json()
print("MOCK?", c.get("/api/health").json())
print("SCN:", s["scenario"]["title"])
def show(m):
    who = {"user": "나", "lead": "팀장", "peer": "도현"}[m["speaker"]]
    print(f"  [{who}] {m['text']}")
show(s["messages"][0])
for t in lines:
    with c.stream("POST", f"/api/sessions/{s['id']}/messages", json={"text": t}) as r:
        for ln in r.iter_lines():
            if ln.startswith("data: "):
                e = json.loads(ln[6:])
                if e["type"] in ("user_message", "message"): show(e["message"])
                elif e["type"] == "milestone": print(f"--- 마일스톤: {e['key']} ---")
                elif e["type"] == "error": print("ERR", e)
adm = c.get(f"/api/admin/sessions/{s['id']}").json()
print("STATUS", adm["status"], "report", adm["report"] and adm["report"]["status"])
for o in adm["observations"]:
    print(f"  {o['competency']} {o['milestone']:11} {o['signal']:8} {o['behavior']} | \"{o['quote'][:40]}\"")
for comp in (adm["report"] or {}).get("competencies", []):
    print(comp["id"], comp["count"], comp["summary"])
