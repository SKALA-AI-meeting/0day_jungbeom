package dev.dayzero.backend;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.repo.AiTaskRepository;
import dev.dayzero.backend.seed.DemoSeeder;
import dev.dayzero.backend.service.AgentClient;
import dev.dayzero.backend.service.TaskDispatcher;
import dev.dayzero.backend.service.TaskService;
import dev.dayzero.backend.task.TaskHandlers;
import dev.dayzero.backend.task.TaskWatchdog;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class BackendFlowTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper om;
    @Autowired TaskDispatcher dispatcher;
    @Autowired AiTaskRepository taskRepo;
    @Autowired TaskService taskService;
    @Autowired TaskHandlers handlers;
    @Autowired TaskWatchdog watchdog;
    @MockitoBean AgentClient agent;

    static final RequestPostProcessor INTERNAL_PORT = r -> { r.setLocalPort(8081); return r; };

    @BeforeEach
    void stubAgent() {
        when(agent.scenario(anyString())).thenAnswer(i -> "nope".equals(i.getArgument(0)) ? null : Map.of("id", i.getArgument(0)));
        when(agent.view(anyString(), anyMap())).thenAnswer(i -> Map.of("kind", i.getArgument(0), "state", i.getArgument(1)));
    }

    JsonNode body(MockHttpServletRequestBuilder b, int status) throws Exception {
        String s = mvc.perform(b).andExpect(status().is(status)).andReturn().getResponse().getContentAsString();
        return s.isBlank() ? null : om.readTree(s);
    }

    MockHttpServletRequestBuilder json(MockHttpServletRequestBuilder b, Object o) throws Exception {
        return b.contentType(MediaType.APPLICATION_JSON).content(om.writeValueAsString(o));
    }

    MockHttpServletRequestBuilder internal(MockHttpServletRequestBuilder b) {
        return b.with(INTERNAL_PORT).header("X-Internal-Key", "test-internal-key");
    }

    String adminToken() throws Exception {
        return body(json(post("/api/auth/login"), Map.of("email", DemoSeeder.EMAIL, "password", DemoSeeder.PASSWORD)), 200).get("token").asText();
    }

    private static int seqNo = 0;

    /** Candidate signup -> (agent) auto-approve via internal API -> ACTIVE. Returns "accountId|token|reviewTaskId". */
    String activeCandidate() throws Exception {
        JsonNode r = body(json(post("/api/auth/candidate/signup"), Map.of("inviteToken", "demo", "email", "cand" + (++seqNo) + "@test.dev", "password", "cand-pass-123",
                "nickname", "지원자" + seqNo, "desiredJob", "pm", "experienceYears", 1, "consent", true)), 201);
        long aid = r.get("account").get("id").asLong();
        body(internal(json(post("/internal/accounts/" + aid + "/decision"), Map.of("decision", "approved", "basis", "auto_clean", "review", Map.of("checks", List.of())))), 200);
        return aid + "|" + r.get("token").asText() + "|" + r.get("reviewTaskId").asText();
    }

    String startSession() throws Exception {
        return startSession(null);
    }

    /** Session through START (init + DONE); `artifacts` is what the agent seeds (null = none). Returns "sessionId|token". */
    String startSession(List<Map<String, Object>> artifacts) throws Exception {
        String[] c = activeCandidate().split("\\|");
        String tok = c[1];
        JsonNode s = body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.pm.fintech")).header("Authorization", "Bearer " + tok), 201);
        String sid = s.get("sessionId").asText();
        Map<String, Object> init = new HashMap<>(Map.of("condition", Map.of("stratum", "V2", "lead", "competing", "peer", "avoiding"),
                "message", Map.of("idx", 0, "speaker", "lead", "text", "시작할게요", "milestone", "communicate")));
        if (artifacts != null) init.put("artifacts", artifacts);
        body(internal(json(post("/internal/sessions/" + sid + "/init"), init)), 200);
        doneAll(sid, "START");
        return sid + "|" + tok;
    }

    static final String DESIGN_BODY = "# 재참여 개선 기획\n목표: 7일 재방문 $+3\\%p$\n범위: 신규 가입자 전체\n일정: 2주\n";
    static final String CODE_BODY = "fun score(x: Int): Int {\n    return x / 0\n}";

    /** Two work items as the agent seeds them, incl. the agent-only checkpoints Spring must drop. */
    static List<Map<String, Object>> sampleArtifacts() {
        return List.of(
                Map.of("id", "a1", "kind", "design", "title", "재참여 개선 기획안", "owner", "lead", "status", "검토 중", "summary", "7일 재방문 개선안",
                        "body", DESIGN_BODY, "checkpoints", List.of(Map.of("line", 3, "issue", "범위가 모호한 체크포인트"))),
                Map.of("id", "a2", "kind", "code", "title", "점수 계산", "owner", "peer", "status", "초안", "summary", "점수 함수", "lang", "kotlin",
                        "body", CODE_BODY, "checkpoints", List.of(Map.of("line", 2, "issue", "0으로 나누는 체크포인트"))));
    }

    JsonNode annotate(String sid, String auth, Map<String, Object> req, int status) throws Exception {
        return body(json(post("/api/sessions/" + sid + "/annotations"), req).header("Authorization", auth), status);
    }

    static Map<String, Object> mark(String artifactId, Map<String, Object> anchor, String kind, String text) {
        Map<String, Object> m = new HashMap<>();
        m.put("artifactId", artifactId); m.put("anchor", anchor); m.put("kind", kind); m.put("text", text);
        return m;
    }

    JsonNode inboxItem(String admin, String id) throws Exception {
        for (JsonNode it : body(get("/api/admin/inbox").header("Authorization", admin), 200).get("items"))
            if (id.equals(it.get("id").asText())) return it;
        return null;
    }

    void event(String taskId, String type, Map<String, Object> data) throws Exception {
        body(internal(json(post("/internal/tasks/" + taskId + "/events"), List.of(Map.of("type", type, "data", data)))), 200);
    }

    void age(String taskId, int minutes) {
        AiTask t = taskRepo.findById(taskId).orElseThrow();
        t.updatedAt = OffsetDateTime.now().minusMinutes(minutes);
        taskRepo.save(t);
    }

    @SuppressWarnings("unchecked")
    String sentTaskId(String sid, String type, String notId) {
        return ((TaskDispatcher.Recording) dispatcher).sent.stream()
                .filter(m -> sid.equals(m.get("sessionId")) && type.equals(m.get("type")) && !m.get("taskId").equals(notId))
                .map(m -> (String) m.get("taskId")).reduce((a, b) -> b).orElseThrow();
    }

    @SuppressWarnings("unchecked")
    void doneAll(String sid, String type) throws Exception {
        for (Map<String, Object> m : ((TaskDispatcher.Recording) dispatcher).sent) {
            if (sid.equals(m.get("sessionId")) && type.equals(m.get("type")))
                body(internal(json(post("/internal/tasks/" + m.get("taskId") + "/events"), List.of(Map.of("type", "DONE", "data", Map.of())))), 200);
        }
    }

    @Test
    void authAndCompanyIsolation() throws Exception {
        mvc.perform(get("/api/admin/sessions")).andExpect(status().isUnauthorized());
        body(json(post("/api/auth/login"), Map.of("email", DemoSeeder.EMAIL, "password", "wrong-password")), 401);
        String other = body(json(post("/api/auth/signup"), Map.of("companyName", "다른 회사", "email", "other@corp.dev", "password", "other-pass-123")), 200).get("token").asText();
        String sid = startSession().split("\\|")[0];
        mvc.perform(get("/api/admin/sessions/" + sid).header("Authorization", "Bearer " + other)).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/sessions/" + sid).header("Authorization", "Bearer " + adminToken())).andExpect(status().isOk());
    }

    @Test
    void internalApiOnlyOnInternalPortWithKey() throws Exception {
        mvc.perform(get("/internal/conditions").header("X-Internal-Key", "test-internal-key")).andExpect(status().isNotFound()); // public port
        mvc.perform(get("/internal/conditions").with(INTERNAL_PORT)).andExpect(status().isUnauthorized()); // no key
        mvc.perform(get("/api/meta").with(INTERNAL_PORT)).andExpect(status().isNotFound()); // public API not on internal port
        mvc.perform(internal(get("/internal/conditions"))).andExpect(status().isOk());
    }

    @Test
    void turnRulesAndTaskContract() throws Exception {
        String[] st = startSession().split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        // choice outside compromise milestone is rejected by the business rule
        body(json(post("/api/ai/tasks"), Map.of("type", "TURN", "sessionId", sid, "text", "선택", "choiceId", "a")).header("Authorization", cand), 409);
        JsonNode t = body(json(post("/api/ai/tasks"), Map.of("type", "TURN", "sessionId", sid, "text", "진행 상황 공유드릴게요")).header("Authorization", cand), 202);
        String taskId = t.get("taskId").asText();
        assertThat(t.get("userMessage").get("idx").asInt()).isEqualTo(1);
        // one turn at a time
        body(json(post("/api/ai/tasks"), Map.of("type", "TURN", "sessionId", sid, "text", "또 보냄")).header("Authorization", cand), 409);
        // another session's candidate cannot read this task
        String other = startSession().split("\\|")[1];
        mvc.perform(get("/api/ai/tasks/" + taskId).header("Authorization", "Bearer " + other)).andExpect(status().isForbidden());
        // agent progress events -> status + SSE replay
        body(internal(json(post("/internal/tasks/" + taskId + "/events"), List.of(
                Map.of("type", "TOOL_START", "data", Map.of("tool", "search_docs")),
                Map.of("type", "TOKEN", "data", Map.of("idx", 2, "speaker", "lead", "delta", "네")),
                Map.of("type", "DONE", "data", Map.of("milestone_idx", 0))))), 200);
        assertThat(body(get("/api/ai/tasks/" + taskId).header("Authorization", cand), 200).get("status").asText()).isEqualTo("DONE");
        String sse = mvc.perform(get("/api/ai/tasks/" + taskId + "/stream").header("Authorization", cand)).andReturn().getResponse().getContentAsString();
        assertThat(sse).contains("event:TOOL_START").contains("event:DONE").doesNotContain("event:TOKEN"); // TOKEN is live-only
    }

    @Test
    @SuppressWarnings("unchecked")
    void completionCreatesReportAndApprovalResumes() throws Exception {
        String sid = startSession().split("\\|")[0];
        String admin = "Bearer " + adminToken();
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        var rec = (TaskDispatcher.Recording) dispatcher;
        Map<String, Object> report = rec.sent.stream().filter(m -> sid.equals(m.get("sessionId")) && "REPORT".equals(m.get("type"))).findFirst().orElseThrow();
        String rid = (String) report.get("taskId");
        assertThat((String) report.get("threadId")).startsWith("report:" + sid);
        // approval before the agent asks for it is refused
        body(json(post("/api/ai/tasks/" + rid + "/approval"), Map.of("approved", true)).header("Authorization", admin), 409);
        body(internal(json(post("/internal/tasks/" + rid + "/events"), List.of(Map.of("type", "APPROVAL_REQUIRED", "data", Map.of("tool", "save_report", "trace", Map.of("llm_calls", 1)))))), 200);
        JsonNode view = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(view.get("pending_approval").get("taskId").asText()).isEqualTo(rid);
        // the REPORT handler mirrors the pause into report_status and builds the checklist item
        assertThat(body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("report_status").asText()).isEqualTo("awaiting_approval");
        JsonNode item = inboxItem(admin, "task:" + rid);
        assertThat(item.get("kind").asText()).isEqualTo("REPORT");
        assertThat(item.get("title").asText()).isEqualTo("리포트 공개 승인 요청");
        assertThat(item.get("actions").get("approve").asText()).isEqualTo("공개 승인");
        assertThat(item.get("actions").get("reject").asText()).isEqualTo("반려");
        body(json(post("/api/ai/tasks/" + rid + "/approval"), Map.of("approved", true, "comment", "ok")).header("Authorization", admin), 202);
        body(internal(json(post("/internal/tasks/" + rid + "/events"), List.of(Map.of("type", "DONE", "data", Map.of("saved", true, "trace", Map.of("llm_calls", 0)))))), 200);
        JsonNode done = body(get("/api/ai/tasks/" + rid).header("Authorization", admin), 200);
        assertThat(done.get("trace")).hasSize(2); // both runs kept
        assertThat(done.get("result").has("trace")).isFalse(); // on the task only, not in the result / stored events
        Map<String, Object> resume = rec.sent.get(rec.sent.size() - 1);
        assertThat(resume.get("mode")).isEqualTo("RESUME");
        assertThat(((Map<String, Object>) resume.get("resume")).get("approved")).isEqualTo(true);
        assertThat(resume.get("threadId")).isEqualTo(report.get("threadId"));
        // the agent saves through business-mcp -> internal API
        body(internal(json(put("/internal/sessions/" + sid + "/report"), Map.of("report", Map.of("status", "ready")))), 200);
        assertThat(body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("report_status").asText()).isEqualTo("ready");
    }

    @Test
    void adminHistoryIncludesSystemMadeReportTasks() throws Exception {
        String sid = startSession().split("\\|")[0];
        String admin = "Bearer " + adminToken();
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        JsonNode mine = body(get("/api/ai/tasks?mine=true").header("Authorization", admin), 200);
        boolean hasReport = false;
        for (JsonNode t : mine) hasReport |= "REPORT".equals(t.get("type").asText()) && sid.equals(t.get("sessionId").asText());
        assertThat(hasReport).isTrue();
    }

    @Test
    void expiredAndUnknownInvites() throws Exception {
        assertThat(body(get("/api/invites/nope"), 200).get("valid").asBoolean()).isFalse();
        String tok = activeCandidate().split("\\|")[1];
        body(json(post("/api/me/sessions"), Map.of("scenarioId", "nope")).header("Authorization", "Bearer " + tok), 400);
        String admin = "Bearer " + adminToken();
        String invite = body(json(post("/api/admin/invites"), Map.of("alias", "지원자Z")).header("Authorization", admin), 201).get("token").asText();
        body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.dev.saas", "inviteToken", invite)).header("Authorization", "Bearer " + tok), 201);
        // single-use invite
        body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.dev.saas", "inviteToken", invite)).header("Authorization", "Bearer " + tok), 410);
    }

    @Test
    @SuppressWarnings("unchecked")
    void candidateSignupIsScreenedByTheAgentAndAmbiguousCasesReachTheInbox() throws Exception {
        String admin = "Bearer " + adminToken();
        JsonNode r = body(json(post("/api/auth/candidate/signup"), Map.of("inviteToken", "demo", "email", "amb@test.dev", "password", "cand-pass-123",
                "nickname", "asdf", "desiredJob", "dev", "experienceYears", 7, "consent", true)), 201);
        String tok = "Bearer " + r.get("token").asText();
        long aid = r.get("account").get("id").asLong();
        String reviewTask = r.get("reviewTaskId").asText();
        assertThat(r.get("account").get("status").asText()).isEqualTo("PENDING_REVIEW");
        var rec = (TaskDispatcher.Recording) dispatcher;
        Map<String, Object> sent = rec.sent.stream().filter(m -> reviewTask.equals(m.get("taskId"))).findFirst().orElseThrow();
        assertThat(sent.get("type")).isEqualTo("ACCOUNT_REVIEW");
        assertThat(((Number) sent.get("accountId")).longValue()).isEqualTo(aid);
        // a pending account cannot start an assessment
        body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.pm.fintech")).header("Authorization", tok), 403);
        // the agent pauses: ambiguous -> APPROVAL_REQUIRED -> admin inbox
        body(internal(json(post("/internal/tasks/" + reviewTask + "/events"), List.of(
                Map.of("type", "PROGRESS", "data", Map.of("stage", "schema", "status", "done")),
                Map.of("type", "APPROVAL_REQUIRED", "data", Map.of("tool", "business.decide_account", "recommendation", "ask",
                        "flags", List.of(Map.of("field", "nickname", "message", "의미 없는 문자열로 보여요")), "reason", "모호함"))))), 200);
        JsonNode inbox = body(get("/api/admin/inbox").header("Authorization", admin), 200);
        boolean found = false;
        for (JsonNode it : inbox.get("items")) found |= reviewTask.equals(it.path("taskId").asText()) && "ACCOUNT_REVIEW".equals(it.get("kind").asText())
                && "승인".equals(it.get("actions").get("approve").asText()) && "반려".equals(it.get("actions").get("reject").asText());
        assertThat(found).isTrue();
        for (JsonNode it : inbox.get("items")) assertThat(it.get("actions").get("approve").asText()).isNotBlank(); // every item has button labels
        // the candidate's stream shows stages only, never the agent's flags
        String sse = mvc.perform(get("/api/me/review/stream").header("Authorization", tok)).andReturn().getResponse().getContentAsString();
        assertThat(sse).contains("event:PROGRESS").contains("admin_review").doesNotContain("의미 없는").doesNotContain("APPROVAL_REQUIRED");
        // ...and the generic task endpoints do not hand the raw review (flags, admin notes) to the candidate
        body(get("/api/ai/tasks/" + reviewTask).header("Authorization", tok), 403);
        body(get("/api/ai/tasks/" + reviewTask + "/stream").header("Authorization", tok), 403);
        assertThat(body(get("/api/ai/tasks?mine=true").header("Authorization", tok), 200).toString()).doesNotContain(reviewTask);
        // the admin approves -> resume on the same thread; the agent then records the decision
        body(json(post("/api/ai/tasks/" + reviewTask + "/approval"), Map.of("approved", true)).header("Authorization", admin), 202);
        Map<String, Object> resume = rec.sent.get(rec.sent.size() - 1);
        assertThat(resume.get("mode")).isEqualTo("RESUME");
        body(internal(json(post("/internal/accounts/" + aid + "/decision"), Map.of("decision", "approved", "basis", "admin_approved"))), 200);
        assertThat(body(get("/api/me").header("Authorization", tok), 200).get("status").asText()).isEqualTo("ACTIVE");
        // decisions are single-shot, and the basis must match the decision
        body(internal(json(post("/internal/accounts/" + aid + "/decision"), Map.of("decision", "rejected", "basis", "admin_rejected"))), 409);
        body(internal(json(post("/internal/accounts/" + aid + "/decision"), Map.of("decision", "rejected", "basis", "auto_clean"))), 400);
    }

    @Test
    void failedReviewClosesTheLoopThroughTheInbox() throws Exception {
        String admin = "Bearer " + adminToken();
        JsonNode r = body(json(post("/api/auth/candidate/signup"), Map.of("inviteToken", "demo", "email", "fail@test.dev", "password", "cand-pass-123",
                "nickname", "실패테스트", "desiredJob", "data", "experienceYears", 2, "consent", true)), 201);
        long aid = r.get("account").get("id").asLong();
        body(internal(json(post("/internal/tasks/" + r.get("reviewTaskId").asText() + "/events"), List.of(Map.of("type", "FAILED", "data", Map.of("error", "timeout")))) ), 200);
        JsonNode inbox = body(get("/api/admin/inbox").header("Authorization", admin), 200);
        boolean found = false;
        for (JsonNode it : inbox.get("items")) found |= "ACCOUNT_REVIEW_ERROR".equals(it.get("kind").asText()) && it.get("accountId").asLong() == aid;
        assertThat(found).isTrue();
        body(json(post("/api/admin/accounts/" + aid + "/decision"), Map.of("approved", true, "comment", "직접 확인")).header("Authorization", admin), 200);
        assertThat(body(get("/api/admin/accounts").header("Authorization", admin), 200).toString()).contains("\"status\":\"ACTIVE\"");
    }

    // ------------------------------------------------------------------ item 4: shared work items + markups
    @Test
    void artifactsAreSeededAndMarkupsFollowTheContract() throws Exception {
        String[] st = startSession(sampleArtifacts()).split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        String admin = "Bearer " + adminToken();
        // internal state: full items + markups + dialogue; the agent-only checkpoints were never stored
        JsonNode state = body(internal(get("/internal/sessions/" + sid + "/state")), 200);
        assertThat(state.get("artifacts")).hasSize(2);
        assertThat(state.get("artifacts").get(0).get("id").asText()).isEqualTo("a1");
        assertThat(state.get("artifacts").get(0).get("body").asText()).isEqualTo(DESIGN_BODY);
        assertThat(state.get("artifacts").get(1).get("lang").asText()).isEqualTo("kotlin");
        assertThat(state.get("annotations")).isEmpty();
        assertThat(state.get("dialogue").isNull()).isTrue();
        assertThat(state.toString()).doesNotContain("checkpoints").doesNotContain("체크포인트");
        JsonNode table = body(internal(get("/internal/sessions/" + sid + "/artifacts")), 200);
        assertThat(table.get(0).get("line_count").asInt()).isEqualTo(5); // body.split("\n") keeps the trailing empty line
        assertThat(table.get(1).get("line_count").asInt()).isEqualTo(3);
        assertThat(table.get(0).has("body")).isFalse();
        // candidate view: public items with nested markups + start_status; never dialogue or checkpoints
        JsonNode view = body(get("/api/sessions/" + sid).header("Authorization", cand), 200);
        assertThat(view.get("start_status").asText()).isEqualTo("done");
        assertThat(view.get("artifacts").get(0).get("title").asText()).isEqualTo("재참여 개선 기획안");
        assertThat(view.get("artifacts").get(0).get("annotations")).isEmpty();
        assertThat(view.has("dialogue")).isFalse();
        assertThat(view.toString()).doesNotContain("체크포인트");

        JsonNode n1 = annotate(sid, cand, mark("a1", Map.of("lineStart", 2, "lineEnd", 3), "risk", "  범위가 너무 넓어요  "), 201);
        assertThat(n1.get("artifactId").asText()).isEqualTo("a1");
        assertThat(n1.get("anchor").get("lineStart").asInt()).isEqualTo(2);
        assertThat(n1.get("anchor").get("lineEnd").asInt()).isEqualTo(3);
        assertThat(n1.get("anchor").get("quote").isNull()).isTrue();
        assertThat(n1.get("text").asText()).isEqualTo("범위가 너무 넓어요");
        assertThat(n1.get("msgIdx").asInt()).isEqualTo(1); // one message (the opening) so far
        assertThat(n1.get("createdAt").asText()).contains("T"); // ISO-8601
        JsonNode n2 = annotate(sid, cand, mark("a2", Map.of("quote", "x / 0"), "question", "0으로 나누나요?"), 201);
        assertThat(n2.get("anchor").get("lineStart").isNull()).isTrue();
        JsonNode n3 = annotate(sid, cand, mark("a2", Map.of("lineStart", 2), "ok", "확인했어요"), 201);
        assertThat(n3.get("anchor").get("lineEnd").asInt()).isEqualTo(2); // a single line

        // validation (contract order: 409 inactive, 404 artifact, 400 kind / text / anchor, 409 limit)
        annotate(sid, cand, mark("zz", Map.of("lineStart", 1), "risk", "없는 과제"), 404);
        annotate(sid, cand, mark("a1", Map.of("lineStart", 1), "memo", "종류 오류"), 400);
        annotate(sid, cand, mark("a1", Map.of("lineStart", 1), "risk", "   "), 400);
        annotate(sid, cand, mark("a1", Map.of("lineStart", 1), "risk", "가".repeat(501)), 400);
        annotate(sid, cand, mark("a1", null, "risk", "앵커 없음"), 400);
        annotate(sid, cand, mark("a1", Map.of(), "risk", "앵커 비어 있음"), 400);
        annotate(sid, cand, mark("a1", Map.of("quote", "  "), "risk", "빈 인용"), 400);
        annotate(sid, cand, mark("a1", Map.of("lineStart", 0), "risk", "0번 줄"), 400);
        annotate(sid, cand, mark("a1", Map.of("lineStart", 3, "lineEnd", 2), "risk", "거꾸로"), 400);
        annotate(sid, cand, mark("a1", Map.of("lineStart", 5, "lineEnd", 6), "risk", "줄 수 초과"), 400);
        annotate(sid, cand, mark("a1", Map.of("lineEnd", 2), "risk", "끝만"), 400);
        annotate(sid, cand, mark("a1", Map.of("quote", "본문에 없는 문장"), "risk", "인용 오류"), 400);
        annotate(sid, cand, mark("a1", Map.of("lineStart", 1, "quote", "가".repeat(301)), "risk", "긴 인용"), 400);

        // isolation: another candidate cannot read, mark up or delete; an admin does not mark up
        String other = "Bearer " + startSession().split("\\|")[1];
        body(get("/api/sessions/" + sid).header("Authorization", other), 403);
        annotate(sid, other, mark("a1", Map.of("lineStart", 1), "risk", "남의 세션"), 403);
        body(delete("/api/sessions/" + sid + "/annotations/" + n1.get("id").asLong()).header("Authorization", other), 403);
        annotate(sid, admin, mark("a1", Map.of("lineStart", 1), "risk", "관리자"), 403);

        // internal reads for the agent (snake_case)
        JsonNode one = body(internal(get("/internal/sessions/" + sid + "/artifacts/a2")), 200);
        assertThat(one.get("body").asText()).isEqualTo(CODE_BODY);
        assertThat(one.get("annotations")).hasSize(2);
        assertThat(one.get("annotations").get(0).get("artifact_id").asText()).isEqualTo("a2");
        assertThat(one.get("annotations").get(1).get("anchor").get("line_start").asInt()).isEqualTo(2);
        body(internal(get("/internal/sessions/" + sid + "/artifacts/zz")), 404);
        JsonNode all = body(internal(get("/internal/sessions/" + sid + "/annotations")), 200);
        assertThat(all).hasSize(3);
        assertThat(all.get(0).get("id").asLong()).isLessThan(all.get(1).get("id").asLong());
        assertThat(all.get(0).get("msg_idx").asInt()).isEqualTo(1);
        assertThat(all.get(0).get("created_at").isNumber()).isTrue();
        assertThat(body(internal(get("/internal/sessions/" + sid + "/annotations?since_idx=1")), 200)).hasSize(3);
        assertThat(body(internal(get("/internal/sessions/" + sid + "/annotations?since_idx=2")), 200)).isEmpty();
        assertThat(body(internal(get("/internal/sessions/" + sid + "/artifacts")), 200).get(1).get("annotation_count").asInt()).isEqualTo(2);
        assertThat(body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("annotations")).hasSize(3);

        // the candidate removes a markup
        body(delete("/api/sessions/" + sid + "/annotations/" + n3.get("id").asLong()).header("Authorization", cand), 204);
        body(delete("/api/sessions/" + sid + "/annotations/" + n3.get("id").asLong()).header("Authorization", cand), 404);
        view = body(get("/api/sessions/" + sid).header("Authorization", cand), 200);
        assertThat(view.get("artifacts").get(1).get("annotations")).hasSize(1);
        assertThat(view.get("artifacts").get(1).get("annotations").get(0).get("anchor").get("quote").asText()).isEqualTo("x / 0");

        // admin view: the same public items with markups, plus the dialogue slot and the state's markups (internal shape);
        // the planted-checkpoint checks are agent-computed, so they only come inside the analytics snapshot (none yet)
        JsonNode av = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(av.get("artifacts")).hasSize(2);
        assertThat(av.get("artifacts").get(0).get("annotations")).hasSize(1);
        assertThat(av.has("dialogue")).isTrue();
        assertThat(av.get("annotations")).hasSize(2);
        assertThat(av.has("artifact_checks")).isFalse();
        assertThat(av.get("analytics").isNull()).isTrue();
    }

    @Test
    void markupLimitAndClosedSessions() throws Exception {
        String[] st = startSession(sampleArtifacts()).split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        long last = 0;
        for (int i = 0; i < 40; i++) last = annotate(sid, cand, mark("a1", Map.of("lineStart", 1 + i % 5), "suggest", "제안 " + i), 201).get("id").asLong();
        annotate(sid, cand, mark("a1", Map.of("lineStart", 1), "suggest", "41번째"), 409);
        body(delete("/api/sessions/" + sid + "/annotations/" + last).header("Authorization", cand), 204);
        long kept = annotate(sid, cand, mark("a1", Map.of("lineStart", 1), "suggest", "다시 40번째"), 201).get("id").asLong();
        // a finished session takes no more markups (and keeps the ones it has)
        body(post("/api/sessions/" + sid + "/finish").header("Authorization", cand), 200);
        annotate(sid, cand, mark("a2", Map.of("lineStart", 1), "risk", "끝난 뒤"), 409);
        body(delete("/api/sessions/" + sid + "/annotations/" + kept).header("Authorization", cand), 409); // exists, but the session is over
        body(delete("/api/sessions/" + sid + "/annotations/" + last).header("Authorization", cand), 404);
    }

    @Test
    void initReplacesArtifactsAllAtOnce() throws Exception {
        String tok = "Bearer " + activeCandidate().split("\\|")[1];
        String sid = body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.pm.fintech")).header("Authorization", tok), 201).get("sessionId").asText();
        Map<String, Object> cond = Map.of("stratum", "V2", "lead", "competing", "peer", "avoiding");
        // the agent's rules are checked by Spring (400, nothing stored)
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", cond,
                "artifacts", List.of(Map.of("id", "a1", "kind", "memo", "title", "t", "owner", "lead", "body", "x"))))), 400);
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", cond,
                "artifacts", List.of(Map.of("id", "a1", "kind", "design", "title", "가".repeat(81), "owner", "lead", "body", "x"))))), 400);
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", cond,
                "artifacts", List.of(Map.of("id", "a1", "kind", "design", "title", "t", "body", "x"), Map.of("id", "a1", "kind", "code", "title", "t", "body", "y"))))), 400);
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", cond,
                "artifacts", List.of(Map.of("id", "a1", "kind", "design", "title", "t", "body", "가".repeat(6001)))))), 400);
        assertThat(body(internal(get("/internal/sessions/" + sid + "/artifacts")), 200)).isEmpty();
        // replace-all and idempotent (a retried START sends the same list)
        Map<String, Object> init = Map.of("condition", cond, "artifacts", sampleArtifacts());
        body(internal(json(post("/internal/sessions/" + sid + "/init"), init)), 200);
        body(internal(json(post("/internal/sessions/" + sid + "/init"), init)), 200);
        assertThat(body(internal(get("/internal/sessions/" + sid + "/artifacts")), 200)).hasSize(2);
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", cond,
                "artifacts", List.of(Map.of("id", "a2", "kind", "result", "title", "지표 표", "body", "| a | b |"))))), 200);
        JsonNode arts = body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("artifacts");
        assertThat(arts).hasSize(1);
        assertThat(arts.get(0).get("kind").asText()).isEqualTo("result");
        assertThat(arts.get(0).get("owner").asText()).isEqualTo("team"); // default owner
        // once the opening message is stored, init is closed
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", cond, "artifacts", sampleArtifacts(),
                "message", Map.of("idx", 0, "speaker", "lead", "text", "시작할게요", "milestone", "communicate")))), 200);
        body(internal(json(post("/internal/sessions/" + sid + "/init"), init)), 409);
        assertThat(body(internal(get("/internal/sessions/" + sid + "/artifacts")), 200)).hasSize(2);
    }

    // ------------------------------------------------------------------ item 6 plumbing: dialogue ledger
    @Test
    void dialogueRoundTripsAndNeverReachesTheCandidate() throws Exception {
        String[] st = startSession().split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        String admin = "Bearer " + adminToken();
        Map<String, Object> dialogue = Map.of("version", 1, "summary", "비밀 원장 요약", "issues", List.of(Map.of("id", "i1", "title", "범위", "status", "open", "raised_by", "lead", "last_idx", 2)),
                "positions", Map.of("lead", Map.of("claim", "전체 적용")), "extra_key", true);
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "dialogue", dialogue))), 200);
        JsonNode state = body(internal(get("/internal/sessions/" + sid + "/state")), 200);
        assertThat(state.get("dialogue").get("summary").asText()).isEqualTo("비밀 원장 요약");
        assertThat(state.get("dialogue").get("extra_key").asBoolean()).isTrue(); // stored opaque
        // a turn without a ledger keeps the last one; a non-object is refused
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 2))), 200);
        assertThat(body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("dialogue").get("issues")).hasSize(1);
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 3, "dialogue", "text"))), 400);
        JsonNode av = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(av.get("dialogue").get("summary").asText()).isEqualTo("비밀 원장 요약");
        JsonNode cv = body(get("/api/sessions/" + sid).header("Authorization", cand), 200);
        assertThat(cv.has("dialogue")).isFalse();
        assertThat(cv.toString()).doesNotContain("비밀 원장 요약").doesNotContain("\"dialogue\"");
    }

    // ------------------------------------------------------------------ item 5: loop closure
    @Test
    void restartOnlyAfterAFailedStart() throws Exception {
        String[] c = activeCandidate().split("\\|");
        String cand = "Bearer " + c[1];
        JsonNode started = body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.pm.fintech")).header("Authorization", cand), 201);
        String sid = started.get("sessionId").asText(), first = started.get("startTaskId").asText();
        JsonNode view = body(get("/api/sessions/" + sid).header("Authorization", cand), 200);
        assertThat(view.get("start_status").asText()).isEqualTo("running");
        assertThat(view.get("busy").asBoolean()).isTrue();
        body(post("/api/sessions/" + sid + "/restart").header("Authorization", cand), 409); // still running
        event(first, "FAILED", Map.of("error", "LLM timeout"));
        view = body(get("/api/sessions/" + sid).header("Authorization", cand), 200);
        assertThat(view.get("start_status").asText()).isEqualTo("failed");
        assertThat(view.get("busy").asBoolean()).isFalse();
        // only the session's own candidate restarts it
        body(post("/api/sessions/" + sid + "/restart").header("Authorization", "Bearer " + startSession().split("\\|")[1]), 403);
        body(post("/api/sessions/" + sid + "/restart").header("Authorization", "Bearer " + adminToken()), 403);
        String second = body(post("/api/sessions/" + sid + "/restart").header("Authorization", cand), 202).get("taskId").asText();
        assertThat(second).isNotEqualTo(first);
        assertThat(sentTaskId(sid, "START", first)).isEqualTo(second);
        assertThat(body(get("/api/ai/tasks/" + second).header("Authorization", cand), 200).get("type").asText()).isEqualTo("START");
        assertThat(body(get("/api/sessions/" + sid).header("Authorization", cand), 200).get("start_status").asText()).isEqualTo("running");
        body(post("/api/sessions/" + sid + "/restart").header("Authorization", cand), 409); // the new START is running
        // once the opening exists the session is started, even if the task itself is reported failed
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", Map.of("stratum", "V2", "lead", "competing", "peer", "avoiding"),
                "message", Map.of("idx", 0, "speaker", "lead", "text", "시작할게요", "milestone", "communicate")))), 200);
        event(second, "FAILED", Map.of("error", "late failure"));
        assertThat(body(get("/api/sessions/" + sid).header("Authorization", cand), 200).get("start_status").asText()).isEqualTo("done");
        body(post("/api/sessions/" + sid + "/restart").header("Authorization", cand), 409);
    }

    @Test
    void failedReportReachesTheInboxAndIsRetriedOrDismissed() throws Exception {
        String sid = startSession().split("\\|")[0];
        String admin = "Bearer " + adminToken();
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        String r1 = sentTaskId(sid, "REPORT", "");
        assertThat(inboxItem(admin, "report:" + sid)).isNull();
        event(r1, "FAILED", Map.of("error", "RateLimitError: quota"));
        JsonNode item = inboxItem(admin, "report:" + sid);
        assertThat(item.get("kind").asText()).isEqualTo("REPORT_FAILED");
        assertThat(item.get("sessionId").asText()).isEqualTo(sid);
        assertThat(item.get("title").asText()).isEqualTo("리포트를 만들지 못했어요");
        assertThat(item.get("subject").get("sessionId").asText()).isEqualTo(sid);
        assertThat(item.get("subject").get("detail").asText()).isEqualTo("dl.pm.fintech");
        assertThat(item.get("reason").asText()).isEqualTo("RateLimitError: quota");
        assertThat(item.get("recommendation").asText()).isEqualTo("retry");
        assertThat(item.get("flags")).isEmpty();
        assertThat(item.get("createdAt").asText()).isNotBlank();
        assertThat(item.get("actions").get("approve").asText()).isEqualTo("다시 만들기");
        assertThat(item.get("actions").get("reject").asText()).isEqualTo("넘기기");
        // approve = retry through the existing task API; the item leaves while it runs
        String r2 = body(json(post("/api/ai/tasks"), Map.of("type", "REPORT", "sessionId", sid)).header("Authorization", admin), 202).get("taskId").asText();
        assertThat(inboxItem(admin, "report:" + sid)).isNull();
        assertThat(body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("report_status").asText()).isEqualTo("pending");
        body(post("/api/admin/sessions/" + sid + "/report/dismiss").header("Authorization", admin), 409); // nothing failed now
        event(r2, "FAILED", Map.of("error", "second failure"));
        assertThat(inboxItem(admin, "report:" + sid).get("reason").asText()).isEqualTo("second failure"); // the last REPORT's error
        // reject = dismiss (company-scoped, once)
        String other = body(json(post("/api/auth/signup"), Map.of("companyName", "타사", "email", "dismiss@corp.dev", "password", "other-pass-123")), 200).get("token").asText();
        body(post("/api/admin/sessions/" + sid + "/report/dismiss").header("Authorization", "Bearer " + other), 403);
        assertThat(body(post("/api/admin/sessions/" + sid + "/report/dismiss").header("Authorization", admin), 200).get("report_status").asText()).isEqualTo("dismissed");
        assertThat(inboxItem(admin, "report:" + sid)).isNull();
        body(post("/api/admin/sessions/" + sid + "/report/dismiss").header("Authorization", admin), 409);
    }

    @Test
    void rejectionSemanticsAreUnchanged() throws Exception {
        String sid = startSession().split("\\|")[0];
        String admin = "Bearer " + adminToken();
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        String rid = sentTaskId(sid, "REPORT", "");
        event(rid, "APPROVAL_REQUIRED", Map.of("tool", "save_report"));
        body(json(post("/api/ai/tasks/" + rid + "/approval"), Map.of("approved", false, "comment", "근거 부족")).header("Authorization", admin), 202);
        event(rid, "DONE", Map.of("approved", false, "saved", false));
        assertThat(body(get("/api/ai/tasks/" + rid).header("Authorization", admin), 200).get("status").asText()).isEqualTo("REJECTED");
        assertThat(body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("report_status").asText()).isEqualTo("rejected");
        // a rejected account is still a finished review: the person's answer was the decision itself
        JsonNode r = body(json(post("/api/auth/candidate/signup"), Map.of("inviteToken", "demo", "email", "rej@test.dev", "password", "cand-pass-123",
                "nickname", "반려대상", "desiredJob", "dev", "experienceYears", 3, "consent", true)), 201);
        String review = r.get("reviewTaskId").asText();
        long aid = r.get("account").get("id").asLong();
        event(review, "APPROVAL_REQUIRED", Map.of("tool", "business.decide_account", "recommendation", "ask"));
        body(json(post("/api/ai/tasks/" + review + "/approval"), Map.of("approved", false)).header("Authorization", admin), 202);
        body(internal(json(post("/internal/accounts/" + aid + "/decision"), Map.of("decision", "rejected", "basis", "admin_rejected"))), 200);
        event(review, "DONE", Map.of("approved", false, "decision", "rejected"));
        assertThat(body(get("/api/ai/tasks/" + review).header("Authorization", admin), 200).get("status").asText()).isEqualTo("DONE");
        assertThat(body(get("/api/admin/accounts").header("Authorization", admin), 200).toString()).contains("\"email\":\"rej@test.dev\"");
        assertThat(inboxItem(admin, "account:" + aid)).isNull(); // REJECTED, not REVIEW_ERROR
    }

    @Test
    void watchdogFailsStaleTasksButNeverWaitingApprovals() throws Exception {
        String admin = "Bearer " + adminToken();
        JsonNode stale = body(json(post("/api/auth/candidate/signup"), Map.of("inviteToken", "demo", "email", "stale@test.dev", "password", "cand-pass-123",
                "nickname", "멈춘검토", "desiredJob", "pm", "experienceYears", 1, "consent", true)), 201);
        String staleTask = stale.get("reviewTaskId").asText();
        long staleAid = stale.get("account").get("id").asLong();
        JsonNode waiting = body(json(post("/api/auth/candidate/signup"), Map.of("inviteToken", "demo", "email", "wait@test.dev", "password", "cand-pass-123",
                "nickname", "대기검토", "desiredJob", "pm", "experienceYears", 1, "consent", true)), 201);
        String waitingTask = waiting.get("reviewTaskId").asText();
        event(waitingTask, "APPROVAL_REQUIRED", Map.of("tool", "business.decide_account", "recommendation", "ask"));
        JsonNode fresh = body(json(post("/api/auth/candidate/signup"), Map.of("inviteToken", "demo", "email", "fresh@test.dev", "password", "cand-pass-123",
                "nickname", "진행중", "desiredJob", "pm", "experienceYears", 1, "consent", true)), 201);
        String freshTask = fresh.get("reviewTaskId").asText();
        event(freshTask, "PROGRESS", Map.of("stage", "schema", "status", "running")); // RUNNING, with recent progress
        age(staleTask, 30);
        age(waitingTask, 120);
        // a live subscriber of the stale task gets the FAILED event
        MvcResult live = mvc.perform(get("/api/ai/tasks/" + staleTask + "/stream").header("Authorization", admin)).andReturn();

        List<String> closed = watchdog.sweep();
        assertThat(closed).contains(staleTask).doesNotContain(waitingTask, freshTask);
        assertThat(live.getResponse().getContentAsString()).contains("event:FAILED");
        JsonNode t = body(get("/api/ai/tasks/" + staleTask).header("Authorization", admin), 200);
        assertThat(t.get("status").asText()).isEqualTo("FAILED");
        assertThat(t.get("error").asText()).contains("10분");
        String replay = mvc.perform(get("/api/ai/tasks/" + staleTask + "/stream").header("Authorization", admin)).andReturn().getResponse().getContentAsString();
        assertThat(replay).contains("event:FAILED"); // stored, so a later subscriber sees it too
        // ACCOUNT_REVIEW hook: the account goes to the checklist as REVIEW_ERROR
        assertThat(body(get("/api/me").header("Authorization", "Bearer " + stale.get("token").asText()), 200).get("status").asText()).isEqualTo("REVIEW_ERROR");
        JsonNode item = inboxItem(admin, "account:" + staleAid);
        assertThat(item.get("kind").asText()).isEqualTo("ACCOUNT_REVIEW_ERROR");
        assertThat(item.get("reason").asText()).contains("10분");
        assertThat(item.get("actions").get("approve").asText()).isEqualTo("직접 승인");
        assertThat(item.get("actions").get("reject").asText()).isEqualTo("직접 반려");
        // WAITING_APPROVAL never times out; it stays on the checklist
        assertThat(body(get("/api/ai/tasks/" + waitingTask).header("Authorization", admin), 200).get("status").asText()).isEqualTo("WAITING_APPROVAL");
        assertThat(inboxItem(admin, "task:" + waitingTask)).isNotNull();
        assertThat(body(get("/api/ai/tasks/" + freshTask).header("Authorization", admin), 200).get("status").asText()).isEqualTo("RUNNING");
        // a late agent event cannot reopen the closed task; a second sweep has nothing to do
        event(staleTask, "APPROVAL_REQUIRED", Map.of("tool", "business.decide_account"));
        assertThat(body(get("/api/ai/tasks/" + staleTask).header("Authorization", admin), 200).get("status").asText()).isEqualTo("FAILED");
        assertThat(inboxItem(admin, "task:" + staleTask)).isNull();
        assertThat(watchdog.sweep()).doesNotContain(staleTask);
        // the admin closes it directly, as for any failed review
        body(json(post("/api/admin/accounts/" + staleAid + "/decision"), Map.of("approved", true)).header("Authorization", admin), 200);
        assertThat(inboxItem(admin, "account:" + staleAid)).isNull();
    }

    @Test
    void taskTypesComeFromTheRegistry() throws Exception {
        assertThat(handlers.types()).containsExactlyInAnyOrder("START", "TURN", "REPORT", "ACCOUNT_REVIEW", "ANALYTICS");
        String[] st = startSession().split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        String admin = "Bearer " + adminToken();
        body(json(post("/api/ai/tasks"), Map.of("type", "NOPE", "sessionId", sid)).header("Authorization", admin), 400);
        try {
            taskService.create("NOPE", sid, null, "test", Map.of());
            throw new AssertionError("unknown type was accepted");
        } catch (ResponseStatusException e) {
            assertThat(e.getStatusCode().value()).isEqualTo(400);
        }
        // a type that cannot resume is not parked waiting for a person: the pause becomes FAILED
        String turn = body(json(post("/api/ai/tasks"), Map.of("type", "TURN", "sessionId", sid, "text", "확인 부탁드려요")).header("Authorization", cand), 202).get("taskId").asText();
        event(turn, "APPROVAL_REQUIRED", Map.of("tool", "business.append_turn"));
        assertThat(body(get("/api/ai/tasks/" + turn).header("Authorization", cand), 200).get("status").asText()).isEqualTo("FAILED");
        body(json(post("/api/ai/tasks/" + turn + "/approval"), Map.of("approved", true)).header("Authorization", admin), 409);
        // visibility per handler: the candidate sees START / TURN, not REPORT
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        String report = sentTaskId(sid, "REPORT", "");
        body(get("/api/ai/tasks/" + report).header("Authorization", cand), 403);
        List<String> types = new ArrayList<>();
        for (JsonNode x : body(get("/api/ai/tasks?mine=true").header("Authorization", cand), 200)) types.add(x.get("type").asText());
        assertThat(types).contains("START", "TURN").doesNotContain("REPORT", "ACCOUNT_REVIEW");
    }

    // ------------------------------------------------------------------ v4: analytics through MCP (snapshot + ANALYTICS task)
    static final Map<String, Object> COND = Map.of("stratum", "V2", "lead", "competing", "peer", "avoiding");

    long rev(String sid) throws Exception {
        return body(internal(get("/internal/sessions/" + sid + "/state")), 200).get("state_rev").asLong();
    }

    /** The rev moved past `before` (one change that affects analytics); returns the new rev. */
    long bumped(String sid, long before, String what) throws Exception {
        long now = rev(sid);
        assertThat(now).as(what).isGreaterThan(before);
        return now;
    }

    /** A version-1 bundle as analytics-mcp builds it (only the parts Spring reads or passes on). */
    static Map<String, Object> bundle(String sid, long rev, double computedAt) {
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("version", 1);
        b.put("session_id", sid);
        b.put("computed_at", computedAt);
        b.put("source", Map.of("state_rev", rev, "message_count", 1, "status", "active", "milestone_idx", 0));
        b.put("row", Map.of("category", "기획·PM · 핀테크", "scenario_title", "재참여 개선", "axis", "원칙 ↔ 파격", "choice", "통합안",
                "condition", "회피형 팀장 · 협력형 동료"));
        b.put("timeline", List.of(Map.of("key", "communicate", "label", "소통", "reached", true, "messages", 1, "observations", 0)));
        b.put("heatmap", Map.of("cells", List.of(), "totals", Map.of(), "max_n", 0));
        b.put("figures", Map.of("messages", 1, "candidate_messages", 0, "pooled_kappa", 0.31, "checkpoints", "0/2", "milestones_reached", "1/4"));
        b.put("charts", List.of(Map.of("id", "timeline", "type", "timeline", "title", "마일스톤 타임라인", "available", true)));
        return b;
    }

    JsonNode putAnalytics(String sid, Map<String, Object> bundle, int status) throws Exception {
        return body(internal(json(put("/internal/sessions/" + sid + "/analytics"), bundle)), status);
    }

    JsonNode adminRow(String admin, String sid) throws Exception {
        for (JsonNode r : body(get("/api/admin/sessions").header("Authorization", admin), 200))
            if (sid.equals(r.get("id").asText())) return r;
        return null;
    }

    JsonNode analyticsTask(String auth, String sid, int status) throws Exception {
        return body(json(post("/api/ai/tasks"), Map.of("type", "ANALYTICS", "sessionId", sid)).header("Authorization", auth), status);
    }

    @Test
    void stateRevCountsEveryChangeThatAffectsAnalytics() throws Exception {
        String cand = "Bearer " + activeCandidate().split("\\|")[1];
        String sid = body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.pm.fintech")).header("Authorization", cand), 201).get("sessionId").asText();
        long r = rev(sid);
        assertThat(r).isZero();
        body(internal(json(post("/internal/sessions/" + sid + "/init"), Map.of("condition", COND, "artifacts", sampleArtifacts(),
                "message", Map.of("idx", 0, "speaker", "lead", "text", "시작할게요", "milestone", "communicate")))), 200);
        r = bumped(sid, r, "init");
        doneAll(sid, "START");
        body(json(post("/api/ai/tasks"), Map.of("type", "TURN", "sessionId", sid, "text", "범위부터 정리해 볼게요")).header("Authorization", cand), 202);
        r = bumped(sid, r, "candidate message");
        doneAll(sid, "TURN");
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(Map.of("idx", 2, "speaker", "lead", "text", "좋아요", "milestone", "communicate")),
                "observations", List.of(Map.of("id", "o1_0", "competency", "C01", "milestone", "communicate", "behavior", "범위 확인", "quote", "범위부터", "signal", "positive", "msg_idx", 1)),
                "milestone_idx_after", 1, "turns_after", 0))), 200);
        r = bumped(sid, r, "agent turn");
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 2, "turns_after", 0))), 200);
        r = bumped(sid, r, "milestone change");
        body(json(post("/api/ai/tasks"), Map.of("type", "TURN", "sessionId", sid, "text", "둘 다 가져가죠", "choiceId", "both")).header("Authorization", cand), 202);
        r = bumped(sid, r, "choice");
        doneAll(sid, "TURN");
        body(internal(json(post("/internal/sessions/" + sid + "/detections"), Map.of("msg_idx", 1, "detection", Map.of("rules", Map.of("assertiveness", 3))))), 200);
        r = bumped(sid, r, "detection");
        long markup = annotate(sid, cand, mark("a1", Map.of("lineStart", 2), "risk", "목표 수치 근거가 없어요"), 201).get("id").asLong();
        r = bumped(sid, r, "markup added");
        annotate(sid, cand, mark("zz", Map.of("lineStart", 1), "risk", "없는 과제"), 404);
        assertThat(rev(sid)).as("refused markup").isEqualTo(r);
        body(delete("/api/sessions/" + sid + "/annotations/" + markup).header("Authorization", cand), 204);
        r = bumped(sid, r, "markup deleted");
        // not analytics: the candidate's notes and storing a snapshot leave the rev alone
        body(json(put("/api/sessions/" + sid + "/notes"), Map.of("text", "메모")).header("Authorization", cand), 200);
        assertThat(putAnalytics(sid, bundle(sid, r, 1.0), 200).get("stored").asBoolean()).isTrue();
        assertThat(rev(sid)).as("notes + snapshot").isEqualTo(r);
        body(post("/api/sessions/" + sid + "/finish").header("Authorization", cand), 200);
        r = bumped(sid, r, "completion");
        body(internal(json(put("/internal/sessions/" + sid + "/report"), Map.of("report", Map.of("status", "ready")))), 200);
        bumped(sid, r, "report save");
    }

    @Test
    void analyticsSnapshotIsMonotonicAndGoesStaleWithTheSession() throws Exception {
        String[] st = startSession(sampleArtifacts()).split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        String admin = "Bearer " + adminToken();
        JsonNode av = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(av.get("analytics").isNull()).isTrue();
        assertThat(av.get("analytics_status").asText()).isEqualTo("missing");
        assertThat(av.get("analytics_task").isNull()).isTrue();
        JsonNode row = adminRow(admin, sid);
        assertThat(row.get("analytics_status").asText()).isEqualTo("missing");
        assertThat(row.get("category").asText()).isEqualTo("dl.pm.fintech"); // no snapshot: falls back to the scenario id
        assertThat(row.get("axis").isNull()).isTrue();
        assertThat(row.get("messages").asInt()).isEqualTo(1);

        long r = rev(sid);
        assertThat(putAnalytics(sid, bundle(sid, r, 1.0), 200).get("stored").asBoolean()).isTrue();
        av = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(av.get("analytics_status").asText()).isEqualTo("fresh");
        assertThat(av.get("analytics").get("source").get("state_rev").asLong()).isEqualTo(r);
        assertThat(av.get("analytics").get("figures").get("pooled_kappa").asDouble()).isEqualTo(0.31);
        assertThat(av.get("state_rev").asLong()).isEqualTo(r);
        row = adminRow(admin, sid);
        assertThat(row.get("analytics_status").asText()).isEqualTo("fresh");
        assertThat(row.get("category").asText()).isEqualTo("기획·PM · 핀테크");
        assertThat(row.get("axis").asText()).isEqualTo("원칙 ↔ 파격");
        assertThat(row.get("choice").asText()).isEqualTo("통합안");
        assertThat(row.get("condition").asText()).isEqualTo("회피형 팀장 · 협력형 동료");

        // older is refused, equal and newer are stored
        assertThat(putAnalytics(sid, bundle(sid, r - 1, 9.0), 200).get("stored").asBoolean()).isFalse();
        assertThat(body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("analytics").get("computed_at").asDouble()).isEqualTo(1.0);
        assertThat(putAnalytics(sid, bundle(sid, r, 2.0), 200).get("stored").asBoolean()).isTrue();
        assertThat(body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("analytics").get("computed_at").asDouble()).isEqualTo(2.0);

        // a markup makes it stale; the stale numbers stay visible until the next snapshot
        annotate(sid, cand, mark("a2", Map.of("lineStart", 2), "risk", "0으로 나눠요"), 201);
        av = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(av.get("analytics_status").asText()).isEqualTo("stale");
        assertThat(av.get("analytics").get("computed_at").asDouble()).isEqualTo(2.0);
        assertThat(adminRow(admin, sid).get("analytics_status").asText()).isEqualTo("stale");
        long now = rev(sid);
        assertThat(putAnalytics(sid, bundle(sid, now, 3.0), 200).get("stored").asBoolean()).isTrue();
        assertThat(body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("analytics_status").asText()).isEqualTo("fresh");
        assertThat(putAnalytics(sid, bundle(sid, r, 4.0), 200).get("stored").asBoolean()).isFalse(); // the old run finishing late

        // the body is checked: a rev (whole, ≥ 0, not ahead of the session), the same session; unknown session 404
        Map<String, Object> noRev = new HashMap<>(bundle(sid, now, 5.0));
        noRev.remove("source");
        putAnalytics(sid, noRev, 400);
        Map<String, Object> textRev = new HashMap<>(bundle(sid, now, 5.0));
        textRev.put("source", Map.of("state_rev", "42"));
        putAnalytics(sid, textRev, 400);
        putAnalytics(sid, bundle(sid, -1, 5.0), 400);
        putAnalytics(sid, bundle(sid, now + 1, 5.0), 400);
        putAnalytics(sid, bundle("other-session", now, 5.0), 400);
        Map<String, Object> floatRev = new HashMap<>(bundle(sid, now, 5.0));
        floatRev.put("source", Map.of("state_rev", (double) now));
        putAnalytics(sid, floatRev, 400);
        // ...and the parts the screens draw from: a bundle with only a rev never makes the session look fresh
        putAnalytics(sid, Map.of("version", 1, "session_id", sid, "source", Map.of("state_rev", now)), 400);
        for (String key : List.of("version", "session_id", "row", "heatmap", "figures", "timeline", "charts")) {
            Map<String, Object> partial = new HashMap<>(bundle(sid, now, 5.0));
            partial.remove(key);
            putAnalytics(sid, partial, 400);
        }
        Map<String, Object> v2 = new HashMap<>(bundle(sid, now, 5.0));
        v2.put("version", 2);
        putAnalytics(sid, v2, 400);
        Map<String, Object> noCharts = new HashMap<>(bundle(sid, now, 5.0));
        noCharts.put("charts", List.of());
        putAnalytics(sid, noCharts, 400);
        putAnalytics("nope", bundle("nope", 0, 5.0), 404);
        assertThat(body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("analytics").get("computed_at").asDouble()).isEqualTo(3.0);
        // the internal API stays internal
        mvc.perform(json(put("/internal/sessions/" + sid + "/analytics"), bundle(sid, now, 6.0)).header("Authorization", admin)).andExpect(status().isNotFound());
    }

    @Test
    void adminScreensNeverCallTheAgent() throws Exception {
        String[] st = startSession(sampleArtifacts()).split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        String admin = "Bearer " + adminToken();
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(),
                "observations", List.of(Map.of("id", "o0_0", "competency", "C02", "milestone", "communicate", "behavior", "확인", "quote", "시작", "signal", "neutral", "msg_idx", 0)),
                "milestone_idx_after", 0, "turns_after", 1))), 200);
        putAnalytics(sid, bundle(sid, rev(sid), 1.0), 200);
        // the agent is down: every call to it fails
        ResponseStatusException down = new ResponseStatusException(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE, "Agent 서버에 연결하지 못했어요.");
        when(agent.view(anyString(), anyMap())).thenThrow(down);
        when(agent.scenario(anyString())).thenThrow(down);
        when(agent.meta()).thenThrow(down);
        Mockito.clearInvocations(agent);

        JsonNode av = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(av.get("alias").asText()).startsWith("지원자");
        assertThat(av.get("scenario_id").asText()).isEqualTo("dl.pm.fintech");
        assertThat(av.get("messages")).hasSize(1);
        assertThat(av.get("observations")).hasSize(1);
        assertThat(av.get("milestone_log")).hasSize(1);
        assertThat(av.get("artifacts")).hasSize(2);
        assertThat(av.get("tasks").isArray()).isTrue();
        assertThat(av.get("analytics_status").asText()).isEqualTo("fresh");
        assertThat(av.get("analytics").get("row").get("category").asText()).isEqualTo("기획·PM · 핀테크");
        for (String agentMade : List.of("scenario", "painpoints", "detector", "dilemma", "artifact_checks", "category"))
            assertThat(av.has(agentMade)).as(agentMade).isFalse();
        JsonNode row = adminRow(admin, sid);
        List<String> keys = new ArrayList<>();
        row.fieldNames().forEachRemaining(keys::add);
        assertThat(keys).containsExactly("id", "alias", "category", "scenario_id", "axis", "choice", "condition", "status", "milestone_idx",
                "messages", "observations", "report_status", "created_at", "analytics_status");
        assertThat(row.get("observations").asInt()).isEqualTo(1);
        assertThat(row.get("created_at").isNumber()).isTrue();
        assertThat(Mockito.mockingDetails(agent).getInvocations()) // (the startup task-type check may ask for /agent/handlers)
                .noneMatch(i -> !"handlers".equals(i.getMethod().getName()));
        // the candidate's screen is still made by the agent
        body(get("/api/sessions/" + sid).header("Authorization", cand), 503);
    }

    @Test
    @SuppressWarnings("unchecked")
    void analyticsTaskIsForTheCompanysAdminAndAWorkingOneIsReused() throws Exception {
        String[] st = startSession().split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        String admin = "Bearer " + adminToken();
        String other = "Bearer " + body(json(post("/api/auth/signup"), Map.of("companyName", "분석 타사", "email", "analytics@corp.dev", "password", "other-pass-123")), 200).get("token").asText();
        analyticsTask(cand, sid, 403);
        analyticsTask(other, sid, 403);
        analyticsTask(admin, "nope", 404);
        JsonNode first = analyticsTask(admin, sid, 202);
        assertThat(first.get("reused").asBoolean()).isFalse();
        String tid = first.get("taskId").asText();
        Map<String, Object> sent = ((TaskDispatcher.Recording) dispatcher).sent.stream().filter(m -> tid.equals(m.get("taskId"))).findFirst().orElseThrow();
        assertThat(sent.get("type")).isEqualTo("ANALYTICS");
        assertThat(sent.get("mode")).isEqualTo("RUN");
        assertThat(sent.get("threadId")).isEqualTo("analytics:" + sid + ":" + tid);
        // while it works, asking again hands out the same task
        JsonNode again = analyticsTask(admin, sid, 202);
        assertThat(again.get("taskId").asText()).isEqualTo(tid);
        assertThat(again.get("reused").asBoolean()).isTrue();
        event(tid, "TOOL_START", Map.of("tool", "analytics.session_analytics"));
        assertThat(analyticsTask(admin, sid, 202).get("taskId").asText()).isEqualTo(tid);
        JsonNode at = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("analytics_task");
        assertThat(at.get("id").asText()).isEqualTo(tid);
        assertThat(at.get("status").asText()).isEqualTo("RUNNING");
        // admin data: the candidate can neither read nor follow it
        body(get("/api/ai/tasks/" + tid).header("Authorization", cand), 403);
        body(get("/api/ai/tasks/" + tid + "/stream").header("Authorization", cand), 403);
        assertThat(body(get("/api/ai/tasks?mine=true").header("Authorization", cand), 200).toString()).doesNotContain(tid).doesNotContain("ANALYTICS");
        assertThat(body(get("/api/ai/tasks/" + tid).header("Authorization", admin), 200).get("type").asText()).isEqualTo("ANALYTICS");
        // derived work stays out of the admin's task history (it would crowd out what people asked for); the session lists it
        assertThat(body(get("/api/ai/tasks?mine=true").header("Authorization", admin), 200).toString()).doesNotContain(tid).doesNotContain("\"ANALYTICS\"");
        assertThat(body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("tasks").toString()).contains(tid);
        // the agent stores the snapshot (business.save_analytics) and finishes
        putAnalytics(sid, bundle(sid, rev(sid), 1.0), 200);
        event(tid, "DONE", Map.of("stored", true, "figures", Map.of("messages", 1)));
        JsonNode done = body(get("/api/ai/tasks/" + tid).header("Authorization", admin), 200);
        assertThat(done.get("status").asText()).isEqualTo("DONE");
        assertThat(done.get("result").get("stored").asBoolean()).isTrue();
        expectIdleAnalytics(admin, sid, "fresh");
        // a finished task is not reused; the type cannot pause for a person (not resumable)
        JsonNode next = analyticsTask(admin, sid, 202);
        assertThat(next.get("reused").asBoolean()).isFalse();
        assertThat(next.get("taskId").asText()).isNotEqualTo(tid);
        event(next.get("taskId").asText(), "APPROVAL_REQUIRED", Map.of("tool", "business.save_analytics"));
        assertThat(body(get("/api/ai/tasks/" + next.get("taskId").asText()).header("Authorization", admin), 200).get("status").asText()).isEqualTo("FAILED");
        assertThat(body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("analytics_task").isNull()).isTrue();
    }

    /** Admin detail: the snapshot has this status and no ANALYTICS task is working. */
    void expectIdleAnalytics(String admin, String sid, String analyticsStatus) throws Exception {
        JsonNode v = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200);
        assertThat(v.get("analytics_status").asText()).isEqualTo(analyticsStatus);
        assertThat(v.get("analytics_task").isNull()).isTrue();
    }

    @Test
    void refreshStartsTasksOnlyForTheCompanysNonFreshSessions() throws Exception {
        String admin = "Bearer " + adminToken();
        String fresh = startSession().split("\\|")[0];
        String missing = startSession().split("\\|")[0];
        String[] st = startSession(sampleArtifacts()).split("\\|");
        String stale = st[0];
        putAnalytics(fresh, bundle(fresh, rev(fresh), 1.0), 200);
        putAnalytics(stale, bundle(stale, rev(stale), 1.0), 200);
        annotate(stale, "Bearer " + st[1], mark("a1", Map.of("lineStart", 1), "question", "제목 확인"), 201);
        String working = analyticsTask(admin, missing, 202).get("taskId").asText(); // already being computed
        int sentBefore = ((TaskDispatcher.Recording) dispatcher).sent.size();

        JsonNode out = body(json(post("/api/admin/analytics/refresh"), Map.of("sessionIds", List.of(fresh, missing, stale, "nope", missing))).header("Authorization", admin), 202);
        assertThat(out).hasSize(2);
        assertThat(out.get(0).get("sessionId").asText()).isEqualTo(missing);
        assertThat(out.get(0).get("taskId").asText()).isEqualTo(working);
        assertThat(out.get(1).get("sessionId").asText()).isEqualTo(stale);
        String staleTask = out.get(1).get("taskId").asText();
        assertThat(sentTaskId(stale, "ANALYTICS", "")).isEqualTo(staleTask);
        assertThat(((TaskDispatcher.Recording) dispatcher).sent.size()).isEqualTo(sentBefore + 1); // only the stale one is new
        // asked again while they work: the same tasks
        JsonNode again = body(json(post("/api/admin/analytics/refresh"), Map.of("sessionIds", List.of(stale, missing))).header("Authorization", admin), 202);
        assertThat(again.get(0).get("taskId").asText()).isEqualTo(staleTask);
        assertThat(again.get(1).get("taskId").asText()).isEqualTo(working);
        // another company's admin gets nothing for these sessions; candidates cannot ask; at most 20 ids
        String other = "Bearer " + body(json(post("/api/auth/signup"), Map.of("companyName", "새로고침 타사", "email", "refresh@corp.dev", "password", "other-pass-123")), 200).get("token").asText();
        assertThat(body(json(post("/api/admin/analytics/refresh"), Map.of("sessionIds", List.of(missing, stale))).header("Authorization", other), 202)).isEmpty();
        body(json(post("/api/admin/analytics/refresh"), Map.of("sessionIds", List.of(stale))).header("Authorization", "Bearer " + st[1]), 403);
        List<String> many = new ArrayList<>();
        for (int i = 0; i < 21; i++) many.add("s" + i);
        body(json(post("/api/admin/analytics/refresh"), Map.of("sessionIds", many)).header("Authorization", admin), 400);
        body(json(post("/api/admin/analytics/refresh"), Map.of()).header("Authorization", admin), 400);
    }

    @Test
    void candidateNeverSeesAnalyticsFiguresOrCharts() throws Exception {
        String[] st = startSession(sampleArtifacts()).split("\\|");
        String sid = st[0], cand = "Bearer " + st[1];
        putAnalytics(sid, bundle(sid, rev(sid), 1.0), 200);
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        body(internal(json(put("/internal/sessions/" + sid + "/report"), Map.of("report", Map.of("status", "ready", "figures", Map.of("pooled_kappa", 0.31),
                "charts", List.of(Map.of("chart_id", "timeline", "title", "마일스톤 타임라인", "svg", "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>")))))), 200);
        for (JsonNode cv : List.of(body(get("/api/sessions/" + sid).header("Authorization", cand), 200),
                body(post("/api/sessions/" + sid + "/finish").header("Authorization", cand), 200))) {
            assertThat(cv.toString()).doesNotContain("analytics").doesNotContain("figures").doesNotContain("charts")
                    .doesNotContain("pooled_kappa").doesNotContain("<svg");
        }
        // ...while the admin has both the snapshot and the report
        JsonNode av = body(get("/api/admin/sessions/" + sid).header("Authorization", "Bearer " + adminToken()), 200);
        assertThat(av.get("analytics").get("figures").get("pooled_kappa").asDouble()).isEqualTo(0.31);
        assertThat(av.get("report").get("charts")).hasSize(1);
    }

    @Test
    void reportApprovalCardCarriesFiguresAndCharts() throws Exception {
        String sid = startSession().split("\\|")[0];
        String admin = "Bearer " + adminToken();
        body(internal(json(post("/internal/sessions/" + sid + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        String rid = sentTaskId(sid, "REPORT", "");
        String svg = "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"720\" height=\"200\"><text x=\"8\" y=\"20\">소통</text></svg>";
        event(rid, "APPROVAL_REQUIRED", Map.of("tool", "business.save_report", "draft", Map.of("C01", Map.of("summary", "근거 있는 요약")),
                "figures", Map.of("messages", 12, "pooled_kappa", 0.31, "checkpoints", "1/2"),
                "charts", List.of(Map.of("chart_id", "timeline", "title", "마일스톤 타임라인", "svg", svg), Map.of("chart_id", "tki", "title", "TKI", "svg", svg))));
        JsonNode item = inboxItem(admin, "task:" + rid);
        assertThat(item.get("kind").asText()).isEqualTo("REPORT");
        assertThat(item.get("figures").get("pooled_kappa").asDouble()).isEqualTo(0.31);
        assertThat(item.get("figures").get("checkpoints").asText()).isEqualTo("1/2");
        assertThat(item.get("charts")).hasSize(2);
        assertThat(item.get("charts").get(0).get("chart_id").asText()).isEqualTo("timeline");
        assertThat(item.get("charts").get(0).get("svg").asText()).isEqualTo(svg);
        assertThat(item.get("draft").get("C01").get("summary").asText()).isEqualTo("근거 있는 요약");
        JsonNode pending = body(get("/api/admin/sessions/" + sid).header("Authorization", admin), 200).get("pending_approval");
        assertThat(pending.get("draft").get("charts")).hasSize(2);
        // a draft from before v4 (no figures / charts) still makes a card
        String sid2 = startSession().split("\\|")[0];
        body(internal(json(post("/internal/sessions/" + sid2 + "/turn"), Map.of("new_messages", List.of(), "milestone_idx_after", 0, "turns_after", 1, "completed", true))), 200);
        String rid2 = sentTaskId(sid2, "REPORT", "");
        event(rid2, "APPROVAL_REQUIRED", Map.of("tool", "business.save_report"));
        JsonNode old = inboxItem(admin, "task:" + rid2);
        assertThat(old.get("figures").isNull()).isTrue();
        assertThat(old.get("charts")).isEmpty();
        // the top-bar badge polls a count only: the same number, none of the chart SVGs
        JsonNode count = body(get("/api/admin/inbox/count").header("Authorization", admin), 200);
        assertThat(count.get("count").asInt()).isEqualTo(body(get("/api/admin/inbox").header("Authorization", admin), 200).get("count").asInt());
        assertThat(count.size()).isEqualTo(1);
        assertThat(count.toString()).doesNotContain("<svg");
        body(get("/api/admin/inbox/count").header("Authorization", "Bearer " + startSession().split("\\|")[1]), 403);
    }
}
