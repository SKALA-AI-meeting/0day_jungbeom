package dev.dayzero.backend.task;

import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.domain.ChatSession;
import dev.dayzero.backend.repo.AiTaskRepository;
import dev.dayzero.backend.repo.ChatSessionRepository;
import java.util.*;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * REPORT_FAILED: a session whose report could not be made. approve = make it again (POST /api/ai/tasks REPORT),
 * reject = dismiss it (POST /api/admin/sessions/{id}/report/dismiss). Either way report_status leaves "failed".
 */
@Component
@Order(20)
public class ReportFailedInbox implements InboxContributor {
    private final ChatSessionRepository sessions;
    private final AiTaskRepository tasks;

    public ReportFailedInbox(ChatSessionRepository sessions, AiTaskRepository tasks) { this.sessions = sessions; this.tasks = tasks; }

    @Override
    public List<Map<String, Object>> items(Long companyId) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (ChatSession s : sessions.findByCompanyIdAndReportStatusOrderByCreatedAtAsc(companyId, "failed")) {
            Optional<AiTask> last = tasks.findBySessionIdAndTypeOrderByCreatedAtDesc(s.id, "REPORT").stream().findFirst();
            Map<String, Object> it = new LinkedHashMap<>();
            it.put("id", "report:" + s.id);
            it.put("kind", "REPORT_FAILED");
            it.put("sessionId", s.id);
            it.put("title", "리포트를 만들지 못했어요");
            it.put("subject", InboxItems.subject(s));
            it.put("reason", last.map(t -> t.error).filter(e -> !e.isBlank()).orElse("원인 미상"));
            it.put("recommendation", "retry");
            it.put("flags", List.of());
            it.put("createdAt", last.map(t -> t.updatedAt).orElse(s.createdAt));
            it.put("actions", InboxItems.actions("다시 만들기", "넘기기"));
            items.add(it);
        }
        return items;
    }
}
