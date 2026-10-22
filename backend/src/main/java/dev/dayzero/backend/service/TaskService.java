package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.domain.TaskEvent;
import dev.dayzero.backend.repo.AiTaskRepository;
import dev.dayzero.backend.repo.ChatSessionRepository;
import dev.dayzero.backend.repo.TaskEventRepository;
import dev.dayzero.backend.security.AuthUser;
import dev.dayzero.backend.task.TaskHandler;
import dev.dayzero.backend.task.TaskHandlers;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.server.ResponseStatusException;

/**
 * Task lifecycle: create (202) -> dispatch -> progress events -> approval -> DONE / FAILED / REJECTED.
 * Generic over task types; what a type adds (visibility, resume, status mirrors, checklist items) is its TaskHandler.
 */
@Service
public class TaskService {
    private static final Logger log = LoggerFactory.getLogger(TaskService.class);
    public static final Set<String> ACTIVE = Set.of("QUEUED", "RUNNING", "WAITING_APPROVAL");

    private final AiTaskRepository tasks;
    private final TaskEventRepository events;
    private final ChatSessionRepository sessions;
    private final SseHub hub;
    private final TaskDispatcher dispatcher;
    private final Json json;
    private final Map<String, AtomicInteger> seq = new ConcurrentHashMap<>();
    private final ApplicationEventPublisher publisher;
    private final TaskHandlers handlers;

    public TaskService(AiTaskRepository tasks, TaskEventRepository events, ChatSessionRepository sessions, SseHub hub, TaskDispatcher dispatcher, Json json,
                       ApplicationEventPublisher publisher, TaskHandlers handlers) {
        this.tasks = tasks; this.events = events; this.sessions = sessions; this.hub = hub; this.dispatcher = dispatcher; this.json = json; this.publisher = publisher;
        this.handlers = handlers;
    }

    @Transactional
    public AiTask create(String type, String sessionId, Long companyId, String createdBy, Map<String, Object> payload) {
        return create(type, sessionId, companyId, null, createdBy, payload);
    }

    @Transactional
    public AiTask create(String type, String sessionId, Long companyId, Long accountId, String createdBy, Map<String, Object> payload) {
        handlers.require(type); // unknown types are rejected before anything is stored
        AiTask t = new AiTask();
        t.id = UUID.randomUUID().toString();
        t.type = type;
        t.sessionId = sessionId;
        t.companyId = companyId;
        t.accountId = accountId;
        t.createdBy = createdBy;
        t.threadId = handlers.of(type).threadId(t);
        t.payloadJson = json.write(payload);
        tasks.save(t);
        afterCommit(() -> send(t, "RUN", null));
        return t;
    }

    public AiTask get(String id) {
        return tasks.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "작업을 찾을 수 없어요."));
    }

    public void authorize(AiTask t, AuthUser u) {
        if (!canSee(t, u)) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "이 작업에 접근할 수 없어요.");
    }

    /**
     * Admin: any task of their company. Candidate: tasks of their own sessions whose handler is candidateVisible
     * (START, TURN) — a review's flags and an admin's notes are for the company.
     */
    public boolean canSee(AiTask t, AuthUser u) {
        if (u.isAdmin()) return Objects.equals(u.companyId(), t.companyId);
        if (!u.isCandidate() || u.accountId() == null) return false;
        if (!handlers.of(t.type).candidateVisible() || t.sessionId == null) return false;
        return sessions.findById(t.sessionId).map(s -> s.account != null && Objects.equals(s.account.id, u.accountId())).orElse(false);
    }

    /** Human-in-the-loop inbox: every task paused at a change tool, oldest first. */
    public List<AiTask> waitingApproval(Long companyId) {
        return tasks.findByCompanyIdAndStatusOrderByCreatedAtAsc(companyId, "WAITING_APPROVAL");
    }

    public List<SseHub.Ev> replay(String taskId) {
        return events.findByTaskIdOrderBySeqAsc(taskId).stream().map(e -> new SseHub.Ev(e.seq, e.type, json.any(e.dataJson))).toList();
    }

    /**
     * "My history": a candidate sees the tasks of their own session; an admin sees the company's tasks (system-made ones
     * included), except the types whose handler is not listedInHistory (derived ANALYTICS refreshes).
     */
    public List<AiTask> mine(AuthUser u) {
        if (u.isAdmin()) {
            List<String> unlisted = handlers.types().stream().filter(type -> !handlers.of(type).listedInHistory()).toList();
            return unlisted.isEmpty() ? tasks.findTop30ByCompanyIdOrderByCreatedAtDesc(u.companyId())
                    : tasks.findTop30ByCompanyIdAndTypeNotInOrderByCreatedAtDesc(u.companyId(), unlisted);
        }
        List<AiTask> out = new ArrayList<>(tasks.findTop30ByCreatedByOrderByCreatedAtDesc(u.subject()));
        out.removeIf(t -> !handlers.of(t.type).candidateVisible());
        if (u.accountId() != null) {
            for (var s : sessions.findByAccountIdOrderByCreatedAtDesc(u.accountId()))
                for (AiTask t : tasks.findBySessionIdOrderByCreatedAtDesc(s.id))
                    if (handlers.of(t.type).candidateVisible() && out.stream().noneMatch(x -> x.id.equals(t.id))) out.add(t);
        }
        out.sort(Comparator.comparing((AiTask x) -> x.createdAt).reversed());
        return out.size() > 30 ? out.subList(0, 30) : out;
    }

    /**
     * Agent -> Spring progress events (batched). Updates task status and relays to subscribers.
     * A finished task stays finished: late events (e.g. after the watchdog closed it) are dropped.
     */
    @Transactional
    @SuppressWarnings("unchecked")
    public void onEvents(String taskId, List<Map<String, Object>> batch) {
        AiTask t = get(taskId);
        TaskHandler h = handlers.of(t.type);
        if (t.finished()) { // checked before the counter map so a late batch cannot leave an entry behind
            seq.remove(taskId);
            log.info("dropping {} events for finished task {} ({})", batch.size(), taskId, t.status);
            return;
        }
        AtomicInteger counter = seq.computeIfAbsent(taskId, k -> new AtomicInteger(events.countByTaskId(k)));
        for (Map<String, Object> ev : batch) {
            if (t.finished()) {
                log.info("dropping {} event for finished task {} ({})", ev.get("type"), taskId, t.status);
                continue;
            }
            String type = String.valueOf(ev.get("type"));
            Object data = ev.get("data");
            if ("APPROVAL_REQUIRED".equals(type) && !h.resumable()) { // nothing could resume it: close the loop instead of parking it forever
                type = "FAILED";
                data = Map.of("error", t.type + " 작업은 승인 후 이어서 진행할 수 없어요.");
            }
            Map<String, Object> d = data instanceof Map ? (Map<String, Object>) data : Map.of();
            appendTrace(t, d.get("trace"));  // one entry per agent run (a report task has two: draft + resume)
            if (d.containsKey("trace")) { // kept on the task (admin GET /api/ai/tasks/{id}); not in events a candidate can stream
                d = new LinkedHashMap<>(d);
                d.remove("trace");
                data = d;
            }
            int n = counter.incrementAndGet();
            if (!"TOKEN".equals(type)) {
                TaskEvent e = new TaskEvent();
                e.taskId = taskId; e.seq = n; e.type = type; e.dataJson = json.write(data);
                events.save(e);
            }
            boolean terminal = false;
            switch (type) {
                case "APPROVAL_REQUIRED" -> { t.status = "WAITING_APPROVAL"; t.resultJson = json.write(data); h.onApprovalRequired(t, d); }
                case "DONE" -> {
                    // approved=false: the person declined the change, nothing was applied (REJECTED, e.g. an unpublished report) —
                    // unless their answer was itself the decision the task records (data.decision, e.g. a rejected account: DONE)
                    boolean rejected = Boolean.FALSE.equals(d.get("approved")) && !d.containsKey("decision");
                    t.status = rejected ? "REJECTED" : "DONE";
                    t.resultJson = json.write(data);
                    if (d.get("attempt") instanceof Number a) t.attempts = a.intValue();
                    terminal = true;
                }
                case "FAILED" -> {
                    t.status = "FAILED";
                    t.error = String.valueOf(d.getOrDefault("error", "unknown"));
                    if (d.get("attempt") instanceof Number a) t.attempts = a.intValue();
                    terminal = true;
                }
                default -> { if ("QUEUED".equals(t.status)) t.status = "RUNNING"; }
            }
            t.updatedAt = OffsetDateTime.now();
            hub.publish(taskId, new SseHub.Ev(n, type, data), terminal);
            if (terminal) {
                seq.remove(taskId);
                tasks.save(t);
                publisher.publishEvent(new TaskFinishedEvent(t, t.status, d)); // end of the loop -> TaskHandler.onFinished
            }
        }
        tasks.save(t);
    }

    /** Human-in-the-loop: resume the agent's paused graph on the same thread id. */
    @Transactional
    public AiTask approve(String taskId, AuthUser u, boolean approved, String comment) {
        AiTask t = get(taskId);
        if (!u.isAdmin() || !Objects.equals(u.companyId(), t.companyId)) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "승인 권한이 없어요.");
        if (!handlers.of(t.type).resumable()) throw new ResponseStatusException(HttpStatus.CONFLICT, "승인으로 이어서 진행하는 작업이 아니에요.");
        if (!"WAITING_APPROVAL".equals(t.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "승인을 기다리는 작업이 아니에요.");
        t.status = "QUEUED";
        t.updatedAt = OffsetDateTime.now();
        tasks.save(t);
        Map<String, Object> resume = new HashMap<>();
        resume.put("approved", approved);
        resume.put("comment", comment == null ? "" : comment);
        resume.put("by", u.subject());
        afterCommit(() -> send(t, "RESUME", resume));
        return t;
    }

    @Transactional
    public void fail(String taskId, String error) {
        onEvents(taskId, List.of(Map.of("type", "FAILED", "data", Map.of("error", error))));
    }

    /**
     * Watchdog: fail the task if it is still QUEUED / RUNNING with no progress since `cutoff` (re-checked here, in the
     * same transaction, so a task that moved on meanwhile is left alone). The FAILED event reaches SSE subscribers and
     * TaskFinishedEvent runs the handler hooks, exactly as an agent-reported failure would.
     */
    @Transactional
    public boolean expire(String taskId, OffsetDateTime cutoff, String error) {
        AiTask t = get(taskId);
        if (!Set.of("QUEUED", "RUNNING").contains(t.status) || !t.updatedAt.isBefore(cutoff)) return false;
        onEvents(taskId, List.of(Map.of("type", "FAILED", "data", Map.of("error", error, "stale", true))));
        return true;
    }

    private void appendTrace(AiTask t, Object trace) {
        if (trace == null) return;
        List<Object> all = new ArrayList<>(json.list(t.traceJson));
        all.add(trace);
        t.traceJson = json.write(all);
    }

    private void send(AiTask t, String mode, Map<String, Object> resume) {
        Map<String, Object> m = new HashMap<>();
        m.put("taskId", t.id);
        m.put("type", t.type);
        m.put("mode", mode);
        m.put("sessionId", t.sessionId);
        m.put("accountId", t.accountId);
        m.put("threadId", t.threadId);
        m.put("payload", json.map(t.payloadJson));
        if (resume != null) m.put("resume", resume);
        try {
            dispatcher.dispatch(m);
        } catch (Exception e) {
            log.warn("dispatch failed for task {}: {}", t.id, e.toString());
            fail(t.id, "Agent 서버에 작업을 전달하지 못했어요: " + e.getClass().getSimpleName());
        }
    }

    private static void afterCommit(Runnable r) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override public void afterCommit() { r.run(); }
            });
        } else {
            r.run();
        }
    }
}
