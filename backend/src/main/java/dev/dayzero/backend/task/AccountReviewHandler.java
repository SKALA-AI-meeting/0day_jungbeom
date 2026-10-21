package dev.dayzero.backend.task;

import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.repo.AccountRepository;
import dev.dayzero.backend.service.Json;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * ACCOUNT_REVIEW: the agent screens a new account and decides clean cases itself; ambiguous ones pause for an admin.
 * Hidden from the candidate (flags and admin notes are for the company; the candidate follows /api/me/review/stream).
 */
@Component
public class AccountReviewHandler implements TaskHandler {
    private final AccountRepository accounts;
    private final Json json;

    public AccountReviewHandler(AccountRepository accounts, Json json) { this.accounts = accounts; this.json = json; }

    @Override public String type() { return "ACCOUNT_REVIEW"; }
    @Override public String threadId(AiTask t) { return "account:" + t.accountId + ":" + t.id; }
    @Override public boolean resumable() { return true; }

    /** Loop closure: a review task that ends without a decision hands the account to an admin (REVIEW_ERROR). */
    @Override
    public void onFinished(AiTask t, String status, Map<String, Object> data) {
        if (t.accountId == null || "DONE".equals(status)) return;
        accounts.findById(t.accountId).ifPresent(a -> {
            if (!"PENDING_REVIEW".equals(a.status)) return;
            a.status = "REVIEW_ERROR";
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("error", t.error == null ? "에이전트 검토가 끝나지 않았어요." : t.error);
            r.put("task_id", t.id);
            a.reviewJson = json.write(r);
            accounts.save(a);
        });
    }

    @Override
    public Optional<Map<String, Object>> inboxItem(AiTask t) {
        Map<String, Object> it = InboxItems.approval(t, json, "승인", "반려");
        if (t.accountId != null) {
            accounts.findById(t.accountId).ifPresent(a -> {
                it.put("title", "지원자 계정 승인 요청");
                it.put("subject", InboxItems.subject(a));
                it.put("accountId", a.id);
            });
        }
        return Optional.of(it);
    }
}
