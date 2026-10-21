"""Minimal in-memory stand-in for Spring Boot's /internal/** (tests only; the real rules live in Spring)."""
import json
import time

import httpx

MILESTONES = ["communicate", "coordinate", "compromise", "persuade"]


class FakeBackend:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}

    def create(self, sid: str, scenario_id: str, alias: str = "지원자") -> dict:
        s = {"id": sid, "alias": alias, "company": "테스트", "scenario_id": scenario_id, "status": "active", "milestone_idx": 0,
             "turns_in_milestone": 0, "condition": None, "choice": None, "milestone_log": [], "notes": "", "report_status": "none",
             "created_at": time.time(), "ended_at": None, "messages": [], "observations": [], "detections": {}, "report": None}
        self.sessions[sid] = s
        return s

    def user_message(self, sid: str, text: str, choice: str | None = None) -> int:
        s = self.sessions[sid]
        idx = len(s["messages"])
        m = {"idx": idx, "speaker": "user", "text": text, "milestone": MILESTONES[s["milestone_idx"]], "ts": time.time()}
        if choice:
            assert s["milestone_idx"] == 2 and not s["choice"]
            m["choice"] = choice
            s["choice"] = {"option": choice, "pole": choice, "msg_idx": idx, "ts": m["ts"]}
        s["messages"].append(m)
        return idx

    def handle(self, req: httpx.Request) -> httpx.Response:
        assert req.headers.get("X-Internal-Key")
        parts = req.url.path.strip("/").split("/")
        body = json.loads(req.content) if req.content else None
        if parts[1] == "conditions":
            return httpx.Response(200, json=[s["condition"] for s in self.sessions.values() if s["condition"]])
        sid = parts[2]
        if sid not in self.sessions:
            return httpx.Response(404, json={"detail": "세션을 찾을 수 없어요."})
        s = self.sessions[sid]
        op = parts[3]
        if op == "state":
            return httpx.Response(200, json=s)
        if op == "init":
            if s["messages"]:
                return httpx.Response(409, json={"detail": "이미 시작된 세션이에요."})
            s["condition"] = body["condition"]
            s["messages"].append(body["message"])
            s["milestone_log"] = [{"key": "communicate", "entered_idx": 0, "ts": time.time()}]
            return httpx.Response(200, json={"ok": True})
        if op == "turn":
            if s["status"] != "active":
                return httpx.Response(409, json={"detail": "이미 종료된 세션이에요."})
            for m in body["new_messages"]:
                assert m["idx"] == len(s["messages"]), "message order"
                assert m["speaker"] in ("lead", "peer")
                s["messages"].append(m)
            s["observations"] += body["observations"]
            assert body["milestone_idx_after"] in (s["milestone_idx"], s["milestone_idx"] + 1)
            if body.get("milestone_log_entry"):
                s["milestone_log"].append(body["milestone_log_entry"])
            s["milestone_idx"], s["turns_in_milestone"] = body["milestone_idx_after"], body["turns_after"]
            if body.get("completed"):
                s["status"], s["ended_at"] = "completed", time.time()
            return httpx.Response(200, json={"status": s["status"], "milestone_idx": s["milestone_idx"]})
        if op == "detections":
            s["detections"][str(body["msg_idx"])] = body["detection"]
            return httpx.Response(200, json={"ok": True})
        if op == "report":
            if s["status"] != "completed":
                return httpx.Response(409, json={"detail": "끝나지 않은 세션"})
            s["report"], s["report_status"] = body["report"], "ready"
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"detail": "unknown"})
