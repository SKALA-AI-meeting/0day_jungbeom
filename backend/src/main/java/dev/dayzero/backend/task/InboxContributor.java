package dev.dayzero.backend.task;

import java.util.List;
import java.util.Map;

/**
 * Checklist items that are not a paused task: loops the agent could not close itself (an account review that failed,
 * a report that could not be made). Order with @Order; items keep the inbox item shape incl. `actions`.
 */
public interface InboxContributor {
    List<Map<String, Object>> items(Long companyId);
}
