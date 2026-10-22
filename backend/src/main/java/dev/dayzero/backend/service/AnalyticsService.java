package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.domain.ChatSession;
import dev.dayzero.backend.repo.AiTaskRepository;
import dev.dayzero.backend.repo.ChatSessionRepository;
import dev.dayzero.backend.security.AuthUser;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Admin analytics snapshot (api-contract §5). analytics-mcp computes the bundle (timeline, heatmap, TKI, agreement,
 * planted checkpoints, figures), the agent stores it through business.save_analytics, and the admin screens read only
 * what is stored here — never the agent, synchronously. sessions.state_rev counts the changes that affect analytics;
 * a snapshot computed from an older rev is stale. Recomputing is an ANALYTICS task: admin only, and a session's task
 * that is still working is handed out again instead of starting a second one.
 */
@Service
public class AnalyticsService {
    public static final String TYPE = "ANALYTICS";
    /** An ANALYTICS task still working (it is not resumable, so it never waits for a person). */
    public static final Set<String> WORKING = Set.of("QUEUED", "RUNNING");
    public static final int MAX_REFRESH = 20;

    private final ChatSessionRepository sessions;
    private final AiTaskRepository taskRepo;
    private final TaskService tasks;
    private final Json json;

    public AnalyticsService(ChatSessionRepository sessions, AiTaskRepository taskRepo, TaskService tasks, Json json) {
        this.sessions = sessions; this.taskRepo = taskRepo; this.tasks = tasks; this.json = json;
    }

    // ---------------------------------------------------------------- read side (admin screens)
    /** The stored bundle, or null. */
    public Map<String, Object> snapshot(ChatSession s) {
        return json.map(s.analyticsJson);
    }

    /** missing (no snapshot) | stale (computed from an older state_rev) | fresh. */
    public String status(ChatSession s, Map<String, Object> bundle) {
        if (bundle == null) return "missing";
        return revOf(bundle) < s.stateRev ? "stale" : "fresh";
    }

    /** `{id, status}` of a task while it is a working ANALYTICS task (admin detail's analytics_task), else null. */
    public static Map<String, Object> working(AiTask t) {
        if (!TYPE.equals(t.type) || !WORKING.contains(t.status)) return null;
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", t.id);
        m.put("status", t.status);
        return m;
    }

    // ---------------------------------------------------------------- store (internal PUT from business-mcp)
    /**
     * Monotonic: stored only when the bundle's source.state_rev is at least the stored one's, so a slow run cannot
     * overwrite a newer snapshot. The row lock serialises two saves of the same session. Storing is not a change
     * that affects analytics, so state_rev stays.
     */
    @Transactional
    public boolean store(String id, Map<String, Object> bundle) {
        ChatSession s = sessions.findForUpdate(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "세션을 찾을 수 없어요."));
        long rev = revOf(bundle);
        if (rev < 0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "source.state_rev(0 이상의 정수)가 필요해요.");
        if (!(bundle.get("version") instanceof Integer v) || v != 1) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "분석 번들 version 1만 받아요.");
        if (!id.equals(bundle.get("session_id"))) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "다른 세션의 분석이에요.");
        if (!shaped(bundle)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "분석 번들에 row·heatmap·figures(객체)와 timeline·charts(비어 있지 않은 목록)가 있어야 해요.");
        if (rev > s.stateRev) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "세션보다 앞선 state_rev예요 (" + rev + " > " + s.stateRev + ").");
        Map<String, Object> stored = snapshot(s);
        if (stored != null && rev < revOf(stored)) return false;
        sessions.storeAnalytics(id, json.write(bundle), OffsetDateTime.now());
        return true;
    }

    // ---------------------------------------------------------------- ANALYTICS tasks
    /** POST /api/ai/tasks {type: ANALYTICS}: admin of the session's company; a working task is reused. */
    @Transactional
    public Map<String, Object> request(AuthUser u, String sessionId) {
        if (!u.isAdmin()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "분석은 관리자만 요청할 수 있어요.");
        if (sessionId == null || sessionId.isBlank()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "분석할 세션을 정해 주세요.");
        ChatSession s = sessions.findForUpdate(sessionId).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "세션을 찾을 수 없어요."));
        if (!Objects.equals(u.companyId(), s.company.id)) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "이 세션에 접근할 수 없어요.");
        Optional<AiTask> running = running(s.id);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("taskId", running.map(t -> t.id).orElseGet(() -> create(s, u).id));
        out.put("reused", running.isPresent());
        return out;
    }

    /**
     * POST /api/admin/analytics/refresh: an ANALYTICS task (new or reused) for each listed session of the admin's
     * company whose snapshot is missing or stale. Fresh sessions, other companies' and unknown ids are skipped.
     */
    @Transactional
    public List<Map<String, Object>> refresh(AuthUser u, List<String> sessionIds) {
        if (!u.isAdmin()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "분석은 관리자만 요청할 수 있어요.");
        if (sessionIds == null || sessionIds.size() > MAX_REFRESH)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "세션은 한 번에 " + MAX_REFRESH + "개까지 요청할 수 있어요.");
        List<String> ids = sessionIds.stream().filter(id -> id != null && !id.isBlank()).distinct().toList();
        Map<String, String> started = new HashMap<>();
        for (String id : ids.stream().sorted().toList()) { // rows locked in one order: two refreshes never wait on each other in a cycle
            sessions.findForUpdate(id)
                    .filter(s -> Objects.equals(u.companyId(), s.company.id))
                    .filter(s -> !"fresh".equals(status(s, snapshot(s))))
                    .ifPresent(s -> started.put(s.id, running(s.id).map(t -> t.id).orElseGet(() -> create(s, u).id)));
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (String id : ids) {
            if (started.containsKey(id)) out.add(Map.of("sessionId", id, "taskId", started.get(id)));
        }
        return out;
    }

    // ---------------------------------------------------------------- helpers
    /** The caller holds the session's row lock, so a task created meanwhile by another request is already visible. */
    private Optional<AiTask> running(String sessionId) {
        return taskRepo.findBySessionIdAndTypeAndStatusIn(sessionId, TYPE, WORKING).stream()
                .max(Comparator.comparing((AiTask t) -> t.createdAt));
    }

    private AiTask create(ChatSession s, AuthUser u) {
        return tasks.create(TYPE, s.id, s.company.id, u.subject(), Map.of());
    }

    /** source.state_rev of a bundle; -1 when it is missing or not a non-negative JSON integer (8.0 and "8" are refused). */
    private static long revOf(Map<String, Object> bundle) {
        if (bundle == null || !(bundle.get("source") instanceof Map<?, ?> src)) return -1;
        Object n = src.get("state_rev");
        long rev = n instanceof Integer i ? i : n instanceof Long l ? l : -1;
        return Math.max(rev, -1);
    }

    /**
     * The parts the admin screens draw from are there (business-mcp checks the same before calling): a bundle with
     * only a rev would otherwise be stored and make the session look fresh with empty charts.
     */
    private static boolean shaped(Map<String, Object> bundle) {
        for (String k : List.of("row", "heatmap", "figures")) if (!(bundle.get(k) instanceof Map<?, ?>)) return false;
        for (String k : List.of("timeline", "charts")) if (!(bundle.get(k) instanceof List<?> l) || l.isEmpty()) return false;
        return true;
    }
}
