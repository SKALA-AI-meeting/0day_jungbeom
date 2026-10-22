package dev.dayzero.backend.task;

import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.repo.ChatSessionRepository;
import dev.dayzero.backend.service.Json;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * REPORT: the agent drafts the report and pauses at save_report until an admin approves publishing it.
 * Mirrors the task into sessions.report_status; a failed report becomes a REPORT_FAILED checklist item.
 * The checklist card carries the draft's figures and charts (analytics-mcp) as the agent sent them.
 */
@Component
public class ReportHandler implements TaskHandler {
    private final ChatSessionRepository sessions;
    private final Json json;

    public ReportHandler(ChatSessionRepository sessions, Json json) { this.sessions = sessions; this.json = json; }

    @Override public String type() { return "REPORT"; }
    @Override public String threadId(AiTask t) { return "report:" + t.sessionId + ":" + t.id; }
    @Override public boolean resumable() { return true; }

    @Override
    public void onApprovalRequired(AiTask t, Map<String, Object> ask) { reportStatus(t, "awaiting_approval"); }

    @Override
    public void onFinished(AiTask t, String status, Map<String, Object> data) {
        // DONE: save_report already set "ready" through the internal API
        if ("REJECTED".equals(status)) reportStatus(t, "rejected");
        if ("FAILED".equals(status)) reportStatus(t, "failed");
    }

    @Override
    public Optional<Map<String, Object>> inboxItem(AiTask t) {
        Map<String, Object> it = InboxItems.approval(t, json, "공개 승인", "반려");
        Map<String, Object> ask = Objects.requireNonNullElseGet(json.map(t.resultJson), Map::of);
        it.put("figures", ask.get("figures"));                     // the numbers the summary is grounded in
        it.put("charts", ask.getOrDefault("charts", List.of()));   // [{chart_id, title, svg}]: shown as <img>, never as HTML
        if (t.sessionId != null) {
            sessions.findById(t.sessionId).ifPresent(s -> {
                it.put("title", "리포트 공개 승인 요청");
                it.put("subject", InboxItems.subject(s));
                it.put("sessionId", s.id);
            });
        }
        return Optional.of(it);
    }

    /** A published report stays "ready" unless a later run fails. */
    private void reportStatus(AiTask t, String status) {
        if (t.sessionId == null) return;
        sessions.findById(t.sessionId).ifPresent(s -> {
            if (!"ready".equals(s.reportStatus) || "failed".equals(status)) { s.reportStatus = status; sessions.save(s); }
        });
    }
}
