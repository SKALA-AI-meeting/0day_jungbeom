package dev.dayzero.backend.service;

import dev.dayzero.backend.config.AppProperties;
import dev.dayzero.backend.domain.*;
import dev.dayzero.backend.repo.*;
import dev.dayzero.backend.security.AuthUser;
import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * All business rules of an assessment session live here (single place, PDF 5-1):
 * invite validity, one turn at a time, choice only once and only in the compromise milestone,
 * status transitions, automatic report task on completion, company isolation, restarting a failed opening.
 * Every change that affects the admin analytics bumps sessions.state_rev (ChatSessionRepository.bumpRev): init, turn
 * (the candidate's message and choice, the agent's reply), detection, report save, completion; markups in ArtifactService.
 * Shared work items and markups: ArtifactService. Analytics snapshot and ANALYTICS tasks: AnalyticsService.
 */
@Service
public class SessionService {
    public static final List<String> MILESTONES = List.of("communicate", "coordinate", "compromise", "persuade");
    private static final Set<String> CHOICES = Set.of("a", "b", "both");
    private static final SecureRandom RNG = new SecureRandom();

    private final ChatSessionRepository sessions;
    private final InviteRepository invites;
    private final MessageRepository messages;
    private final ObservationRepository observations;
    private final DetectionRepository detections;
    private final AiTaskRepository taskRepo;
    private final TaskService tasks;
    private final AgentClient agent;
    private final ArtifactService artifacts;
    private final AnalyticsService analytics;
    private final Json json;
    private final AppProperties props;

    public SessionService(ChatSessionRepository sessions, InviteRepository invites, MessageRepository messages, ObservationRepository observations,
                          DetectionRepository detections, AiTaskRepository taskRepo, TaskService tasks, AgentClient agent, ArtifactService artifacts,
                          AnalyticsService analytics, Json json, AppProperties props) {
        this.sessions = sessions; this.invites = invites; this.messages = messages; this.observations = observations;
        this.detections = detections; this.taskRepo = taskRepo; this.tasks = tasks; this.agent = agent; this.artifacts = artifacts;
        this.analytics = analytics; this.json = json; this.props = props;
    }

    // ---------------------------------------------------------------- invites
    public Map<String, Object> inviteInfo(String token) {
        Optional<Invite> inv = invites.findByToken(token);
        if (inv.isEmpty()) return Map.of("valid", false, "reason", "not_found", "message", "초대 링크를 찾을 수 없어요.");
        Invite i = inv.get();
        String reason = inviteProblem(i);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("valid", reason == null);
        out.put("company", i.company.name);
        out.put("alias", i.alias);
        out.put("expiresAt", i.expiresAt);
        if (reason != null) {
            out.put("reason", reason);
            out.put("message", "expired".equals(reason) ? "링크가 만료되었습니다. 채용 담당자에게 문의해 주세요." : "이미 완료된 평가입니다.");
        }
        return out;
    }

    private String inviteProblem(Invite i) {
        if (i.expiresAt != null && i.expiresAt.isBefore(OffsetDateTime.now())) return "expired";
        if (!i.reusable && i.usedAt != null) return "used";
        return null;
    }

    /** Start a session for an ACTIVE account. The invite (the account's own, or one passed in) is consumed here. */
    @Transactional
    public Map<String, Object> startForAccount(Account a, String scenarioId, String inviteToken) {
        if (!"ACTIVE".equals(a.status)) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "계정 검토가 끝난 뒤에 평가를 시작할 수 있어요.");
        Invite inv = (inviteToken == null || inviteToken.isBlank()) ? a.invite
                : invites.findByToken(inviteToken).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "초대 링크를 찾을 수 없어요."));
        if (inv == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "초대 링크가 필요해요.");
        if (!Objects.equals(inv.company.id, a.company.id)) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "다른 회사의 초대 링크예요.");
        String problem = inviteProblem(inv);
        if (problem != null) throw new ResponseStatusException(HttpStatus.GONE, "expired".equals(problem) ? "링크가 만료되었습니다." : "이 초대로는 이미 평가를 시작했어요. 내 평가에서 이어서 진행해 주세요.");
        if (agent.scenario(scenarioId) == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "알 수 없는 시나리오예요.");
        ChatSession s = new ChatSession();
        s.id = newId();
        s.company = inv.company;
        s.invite = inv;
        s.account = a;
        s.alias = a.nickname;
        s.scenarioId = scenarioId;
        sessions.save(s);
        if (!inv.reusable) { inv.usedAt = OffsetDateTime.now(); invites.save(inv); }
        AiTask start = tasks.create("START", s.id, s.company.id, a.id, "account:" + a.id, Map.of());
        return Map.of("sessionId", s.id, "startTaskId", start.id, "company", s.company.name);
    }

    public List<Map<String, Object>> accountSessions(Account a) {
        return sessions.findByAccountIdOrderByCreatedAtDesc(a.id).stream().map(s -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", s.id); m.put("scenarioId", s.scenarioId); m.put("status", s.status); m.put("milestoneIdx", s.milestoneIdx);
            m.put("createdAt", s.createdAt); m.put("endedAt", s.endedAt);
            return m;
        }).toList();
    }

    @Transactional
    public Invite createInvite(Company c, String alias, String email) {
        Invite i = new Invite();
        i.company = c;
        i.token = newId() + newId();
        i.alias = alias;
        i.email = email;
        i.reusable = false;
        i.expiresAt = OffsetDateTime.now().plusHours(props.inviteTtlHours());
        return invites.save(i);
    }

    // ---------------------------------------------------------------- access
    public ChatSession load(String id) {
        return sessions.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "세션을 찾을 수 없어요."));
    }

    public ChatSession authorized(String id, AuthUser u) {
        ChatSession s = load(id);
        boolean ok = (u.isCandidate() && s.account != null && Objects.equals(s.account.id, u.accountId()))
                || (u.isAdmin() && Objects.equals(u.companyId(), s.company.id));
        if (!ok) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "이 세션에 접근할 수 없어요.");
        return s;
    }

    // ---------------------------------------------------------------- candidate actions
    @Transactional
    public Map<String, Object> submitTurn(AuthUser u, String sessionId, String text, String choiceId) {
        ChatSession s = authorized(sessionId, u);
        if (!u.isCandidate()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "대화는 지원자만 보낼 수 있어요.");
        if (!"active".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 종료된 세션이에요.");
        if (text == null || text.isBlank() || text.length() > 1500) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "메시지는 1~1500자로 보내 주세요.");
        boolean busy = !taskRepo.findBySessionIdAndTypeAndStatusIn(sessionId, "TURN", TaskService.ACTIVE).isEmpty()
                || !taskRepo.findBySessionIdAndTypeAndStatusIn(sessionId, "START", TaskService.ACTIVE).isEmpty();
        if (busy) throw new ResponseStatusException(HttpStatus.CONFLICT, "팀원들이 아직 답하는 중이에요. 잠시 후 보내 주세요.");
        String milestone = MILESTONES.get(s.milestoneIdx);
        if (choiceId != null) {
            if (!CHOICES.contains(choiceId)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "알 수 없는 선택지예요.");
            if (s.choiceJson != null) throw new ResponseStatusException(HttpStatus.CONFLICT, "선택은 한 번만 할 수 있어요.");
            if (!"compromise".equals(milestone)) throw new ResponseStatusException(HttpStatus.CONFLICT, "지금은 선택을 제출할 수 없어요.");
        }
        int idx = (int) messages.countBySessionId(sessionId);
        Message m = new Message();
        m.sessionId = sessionId; m.idx = idx; m.speaker = "user"; m.text = text.strip(); m.milestone = milestone; m.choice = choiceId;
        messages.save(m);
        if (choiceId != null) {
            s.choiceJson = json.write(Map.of("option", choiceId, "pole", choiceId, "msg_idx", idx, "ts", epoch(m.createdAt)));
            sessions.save(s);
        }
        sessions.bumpRev(sessionId); // the candidate's message (and choice) counts in the analytics
        AiTask t = tasks.create("TURN", sessionId, s.company.id, u.accountId(), u.subject(), Map.of("text", m.text, "user_idx", idx, "choice_id", choiceId == null ? "" : choiceId));
        return Map.of("taskId", t.id, "userMessage", messageMap(m));
    }

    @Transactional
    public void saveNotes(AuthUser u, String id, String text) {
        ChatSession s = authorized(id, u);
        if (!u.isCandidate()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "노트는 지원자만 쓸 수 있어요.");
        s.notes = text == null ? "" : text;
        sessions.save(s);
    }

    @Transactional
    public void finish(AuthUser u, String id) {
        ChatSession s = authorized(id, u);
        if ("active".equals(s.status)) complete(s);
    }

    /**
     * Loop closure for a failed opening: while nobody has spoken yet and the latest START failed, the candidate
     * asks for a new START (the agent re-seeds condition, work items and the opening message).
     */
    @Transactional
    public Map<String, Object> restart(AuthUser u, String id) {
        ChatSession s = authorized(id, u);
        if (!u.isCandidate()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "평가는 지원자만 다시 시작할 수 있어요.");
        if (!"active".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 종료된 세션이에요.");
        if (messages.countBySessionId(id) > 0) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 대화가 시작된 세션이에요.");
        String status = startStatus(id);
        if ("running".equals(status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "팀원들이 아직 대화를 준비하고 있어요. 잠시만 기다려 주세요.");
        if (!"failed".equals(status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 시작된 세션이에요.");
        AiTask start = tasks.create("START", s.id, s.company.id, u.accountId(), u.subject(), Map.of());
        return Map.of("taskId", start.id);
    }

    /** running | failed | done — done once the opening message exists, otherwise the latest START decides. */
    public String startStatus(String id) {
        if (messages.countBySessionId(id) > 0) return "done";
        Optional<AiTask> start = taskRepo.findBySessionIdAndTypeOrderByCreatedAtDesc(id, "START").stream().findFirst();
        if (start.isEmpty()) return "failed"; // nothing will write the opening: let the candidate start it again
        if (TaskService.ACTIVE.contains(start.get().status)) return "running";
        return "DONE".equals(start.get().status) ? "done" : "failed";
    }

    @Transactional
    public Map<String, Object> annotate(AuthUser u, String id, String artifactId, Integer lineStart, Integer lineEnd, String quote, String kind, String text) {
        ChatSession s = authorized(id, u);
        if (!u.isCandidate()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "마크업은 지원자만 남길 수 있어요.");
        return artifacts.publicAnnotation(artifacts.annotate(s, artifactId, lineStart, lineEnd, quote, kind, text));
    }

    @Transactional
    public void deleteAnnotation(AuthUser u, String id, Long annotationId) {
        ChatSession s = authorized(id, u);
        if (!u.isCandidate()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "마크업은 지원자만 지울 수 있어요.");
        artifacts.deleteAnnotation(s, annotationId);
    }

    /** REPORT_FAILED "넘기기": the admin decides not to retry; the item leaves the checklist. */
    @Transactional
    public Map<String, Object> dismissReport(AuthUser u, String id) {
        ChatSession s = authorized(id, u);
        if (!u.isAdmin()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "관리자만 넘길 수 있어요.");
        if (!"failed".equals(s.reportStatus)) throw new ResponseStatusException(HttpStatus.CONFLICT, "만들지 못한 리포트만 넘길 수 있어요.");
        s.reportStatus = "dismissed";
        sessions.save(s);
        return Map.of("report_status", s.reportStatus);
    }

    private void complete(ChatSession s) {
        s.status = "completed";
        s.endedAt = OffsetDateTime.now();
        sessions.save(s);
        sessions.bumpRev(s.id);
        requestReport(s, "system");
    }

    @Transactional
    public AiTask requestReport(ChatSession s, String by) {
        if (!taskRepo.findBySessionIdAndTypeAndStatusIn(s.id, "REPORT", TaskService.ACTIVE).isEmpty())
            throw new ResponseStatusException(HttpStatus.CONFLICT, "리포트를 이미 만들고 있어요.");
        s.reportStatus = "pending";
        sessions.save(s);
        return tasks.create("REPORT", s.id, s.company.id, by, Map.of());
    }

    // ---------------------------------------------------------------- internal API (agent via business-mcp)
    public Map<String, Object> state(String id) {
        return state(load(id));
    }

    /** state_rev is read first (with the row), so a change that lands while the rest is read only makes the snapshot look older. */
    private Map<String, Object> state(ChatSession s) {
        String id = s.id;
        Map<String, Object> st = baseState(s);
        st.put("state_rev", s.stateRev);
        st.put("messages", messages.findBySessionIdOrderByIdxAsc(id).stream().map(this::messageMap).toList());
        st.put("observations", observations.findBySessionIdOrderByIdAsc(id).stream().map(this::obsMap).toList());
        Map<String, Object> det = new LinkedHashMap<>();
        for (Detection d : detections.findBySessionId(id)) det.put(String.valueOf(d.msgIdx), json.any(d.docJson));
        st.put("detections", det);
        st.put("report", json.any(s.reportJson));
        st.put("artifacts", artifacts.internalList(id));
        st.put("annotations", artifacts.internalAnnotations(id, 0));
        st.put("dialogue", json.any(s.dialogueJson));
        return st;
    }

    private Map<String, Object> baseState(ChatSession s) {
        Map<String, Object> st = new LinkedHashMap<>();
        st.put("id", s.id);
        st.put("alias", s.alias);
        st.put("company", s.company.name);
        st.put("scenario_id", s.scenarioId);
        st.put("status", s.status);
        st.put("milestone_idx", s.milestoneIdx);
        st.put("turns_in_milestone", s.turnsInMilestone);
        st.put("condition", json.any(s.conditionJson));
        st.put("choice", json.any(s.choiceJson));
        st.put("milestone_log", json.list(s.milestoneLogJson));
        st.put("notes", s.notes == null ? "" : s.notes);
        st.put("report_status", s.reportStatus);
        st.put("created_at", epoch(s.createdAt));
        st.put("ended_at", s.endedAt == null ? null : epoch(s.endedAt));
        return st;
    }

    public List<Map<String, Object>> conditions() {
        return sessions.allConditionJson().stream().map(json::map).toList();
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> init(String id, Map<String, Object> body) {
        ChatSession s = load(id);
        if (messages.countBySessionId(id) > 0) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 시작된 세션이에요.");
        if (body.get("artifacts") != null) artifacts.replaceAll(id, body.get("artifacts"));
        s.conditionJson = json.write(body.get("condition"));
        Map<String, Object> msg = (Map<String, Object>) body.get("message");
        saveAgentMessage(id, msg, 0);
        s.milestoneLogJson = json.write(List.of(Map.of("key", MILESTONES.get(0), "entered_idx", 0, "ts", epoch(OffsetDateTime.now()))));
        sessions.save(s);
        sessions.bumpRev(id);
        return Map.of("ok", true);
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> applyTurn(String id, Map<String, Object> body) {
        ChatSession s = load(id);
        if (!"active".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 종료된 세션이에요.");
        int next = (int) messages.countBySessionId(id);
        for (Map<String, Object> m : (List<Map<String, Object>>) body.getOrDefault("new_messages", List.of())) {
            saveAgentMessage(id, m, next++);
        }
        for (Map<String, Object> o : (List<Map<String, Object>>) body.getOrDefault("observations", List.of())) {
            Observation ob = new Observation();
            ob.sessionId = id; ob.obsKey = str(o.get("id")); ob.competency = str(o.get("competency")); ob.milestone = str(o.get("milestone"));
            ob.behavior = str(o.get("behavior")); ob.quote = str(o.get("quote")); ob.signal = str(o.get("signal")); ob.msgIdx = num(o.get("msg_idx"));
            observations.save(ob);
        }
        int after = num(body.getOrDefault("milestone_idx_after", s.milestoneIdx));
        if (after < 0 || after >= MILESTONES.size() || after < s.milestoneIdx || after > s.milestoneIdx + 1)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "단계 전환이 올바르지 않아요.");
        if (body.get("milestone_log_entry") instanceof Map<?, ?> entry) {
            List<Object> logList = new ArrayList<>(json.list(s.milestoneLogJson));
            logList.add(entry);
            s.milestoneLogJson = json.write(logList);
        }
        s.milestoneIdx = after;
        s.turnsInMilestone = num(body.getOrDefault("turns_after", s.turnsInMilestone + 1));
        Object dialogue = body.get("dialogue"); // the agent's ledger, replaced whole; absent / null keeps the last one
        if (dialogue != null) {
            if (!(dialogue instanceof Map)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "dialogue는 객체여야 해요.");
            s.dialogueJson = json.write(dialogue);
        }
        sessions.save(s);
        sessions.bumpRev(id);
        boolean completed = Boolean.TRUE.equals(body.get("completed"));
        if (completed) complete(s);
        return Map.of("status", s.status, "milestone_idx", s.milestoneIdx);
    }

    @Transactional
    public void saveDetection(String id, int msgIdx, Object doc) {
        load(id);
        Detection d = detections.findBySessionIdAndMsgIdx(id, msgIdx).orElseGet(Detection::new);
        d.sessionId = id; d.msgIdx = msgIdx; d.docJson = json.write(doc);
        detections.save(d);
        sessions.bumpRev(id);
    }

    @Transactional
    public void saveReport(String id, Object report) {
        ChatSession s = load(id);
        if (!"completed".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "끝나지 않은 세션에는 리포트를 저장할 수 없어요.");
        s.reportJson = json.write(report);
        s.reportStatus = "ready";
        sessions.save(s);
        sessions.bumpRev(id);
    }

    // ---------------------------------------------------------------- views
    /**
     * The candidate's screen (computed by the agent's catalog): never the dialogue ledger, observations, planted
     * checkpoints, the report or anything from the analytics (bundle, figures, charts).
     */
    public Map<String, Object> candidateView(AuthUser u, String id) {
        authorized(id, u);
        Map<String, Object> st = state(id);
        st.remove("dialogue");
        st.remove("report"); // carries the report's figures and charts: for the company only
        Map<String, Object> v = new LinkedHashMap<>(agent.view("candidate", st));
        v.remove("dialogue");
        v.remove("artifact_checks");
        v.remove("analytics");
        v.remove("figures");
        v.remove("charts");
        v.put("artifacts", artifacts.publicList(id));
        v.put("start_status", startStatus(id));
        v.put("busy", !taskRepo.findBySessionIdAndTypeAndStatusIn(id, "TURN", TaskService.ACTIVE).isEmpty()
                || !taskRepo.findBySessionIdAndTypeAndStatusIn(id, "START", TaskService.ACTIVE).isEmpty());
        return v;
    }

    /**
     * The admin's session screen — no call to the agent. Spring's own data (the session state, public work items,
     * dialogue ledger, tasks, the report draft waiting for approval) plus the stored analytics snapshot: everything
     * the agent computes (scenario, painpoints, dilemma and condition details, detector, artifact_checks, timeline,
     * heatmap, figures, charts) is only in `analytics`, with `analytics_status` and the working `analytics_task`.
     */
    public Map<String, Object> adminView(AuthUser u, String id) {
        ChatSession s = authorized(id, u);
        Map<String, Object> v = state(s);
        v.put("artifacts", artifacts.publicList(id));
        List<Map<String, Object>> recent = new ArrayList<>();
        Map<String, Object> analyticsTask = null;
        for (AiTask t : taskRepo.findBySessionIdOrderByCreatedAtDesc(id)) {
            recent.add(taskMap(t));
            if ("REPORT".equals(t.type) && "WAITING_APPROVAL".equals(t.status) && !v.containsKey("pending_approval"))
                v.put("pending_approval", Map.of("taskId", t.id, "draft", Objects.requireNonNullElse(json.any(t.resultJson), Map.of())));
            if (analyticsTask == null) analyticsTask = AnalyticsService.working(t);
        }
        v.put("tasks", recent);
        Map<String, Object> bundle = analytics.snapshot(s);
        v.put("analytics", bundle);
        v.put("analytics_status", analytics.status(s, bundle));
        v.put("analytics_task", analyticsTask);
        return v;
    }

    /**
     * Dashboard rows — no call to the agent. The keys of the agent-made rows (category, axis, choice, condition) come
     * from the snapshot's `row` (category falls back to scenario_id; the others stay null until a snapshot exists);
     * counts and status are Spring's, live.
     */
    public List<Map<String, Object>> adminRows(AuthUser u) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (ChatSession s : sessions.findByCompanyIdOrderByCreatedAtDesc(u.companyId())) {
            Map<String, Object> bundle = analytics.snapshot(s);
            Map<?, ?> row = bundle != null && bundle.get("row") instanceof Map<?, ?> r ? r : Map.of();
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", s.id);
            m.put("alias", s.alias);
            m.put("category", row.get("category") != null ? row.get("category") : s.scenarioId);
            m.put("scenario_id", s.scenarioId);
            m.put("axis", row.get("axis"));
            m.put("choice", row.get("choice"));
            m.put("condition", row.get("condition"));
            m.put("status", s.status);
            m.put("milestone_idx", s.milestoneIdx);
            m.put("messages", messages.countBySessionId(s.id));
            m.put("observations", observations.countBySessionId(s.id));
            m.put("report_status", s.reportStatus);
            m.put("created_at", epoch(s.createdAt));
            m.put("analytics_status", analytics.status(s, bundle));
            rows.add(m);
        }
        return rows;
    }

    public Map<String, Object> taskMap(AiTask t) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", t.id); m.put("type", t.type); m.put("status", t.status); m.put("sessionId", t.sessionId);
        m.put("attempts", t.attempts); m.put("error", t.error); m.put("createdAt", t.createdAt); m.put("updatedAt", t.updatedAt);
        m.put("result", json.any(t.resultJson)); m.put("trace", json.any(t.traceJson));
        return m;
    }

    // ---------------------------------------------------------------- helpers
    private void saveAgentMessage(String id, Map<String, Object> m, int idx) {
        if (m == null) return;
        if (m.get("idx") != null && num(m.get("idx")) != idx)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "메시지 순서가 맞지 않아요 (expected " + idx + ").");
        String speaker = str(m.get("speaker"));
        if (!"lead".equals(speaker) && !"peer".equals(speaker)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "에이전트는 팀원 메시지만 저장할 수 있어요.");
        Message msg = new Message();
        msg.sessionId = id; msg.idx = idx; msg.speaker = speaker; msg.text = str(m.get("text")); msg.milestone = str(m.get("milestone"));
        msg.sourcesJson = json.write(m.get("sources"));
        messages.save(msg);
    }

    public Map<String, Object> messageMap(Message m) {
        Map<String, Object> o = new LinkedHashMap<>();
        o.put("idx", m.idx); o.put("speaker", m.speaker); o.put("text", m.text); o.put("milestone", m.milestone);
        o.put("ts", epoch(m.createdAt));
        if (m.choice != null) o.put("choice", m.choice);
        Object src = json.any(m.sourcesJson);
        if (src != null) o.put("sources", src);
        return o;
    }

    private Map<String, Object> obsMap(Observation o) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", o.obsKey); m.put("competency", o.competency); m.put("milestone", o.milestone); m.put("behavior", o.behavior);
        m.put("quote", o.quote); m.put("signal", o.signal); m.put("msg_idx", o.msgIdx);
        return m;
    }

    private static double epoch(OffsetDateTime t) { return t.toInstant().toEpochMilli() / 1000.0; }
    private static String str(Object o) { return o == null ? null : String.valueOf(o); }
    private static int num(Object o) { return o instanceof Number n ? n.intValue() : Integer.parseInt(String.valueOf(o)); }

    private static String newId() {
        byte[] b = new byte[6];
        RNG.nextBytes(b);
        return HexFormat.of().formatHex(b);
    }
}
