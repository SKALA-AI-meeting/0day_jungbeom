package dev.dayzero.backend;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.dayzero.backend.seed.DemoSeeder;
import dev.dayzero.backend.service.AgentClient;
import dev.dayzero.backend.service.TaskDispatcher;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class BackendFlowTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper om;
    @Autowired TaskDispatcher dispatcher;
    @MockitoBean AgentClient agent;

    static final RequestPostProcessor INTERNAL_PORT = r -> { r.setLocalPort(8081); return r; };

    @BeforeEach
    void stubAgent() {
        when(agent.scenario(anyString())).thenAnswer(i -> "nope".equals(i.getArgument(0)) ? null : Map.of("id", i.getArgument(0)));
        when(agent.view(anyString(), anyMap())).thenAnswer(i -> Map.of("kind", i.getArgument(0), "state", i.getArgument(1)));
        when(agent.rows(anyList())).thenAnswer(i -> i.getArgument(0));
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
        String[] c = activeCandidate().split("\\|");
        String tok = c[1];
        JsonNode s = body(json(post("/api/me/sessions"), Map.of("scenarioId", "dl.pm.fintech")).header("Authorization", "Bearer " + tok), 201);
        String sid = s.get("sessionId").asText();
        body(internal(json(post("/internal/sessions/" + sid + "/init"),
                Map.of("condition", Map.of("stratum", "V2", "lead", "competing", "peer", "avoiding"),
                        "message", Map.of("idx", 0, "speaker", "lead", "text", "시작할게요", "milestone", "communicate")))), 200);
        doneAll(sid, "START");
        return sid + "|" + tok;
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
        body(json(post("/api/ai/tasks/" + rid + "/approval"), Map.of("approved", true, "comment", "ok")).header("Authorization", admin), 202);
        body(internal(json(post("/internal/tasks/" + rid + "/events"), List.of(Map.of("type", "DONE", "data", Map.of("saved", true, "trace", Map.of("llm_calls", 0)))))), 200);
        assertThat(body(get("/api/ai/tasks/" + rid).header("Authorization", admin), 200).get("trace")).hasSize(2); // both runs kept
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
        for (JsonNode it : inbox.get("items")) found |= reviewTask.equals(it.path("taskId").asText()) && "ACCOUNT_REVIEW".equals(it.get("kind").asText());
        assertThat(found).isTrue();
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
}
