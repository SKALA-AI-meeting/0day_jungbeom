package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.Account;
import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.repo.AccountRepository;
import dev.dayzero.backend.repo.ChatSessionRepository;
import dev.dayzero.backend.security.AuthUser;
import java.util.*;
import org.springframework.stereotype.Service;

/**
 * Human-in-the-loop issue checklist: everything the agent asked a person to decide, plus loops the agent
 * could not close itself (REVIEW_ERROR accounts). Shown to the admin right after login, before the dashboard.
 */
@Service
public class InboxService {
    private final TaskService tasks;
    private final AccountRepository accounts;
    private final ChatSessionRepository sessions;
    private final Json json;

    public InboxService(TaskService tasks, AccountRepository accounts, ChatSessionRepository sessions, Json json) {
        this.tasks = tasks; this.accounts = accounts; this.sessions = sessions; this.json = json;
    }

    public Map<String, Object> inbox(AuthUser u) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (AiTask t : tasks.waitingApproval(u.companyId())) {
            Map<String, Object> ask = Objects.requireNonNullElseGet(json.map(t.resultJson), Map::of);
            Map<String, Object> it = new LinkedHashMap<>();
            it.put("id", "task:" + t.id);
            it.put("taskId", t.id);
            it.put("kind", t.type);
            it.put("tool", ask.get("tool"));
            it.put("reason", ask.get("reason"));
            it.put("recommendation", ask.get("recommendation"));
            it.put("flags", ask.getOrDefault("flags", List.of()));
            it.put("checks", ask.getOrDefault("checks", List.of()));
            it.put("draft", ask.get("draft"));
            it.put("createdAt", t.createdAt);
            if ("ACCOUNT_REVIEW".equals(t.type) && t.accountId != null) {
                accounts.findById(t.accountId).ifPresent(a -> { it.put("title", "지원자 계정 승인 요청"); it.put("subject", subject(a)); it.put("accountId", a.id); });
            } else if (t.sessionId != null) {
                sessions.findById(t.sessionId).ifPresent(s -> {
                    it.put("title", "리포트 공개 승인 요청");
                    it.put("subject", Map.of("label", s.alias, "detail", s.scenarioId, "sessionId", s.id));
                    it.put("sessionId", s.id);
                });
            }
            items.add(it);
        }
        for (Account a : accounts.findByCompanyIdAndStatus(u.companyId(), "REVIEW_ERROR")) {
            Map<String, Object> it = new LinkedHashMap<>();
            Map<String, Object> r = Objects.requireNonNullElseGet(json.map(a.reviewJson), Map::of);
            it.put("id", "account:" + a.id);
            it.put("kind", "ACCOUNT_REVIEW_ERROR");
            it.put("accountId", a.id);
            it.put("title", "에이전트가 끝내지 못한 계정 검토");
            it.put("subject", subject(a));
            it.put("reason", "에이전트 검토가 실패했어요: " + r.getOrDefault("error", "원인 미상") + ". 직접 확인해 주세요.");
            it.put("recommendation", "manual");
            it.put("flags", List.of());
            it.put("createdAt", a.createdAt);
            items.add(it);
        }
        return Map.of("items", items, "count", items.size());
    }

    private Map<String, Object> subject(Account a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("label", a.nickname);
        m.put("detail", a.email);
        m.put("profile", Map.of("desiredJob", a.desiredJob, "industry", Objects.requireNonNullElse(a.industry, ""), "experienceYears", a.experienceYears,
                "bio", Objects.requireNonNullElse(a.bio, "")));
        return m;
    }
}
