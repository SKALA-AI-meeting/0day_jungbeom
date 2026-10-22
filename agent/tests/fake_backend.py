"""Minimal in-memory stand-in for Spring Boot's /internal/** (tests only; the real rules live in Spring).

Mirrors docs/architecture/api-contract.md: artifacts (init, replace-all), annotations (annotate() plays the candidate's
browser POST), the dialogue ledger (turn), the artifact/annotation GET endpoints, and all three in the session state.
v4 (§5): `state_rev` in the state, bumped on every change that affects analytics (init, the candidate's message and choice,
turn, detection, annotation, report save, status change), and PUT /internal/sessions/{id}/analytics, kept only when its
source.state_rev is not older than the stored snapshot's. analytics_status() answers like Spring's missing | stale | fresh.
"""
import json
import time

import httpx

MILESTONES = ["communicate", "coordinate", "compromise", "persuade"]
ARTIFACT_FIELDS = {"id", "kind", "title", "owner", "status", "summary", "lang", "body"}
MARK_KINDS = {"question", "risk", "suggest", "ok"}
MAX_ANNOTATIONS = 40


class Rejected(Exception):
    """What Spring would answer with a 4xx (status, detail)."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status} {detail}")
        self.status, self.detail = status, detail


class FakeBackend:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.accounts: dict[int, dict] = {}
        self.analytics: dict[str, dict] = {}  # sid -> stored bundle (sessions.analytics_json); kept out of the state like Spring
        self.analytics_puts: list[tuple[str, int, bool]] = []  # (sid, source.state_rev, stored) per PUT, in order
        self._annotation_id = 0

    @staticmethod
    def _bump(s: dict) -> None:
        s["state_rev"] += 1

    def set_status(self, sid: str, status: str) -> None:
        """Spring's finish/complete: a status change bumps state_rev."""
        s = self.sessions[sid]
        s["status"] = status
        if status != "active":
            s["ended_at"] = s["ended_at"] or time.time()
        self._bump(s)

    def analytics_status(self, sid: str) -> str:
        snap = self.analytics.get(sid)
        if snap is None:
            return "missing"
        return "stale" if snap["source"]["state_rev"] < self.sessions[sid]["state_rev"] else "fresh"

    def account(self, **fields) -> dict:
        aid = len(self.accounts) + 1
        a = {"id": aid, "company": "테스트", "email": f"user{aid}@corp.kr", "nickname": "김지원", "desired_job": "pm", "industry": None,
             "experience_years": 1, "bio": "", "consent": True, "status": "PENDING_REVIEW", "invite_alias": None, "created_at": time.time(), **fields}
        self.accounts[aid] = a
        return a

    def create(self, sid: str, scenario_id: str, alias: str = "지원자") -> dict:
        s = {"id": sid, "alias": alias, "company": "테스트", "scenario_id": scenario_id, "status": "active", "milestone_idx": 0,
             "turns_in_milestone": 0, "condition": None, "choice": None, "milestone_log": [], "notes": "", "report_status": "none",
             "created_at": time.time(), "ended_at": None, "messages": [], "observations": [], "detections": {}, "report": None,
             "artifacts": [], "annotations": [], "dialogue": None, "state_rev": 0}
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
        self._bump(s)
        return idx

    def annotate(self, sid: str, artifact_id: str, *, line_start: int | None = None, line_end: int | None = None,
                 quote: str | None = None, kind: str = "risk", text: str = "여기 확인이 필요해 보여요.") -> dict:
        """The candidate's POST /api/sessions/{id}/annotations, with Spring's validation. Raises Rejected like a 4xx."""
        s = self.sessions[sid]
        if s["status"] != "active":
            raise Rejected(409, "진행 중인 세션이 아니에요.")
        art = next((a for a in s["artifacts"] if a["id"] == artifact_id), None)
        if art is None:
            raise Rejected(404, "과제를 찾을 수 없어요.")
        if kind not in MARK_KINDS:
            raise Rejected(400, "마크업 종류가 올바르지 않아요.")
        text = (text or "").strip()
        if not 1 <= len(text) <= 500:
            raise Rejected(400, "내용은 1~500자로 적어 주세요.")
        lines = art["body"].split("\n")
        if line_start is not None:
            line_end = line_start if line_end is None else line_end
            if not 1 <= line_start <= line_end <= len(lines):
                raise Rejected(400, "줄 범위가 올바르지 않아요.")
        if quote is not None and (not quote.strip() or len(quote) > 300 or quote not in art["body"]):
            raise Rejected(400, "인용한 문장이 과제에 없어요.")
        if line_start is None and quote is None:
            raise Rejected(400, "줄이나 인용 중 하나는 있어야 해요.")
        if len(s["annotations"]) >= MAX_ANNOTATIONS:
            raise Rejected(409, "마크업은 세션당 40개까지 남길 수 있어요.")
        self._annotation_id += 1
        n = {"id": self._annotation_id, "artifact_id": artifact_id, "anchor": {"line_start": line_start, "line_end": line_end, "quote": quote},
             "kind": kind, "text": text, "msg_idx": len(s["messages"]), "created_at": time.time()}
        s["annotations"].append(n)
        self._bump(s)
        return n

    def _artifacts(self, items: list[dict]) -> list[dict]:
        ids = [a.get("id") for a in items]
        if len(set(ids)) != len(ids):
            raise Rejected(400, "과제 id가 겹쳐요.")
        for a in items:
            if set(a) != ARTIFACT_FIELDS:  # strict on purpose: planted checkpoints must never reach Spring
                raise Rejected(400, f"과제 필드가 계약과 달라요: {sorted(set(a) ^ ARTIFACT_FIELDS)}")
            if a["kind"] not in ("design", "result", "code") or a["owner"] not in ("lead", "peer", "team") or len(a["body"]) > 6000:
                raise Rejected(400, "과제 형식이 올바르지 않아요.")
        return [dict(a) for a in items]

    def handle(self, req: httpx.Request) -> httpx.Response:
        try:
            return self._handle(req)
        except Rejected as e:
            return httpx.Response(e.status, json={"detail": e.detail})

    def _handle(self, req: httpx.Request) -> httpx.Response:
        assert req.headers.get("X-Internal-Key")
        parts = req.url.path.strip("/").split("/")
        body = json.loads(req.content) if req.content else None
        if parts[1] == "accounts":
            a = self.accounts.get(int(parts[2]))
            if a is None:
                return httpx.Response(404, json={"detail": "계정을 찾을 수 없어요."})
            if len(parts) == 3:
                return httpx.Response(200, json={k: v for k, v in a.items() if k not in ("review",)})
            basis = {"auto_clean": "approved", "auto_schema": "rejected", "admin_approved": "approved", "admin_rejected": "rejected"}
            if basis.get(body["basis"]) != body["decision"]:
                return httpx.Response(400, json={"detail": "결정과 근거가 맞지 않아요."})
            if a["status"] not in ("PENDING_REVIEW", "REVIEW_ERROR"):
                return httpx.Response(409, json={"detail": "이미 결정된 계정이에요."})
            a["status"] = "ACTIVE" if body["decision"] == "approved" else "REJECTED"
            a["review"] = {**(body.get("review") or {}), "basis": body["basis"]}
            return httpx.Response(200, json={"status": a["status"]})
        if parts[1] == "conditions":
            return httpx.Response(200, json=[s["condition"] for s in self.sessions.values() if s["condition"]])
        sid = parts[2]
        if sid not in self.sessions:
            return httpx.Response(404, json={"detail": "세션을 찾을 수 없어요."})
        s = self.sessions[sid]
        op = parts[3]
        if op == "state":
            return httpx.Response(200, json={**s, "annotations": sorted(s["annotations"], key=lambda n: n["id"])})
        if op == "init":
            if s["messages"]:
                return httpx.Response(409, json={"detail": "이미 시작된 세션이에요."})
            if body.get("artifacts") is not None:  # replace-all
                s["artifacts"] = self._artifacts(body["artifacts"])
                keep = {a["id"] for a in s["artifacts"]}
                s["annotations"] = [n for n in s["annotations"] if n["artifact_id"] in keep]
            s["condition"] = body["condition"]
            s["messages"].append(body["message"])
            s["milestone_log"] = [{"key": "communicate", "entered_idx": 0, "ts": time.time()}]
            self._bump(s)
            return httpx.Response(200, json={"ok": True})
        if op == "artifacts":
            if len(parts) == 4:
                return httpx.Response(200, json=[{**{k: a[k] for k in ("id", "kind", "title", "owner", "status", "summary", "lang")},
                                                  "line_count": len(a["body"].split("\n")),
                                                  "annotation_count": sum(n["artifact_id"] == a["id"] for n in s["annotations"])}
                                                 for a in s["artifacts"]])
            art = next((a for a in s["artifacts"] if a["id"] == parts[4]), None)
            if art is None:
                return httpx.Response(404, json={"detail": "과제를 찾을 수 없어요."})
            return httpx.Response(200, json={**art, "annotations": [n for n in s["annotations"] if n["artifact_id"] == art["id"]]})
        if op == "annotations":
            since = int(req.url.params.get("since_idx", 0))
            return httpx.Response(200, json=[n for n in sorted(s["annotations"], key=lambda n: n["id"]) if n["msg_idx"] >= since])
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
            if body.get("dialogue") is not None:  # opaque to Spring: replaces sessions.dialogue_json
                assert isinstance(body["dialogue"], dict)
                s["dialogue"] = body["dialogue"]
            if body.get("completed"):
                s["status"], s["ended_at"] = "completed", time.time()
            self._bump(s)
            return httpx.Response(200, json={"status": s["status"], "milestone_idx": s["milestone_idx"]})
        if op == "detections":
            s["detections"][str(body["msg_idx"])] = body["detection"]
            self._bump(s)
            return httpx.Response(200, json={"ok": True})
        if op == "report":
            if s["status"] != "completed":
                return httpx.Response(409, json={"detail": "끝나지 않은 세션"})
            s["report"], s["report_status"] = body["report"], "ready"
            self._bump(s)
            return httpx.Response(200, json={"ok": True})
        if op == "analytics":
            assert req.method == "PUT"
            src = body.get("source") if isinstance(body, dict) else None
            if not isinstance(src, dict) or body.get("version") != 1 or not isinstance(src.get("state_rev"), int):
                return httpx.Response(400, json={"detail": "분석 번들 형식이 올바르지 않아요."})
            rev = src["state_rev"]
            # test invariant: a bundle is computed from a state Spring served, so it can never be ahead of it
            assert rev <= s["state_rev"], f"bundle rev {rev} ahead of state_rev {s['state_rev']}"
            held = self.analytics.get(sid)
            stored = held is None or rev >= held["source"]["state_rev"]
            if stored:
                self.analytics[sid] = body
            self.analytics_puts.append((sid, rev, stored))
            return httpx.Response(200, json={"stored": stored})
        return httpx.Response(404, json={"detail": "unknown"})
