package dev.dayzero.backend.task;

import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.service.AnalyticsService;
import org.springframework.stereotype.Component;

/**
 * ANALYTICS: the agent recomputes a session's admin analytics through analytics-mcp (session_analytics) and stores
 * the snapshot (business.save_analytics -> PUT /internal/sessions/{id}/analytics). Derived data: nothing to approve,
 * not resumable, and hidden from the candidate. Created by an admin (POST /api/ai/tasks, POST /api/admin/analytics/refresh);
 * the rules (admin of the company, a working task is reused) are in AnalyticsService. Every dashboard visit with stale
 * rows can start some, so they stay out of the admin's task history (the session detail lists them per session).
 */
@Component
public class AnalyticsHandler implements TaskHandler {
    @Override public String type() { return AnalyticsService.TYPE; }
    @Override public String threadId(AiTask t) { return "analytics:" + t.sessionId + ":" + t.id; }
    @Override public boolean listedInHistory() { return false; }
}
