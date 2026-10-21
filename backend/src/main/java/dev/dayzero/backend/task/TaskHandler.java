package dev.dayzero.backend.task;

import dev.dayzero.backend.domain.AiTask;
import java.util.Map;
import java.util.Optional;

/**
 * One agent task type on the Spring side (the agent registers the same type in app/handlers.py).
 * TaskService keeps the generic lifecycle (202 -> events -> approval -> DONE / FAILED / REJECTED); a handler adds what
 * is specific to its type. Adding a task type = one TaskHandler bean here + one Handler in the agent.
 */
public interface TaskHandler {
    String type();                                   // START, TURN, REPORT, ACCOUNT_REVIEW, …

    /** LangGraph thread id the agent runs (and resumes) the task on; set once at creation. */
    default String threadId(AiTask t) { return t.type.toLowerCase() + ":" + t.id; }

    /** May the candidate who owns the task's session read it (GET / stream / history)? */
    default boolean candidateVisible() { return false; }

    /** Can the agent's graph pause for a person (APPROVAL_REQUIRED) and resume on the same thread? */
    default boolean resumable() { return false; }

    /** The agent paused at a change tool; `ask` is the APPROVAL_REQUIRED data. */
    default void onApprovalRequired(AiTask t, Map<String, Object> ask) {}

    /** Terminal state reached (DONE | FAILED | REJECTED) — by the agent or the watchdog. Runs in the same transaction. */
    default void onFinished(AiTask t, String status, Map<String, Object> data) {}

    /** Checklist item for a task waiting for approval (empty -> a generic item is shown, so nothing waits unseen). */
    default Optional<Map<String, Object>> inboxItem(AiTask t) { return Optional.empty(); }
}
