package dev.dayzero.backend.task;

import dev.dayzero.backend.domain.Account;
import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.domain.ChatSession;
import dev.dayzero.backend.service.Json;
import java.util.*;

/** Building blocks of a checklist item, shared by handlers and contributors. */
public final class InboxItems {
    private InboxItems() {}

    /** Button labels: approve = the first-choice action, reject = the other one. */
    public static Map<String, Object> actions(String approve, String reject) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("approve", approve);
        m.put("reject", reject);
        return m;
    }

    /** What every paused task shows: the tool the agent stopped at, why, and what it recommends. */
    public static Map<String, Object> approval(AiTask t, Json json, String approve, String reject) {
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
        it.put("actions", actions(approve, reject));
        return it;
    }

    public static Map<String, Object> subject(Account a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("label", a.nickname);
        m.put("detail", a.email);
        m.put("profile", Map.of("desiredJob", a.desiredJob, "industry", Objects.requireNonNullElse(a.industry, ""), "experienceYears", a.experienceYears,
                "bio", Objects.requireNonNullElse(a.bio, "")));
        return m;
    }

    public static Map<String, Object> subject(ChatSession s) {
        return Map.of("label", s.alias, "detail", s.scenarioId, "sessionId", s.id);
    }
}
