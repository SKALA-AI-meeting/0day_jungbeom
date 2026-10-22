package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.security.AuthUser;
import dev.dayzero.backend.task.InboxContributor;
import dev.dayzero.backend.task.InboxItems;
import dev.dayzero.backend.task.TaskHandlers;
import java.util.*;
import org.springframework.stereotype.Service;

/**
 * Human-in-the-loop issue checklist: everything the agent asked a person to decide (paused tasks, item built by the
 * task's handler), plus loops the agent could not close itself (InboxContributor beans: REVIEW_ERROR accounts,
 * REPORT_FAILED sessions). Shown to the admin right after login, before the dashboard. Every item carries
 * `actions: {approve, reject}` button labels.
 */
@Service
public class InboxService {
    private final TaskService tasks;
    private final TaskHandlers handlers;
    private final List<InboxContributor> contributors;
    private final Json json;

    public InboxService(TaskService tasks, TaskHandlers handlers, List<InboxContributor> contributors, Json json) {
        this.tasks = tasks; this.handlers = handlers; this.contributors = contributors; this.json = json;
    }

    public Map<String, Object> inbox(AuthUser u) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (AiTask t : tasks.waitingApproval(u.companyId())) {
            Map<String, Object> it = handlers.of(t.type).inboxItem(t).orElseGet(() -> InboxItems.approval(t, json, "승인", "반려"));
            it.putIfAbsent("title", "에이전트 승인 요청");
            items.add(it);
        }
        for (InboxContributor c : contributors) items.addAll(c.items(u.companyId()));
        return Map.of("items", items, "count", items.size());
    }

    /** The top-bar badge: how many items inbox() lists, without building them (a REPORT card carries its chart SVGs). */
    public int count(AuthUser u) {
        int n = tasks.waitingApproval(u.companyId()).size();
        for (InboxContributor c : contributors) n += c.items(u.companyId()).size();
        return n;
    }
}
