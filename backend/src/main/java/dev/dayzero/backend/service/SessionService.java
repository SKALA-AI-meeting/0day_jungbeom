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
 * status transitions, automatic report task on completion, company isolation.
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
    private final Json json;
    private final AppProperties props;

    public SessionService(ChatSessionRepository sessions, InviteRepository invites, MessageRepository messages, ObservationRepository observations,
                          DetectionRepository detections, AiTaskRepository taskRepo, TaskService tasks, AgentClient agent, Json json, AppProperties props) {
        this.sessions = sessions; this.invites = invites; this.messages = messages; this.observations = observations;
        this.detections = detections; this.taskRepo = taskRepo; this.tasks = tasks; this.agent = agent; this.json = json; this.props = props;
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

    @Transactional
    public Map<String, Object> startFromInvite(String token, String alias, String scenarioId) {
        Invite inv = invites.findByToken(token).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "초대 링크를 찾을 수 없어요."));
        String problem = inviteProblem(inv);
        if (problem != null) throw new ResponseStatusException(HttpStatus.GONE, "expired".equals(problem) ? "링크가 만료되었습니다." : "이미 사용한 초대 링크예요.");
        if (agent.scenario(scenarioId) == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "알 수 없는 시나리오예요.");
        ChatSession s = new ChatSession();
        s.id = newId();
        s.company = inv.company;
        s.invite = inv;
        s.alias = (inv.alias != null && !inv.alias.isBlank()) ? inv.alias : alias.strip();
        s.scenarioId = scenarioId;
        sessions.save(s);
        if (!inv.reusable) { inv.usedAt = OffsetDateTime.now(); invites.save(inv); }
        AiTask start = tasks.create("START", s.id, s.company.id, "candidate:" + s.id, Map.of());
        return Map.of("sessionId", s.id, "startTaskId", start.id, "company", s.company.name);
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
        boolean ok = (u.isCandidate() && id.equals(u.sessionId())) || (u.isAdmin() && Objects.equals(u.companyId(), s.company.id));
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
        AiTask t = tasks.create("TURN", sessionId, s.company.id, u.subject(), Map.of("text", m.text, "user_idx", idx, "choice_id", choiceId == null ? "" : choiceId));
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

    private void complete(ChatSession s) {
        s.status = "completed";
        s.endedAt = OffsetDateTime.now();
        sessions.save(s);
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
        ChatSession s = load(id);
        Map<String, Object> st = baseState(s);
        st.put("messages", messages.findBySessionIdOrderByIdxAsc(id).stream().map(this::messageMap).toList());
        st.put("observations", observations.findBySessionIdOrderByIdAsc(id).stream().map(this::obsMap).toList());
        Map<String, Object> det = new LinkedHashMap<>();
        for (Detection d : detections.findBySessionId(id)) det.put(String.valueOf(d.msgIdx), json.any(d.docJson));
        st.put("detections", det);
        st.put("report", json.any(s.reportJson));
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
        return sessions.findByConditionJsonIsNotNull().stream().map(s -> json.map(s.conditionJson)).toList();
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> init(String id, Map<String, Object> body) {
        ChatSession s = load(id);
        if (messages.countBySessionId(id) > 0) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 시작된 세션이에요.");
        s.conditionJson = json.write(body.get("condition"));
        Map<String, Object> msg = (Map<String, Object>) body.get("message");
        saveAgentMessage(id, msg, 0);
        s.milestoneLogJson = json.write(List.of(Map.of("key", MILESTONES.get(0), "entered_idx", 0, "ts", epoch(OffsetDateTime.now()))));
        sessions.save(s);
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
        sessions.save(s);
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
    }

    @Transactional
    public void saveReport(String id, Object report) {
        ChatSession s = load(id);
        if (!"completed".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "끝나지 않은 세션에는 리포트를 저장할 수 없어요.");
        s.reportJson = json.write(report);
        s.reportStatus = "ready";
        sessions.save(s);
    }

    // ---------------------------------------------------------------- views (computed by the agent's catalog)
    public Map<String, Object> candidateView(AuthUser u, String id) {
        authorized(id, u);
        Map<String, Object> v = new LinkedHashMap<>(agent.view("candidate", state(id)));
        v.put("busy", !taskRepo.findBySessionIdAndTypeAndStatusIn(id, "TURN", TaskService.ACTIVE).isEmpty()
                || !taskRepo.findBySessionIdAndTypeAndStatusIn(id, "START", TaskService.ACTIVE).isEmpty());
        return v;
    }

    public Map<String, Object> adminView(AuthUser u, String id) {
        authorized(id, u);
        Map<String, Object> v = new LinkedHashMap<>(agent.view("admin", state(id)));
        List<Map<String, Object>> recent = new ArrayList<>();
        for (AiTask t : taskRepo.findBySessionIdOrderByCreatedAtDesc(id)) {
            recent.add(taskMap(t));
            if ("REPORT".equals(t.type) && "WAITING_APPROVAL".equals(t.status) && !v.containsKey("pending_approval"))
                v.put("pending_approval", Map.of("taskId", t.id, "draft", Objects.requireNonNullElse(json.any(t.resultJson), Map.of())));
        }
        v.put("tasks", recent);
        return v;
    }

    public List<Map<String, Object>> adminRows(AuthUser u) {
        List<Map<String, Object>> states = new ArrayList<>();
        for (ChatSession s : sessions.findByCompanyIdOrderByCreatedAtDesc(u.companyId())) {
            Map<String, Object> st = baseState(s);
            st.put("message_count", messages.countBySessionId(s.id));
            st.put("observation_count", observations.countBySessionId(s.id));
            states.add(st);
        }
        return states.isEmpty() ? List.of() : agent.rows(states);
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
