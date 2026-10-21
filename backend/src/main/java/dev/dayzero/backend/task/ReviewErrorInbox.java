package dev.dayzero.backend.task;

import dev.dayzero.backend.domain.Account;
import dev.dayzero.backend.repo.AccountRepository;
import dev.dayzero.backend.service.Json;
import java.util.*;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/** ACCOUNT_REVIEW_ERROR: the agent could not finish an account review -> an admin decides directly. */
@Component
@Order(10)
public class ReviewErrorInbox implements InboxContributor {
    private final AccountRepository accounts;
    private final Json json;

    public ReviewErrorInbox(AccountRepository accounts, Json json) { this.accounts = accounts; this.json = json; }

    @Override
    public List<Map<String, Object>> items(Long companyId) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (Account a : accounts.findByCompanyIdAndStatus(companyId, "REVIEW_ERROR")) {
            Map<String, Object> it = new LinkedHashMap<>();
            Map<String, Object> r = Objects.requireNonNullElseGet(json.map(a.reviewJson), Map::of);
            it.put("id", "account:" + a.id);
            it.put("kind", "ACCOUNT_REVIEW_ERROR");
            it.put("accountId", a.id);
            it.put("title", "에이전트가 끝내지 못한 계정 검토");
            it.put("subject", InboxItems.subject(a));
            it.put("reason", "에이전트 검토가 실패했어요: " + r.getOrDefault("error", "원인 미상") + ". 직접 확인해 주세요.");
            it.put("recommendation", "manual");
            it.put("flags", List.of());
            it.put("createdAt", a.createdAt);
            it.put("actions", InboxItems.actions("직접 승인", "직접 반려"));
            items.add(it);
        }
        return items;
    }
}
