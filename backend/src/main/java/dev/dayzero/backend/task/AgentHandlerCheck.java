package dev.dayzero.backend.task;

import dev.dayzero.backend.service.AgentClient;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

/**
 * Startup sanity check (non-fatal): every task type Spring can create should have a handler in the agent
 * (GET /agent/handlers), with the same resumable flag. Mismatches are only logged. The agent often starts after
 * Spring (compose), so the list is asked for a few times before the check is skipped.
 */
@Component
public class AgentHandlerCheck {
    private static final Logger log = LoggerFactory.getLogger(AgentHandlerCheck.class);
    private static final long PAUSE_MS = 6_000;

    private final AgentClient agent;
    private final TaskHandlers handlers;
    private final int attempts;

    public AgentHandlerCheck(AgentClient agent, TaskHandlers handlers, @Value("${dayzero.agent-check-attempts:10}") int attempts) {
        this.agent = agent; this.handlers = handlers; this.attempts = Math.max(1, attempts);
    }

    @Async
    @EventListener(ApplicationReadyEvent.class)
    public void check() {
        Optional<List<Map<String, Object>>> served = agent.handlers();
        for (int i = 1; served.isEmpty() && i < attempts; i++) {
            try { Thread.sleep(PAUSE_MS); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
            served = agent.handlers();
        }
        if (served.isEmpty()) {
            log.info("agent handler list not available; skipped the task type check");
            return;
        }
        log.info("agent serves task types {}", served.get().stream().map(h -> h.get("type")).toList());
        Map<String, Object> resumable = new HashMap<>();
        for (Map<String, Object> h : served.get()) resumable.put(String.valueOf(h.get("type")), h.get("resumable"));
        for (String type : handlers.types()) {
            if (!resumable.containsKey(type)) log.warn("task type {} has a Spring handler but the agent does not serve it", type);
            else if (!Objects.equals(resumable.get(type), handlers.of(type).resumable()))
                log.warn("task type {}: resumable differs (spring={}, agent={})", type, handlers.of(type).resumable(), resumable.get(type));
        }
    }
}
