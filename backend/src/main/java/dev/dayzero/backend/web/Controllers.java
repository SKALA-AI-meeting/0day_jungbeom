package dev.dayzero.backend.web;

import dev.dayzero.backend.domain.Account;
import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.domain.Invite;
import dev.dayzero.backend.repo.InviteRepository;
import dev.dayzero.backend.security.AuthUser;
import dev.dayzero.backend.service.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** Public business API (/api/**). The browser never talks to the agent directly. */
public final class Controllers {
    private Controllers() {}

    public record SignupReq(@NotBlank @Size(max = 100) String companyName, @Email @NotBlank String email, @NotBlank @Size(min = 8, max = 72) String password) {}
    public record LoginReq(@NotBlank String email, @NotBlank String password) {}
    public record StartReq(@NotBlank String scenarioId, @Size(max = 64) String inviteToken) {}
    public record CandidateSignupReq(@NotBlank @Size(max = 64) String inviteToken, @Email @NotBlank @Size(max = 200) String email,
                                     @NotBlank @Size(min = 8, max = 72) String password, @NotBlank @Size(min = 2, max = 20) String nickname,
                                     @NotBlank String desiredJob, String industry, @NotNull @Min(0) @Max(40) Integer experienceYears,
                                     @Size(max = 300) String bio, @NotNull Boolean consent) {}
    public record DecisionReq(boolean approved, @Size(max = 500) String comment) {}
    public record NotesReq(@Size(max = 10000) String text) {}
    public record TaskReq(@NotBlank String type, String sessionId, @Size(max = 1500) String text, @Size(max = 10) String choiceId) {}
    public record ApprovalReq(boolean approved, @Size(max = 500) String comment) {}
    public record InviteReq(@Size(max = 20) String alias, @Email String email) {}
    public record AnalyticsRefreshReq(@NotNull @Size(max = AnalyticsService.MAX_REFRESH) List<String> sessionIds) {}
    /** Checked in SessionService/ArtifactService in the contract's order (409 / 404 / 400), not by bean validation. */
    public record AnnotationReq(String artifactId, AnchorReq anchor, String kind, String text) {}
    public record AnchorReq(Integer lineStart, Integer lineEnd, String quote) {}

    @RestController
    @RequestMapping("/api/auth")
    public static class Auth {
        private final AuthService auth;
        private final AccountService accounts;
        public Auth(AuthService auth, AccountService accounts) { this.auth = auth; this.accounts = accounts; }

        /** Company admin signup (creates the company). */
        @PostMapping("/signup") public Map<String, Object> signup(@Valid @RequestBody SignupReq r) { return auth.signup(r.companyName(), r.email(), r.password()); }
        @PostMapping("/login") public Map<String, Object> login(@Valid @RequestBody LoginReq r) { return auth.login(r.email(), r.password()); }

        /** Candidate signup from an invite. The account starts PENDING_REVIEW and the agent screens it. */
        @PostMapping("/candidate/signup")
        public ResponseEntity<Map<String, Object>> candidateSignup(@Valid @RequestBody CandidateSignupReq r) {
            Map<String, Object> out = new LinkedHashMap<>(accounts.signup(new AccountService.SignupData(r.inviteToken(), r.email(), r.password(), r.nickname(),
                    r.desiredJob(), r.industry(), r.experienceYears(), r.bio(), r.consent())));
            @SuppressWarnings("unchecked") Map<String, Object> acc = (Map<String, Object>) out.get("account");
            out.put("token", auth.candidateToken(accounts.load(((Number) acc.get("id")).longValue())));
            out.put("role", "CANDIDATE");
            return ResponseEntity.status(HttpStatus.CREATED).body(out);
        }

        @PostMapping("/candidate/login")
        public Map<String, Object> candidateLogin(@Valid @RequestBody LoginReq r) {
            Account a = accounts.login(r.email(), r.password());
            return Map.of("token", auth.candidateToken(a), "role", "CANDIDATE", "account", accounts.view(a));
        }

        @GetMapping("/me") public Map<String, Object> me(@AuthenticationPrincipal AuthUser u) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("role", u.role()); m.put("subject", u.subject());
            if (u.isAdmin()) m.put("company", auth.companyOf(u).name);
            if (u.isCandidate()) m.put("account", accounts.view(accounts.mine(u)));
            return m;
        }
    }

    /** The signed-in candidate's own account, review progress and sessions. */
    @RestController
    @RequestMapping("/api/me")
    public static class Me {
        private final AccountService accounts;
        private final SessionService sessions;
        private final TaskService tasks;
        private final SseHub hub;
        public Me(AccountService accounts, SessionService sessions, TaskService tasks, SseHub hub) {
            this.accounts = accounts; this.sessions = sessions; this.tasks = tasks; this.hub = hub;
        }

        @GetMapping public Map<String, Object> me(@AuthenticationPrincipal AuthUser u) { return accounts.view(accounts.mine(u)); }

        @GetMapping("/sessions") public List<Map<String, Object>> list(@AuthenticationPrincipal AuthUser u) { return sessions.accountSessions(accounts.mine(u)); }

        @PostMapping("/sessions")
        public ResponseEntity<Map<String, Object>> start(@AuthenticationPrincipal AuthUser u, @Valid @RequestBody StartReq r) {
            return ResponseEntity.status(HttpStatus.CREATED).body(sessions.startForAccount(accounts.mine(u), r.scenarioId(), r.inviteToken()));
        }

        /** Review progress for the candidate: stage names only — the agent's flags and the admin's notes never reach this stream. */
        @GetMapping(value = "/review/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
        public SseEmitter review(@AuthenticationPrincipal AuthUser u) {
            Map<String, Object> me = accounts.view(accounts.mine(u));
            Object id = me.get("reviewTaskId");
            if (id == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "검토 작업이 없어요.");
            AiTask t = tasks.get((String) id); // the account's own review task (id taken from its own account row)
            return hub.subscribe(t.id, tasks.replay(t.id), t.finished(), e -> switch (e.type()) {
                case "PROGRESS" -> e;
                case "APPROVAL_REQUIRED" -> new SseHub.Ev(e.seq(), "PROGRESS", Map.of("stage", "admin_review", "label", "담당자 확인을 기다리는 중", "status", "waiting"));
                case "DONE", "FAILED" -> new SseHub.Ev(e.seq(), e.type(), Map.of());
                default -> null;
            });
        }
    }

    @RestController
    @RequestMapping("/api")
    public static class Public {
        private final AgentClient agent;
        private final SessionService sessions;
        public Public(AgentClient agent, SessionService sessions) { this.agent = agent; this.sessions = sessions; }

        @GetMapping("/meta") public Map<String, Object> meta() { return agent.meta(); }

        @GetMapping("/scenarios/{id}") public Map<String, Object> scenario(@PathVariable String id) {
            Map<String, Object> s = agent.scenario(id);
            if (s == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "알 수 없는 시나리오예요.");
            return s;
        }

        @GetMapping("/invites/{token}") public Map<String, Object> invite(@PathVariable String token) { return sessions.inviteInfo(token); }

    }

    @RestController
    @RequestMapping("/api/sessions")
    public static class Sessions {
        private final SessionService sessions;
        public Sessions(SessionService sessions) { this.sessions = sessions; }

        @GetMapping("/{id}") public Map<String, Object> get(@AuthenticationPrincipal AuthUser u, @PathVariable String id) { return sessions.candidateView(u, id); }
        @PutMapping("/{id}/notes") public Map<String, Object> notes(@AuthenticationPrincipal AuthUser u, @PathVariable String id, @Valid @RequestBody NotesReq r) {
            sessions.saveNotes(u, id, r.text());
            return Map.of("ok", true);
        }
        @PostMapping("/{id}/finish") public Map<String, Object> finish(@AuthenticationPrincipal AuthUser u, @PathVariable String id) {
            sessions.finish(u, id);
            return sessions.candidateView(u, id);
        }

        /** A new START after the opening failed (0 messages, latest START FAILED); 409 otherwise. */
        @PostMapping("/{id}/restart") public ResponseEntity<Map<String, Object>> restart(@AuthenticationPrincipal AuthUser u, @PathVariable String id) {
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(sessions.restart(u, id));
        }

        /** Markups on the shared work items. */
        @PostMapping("/{id}/annotations")
        public ResponseEntity<Map<String, Object>> annotate(@AuthenticationPrincipal AuthUser u, @PathVariable String id, @RequestBody AnnotationReq r) {
            AnchorReq a = r.anchor() == null ? new AnchorReq(null, null, null) : r.anchor();
            return ResponseEntity.status(HttpStatus.CREATED).body(sessions.annotate(u, id, r.artifactId(), a.lineStart(), a.lineEnd(), a.quote(), r.kind(), r.text()));
        }

        @DeleteMapping("/{id}/annotations/{annotationId}")
        public ResponseEntity<Void> deleteAnnotation(@AuthenticationPrincipal AuthUser u, @PathVariable String id, @PathVariable Long annotationId) {
            sessions.deleteAnnotation(u, id, annotationId);
            return ResponseEntity.noContent().build();
        }
    }

    /**
     * The AI task contract (PDF table 5-8): create 202, get, stream, approval, mine.
     * Browser-made types each delegate to the service that owns their rules; every other type is 400 here.
     */
    @RestController
    @RequestMapping("/api/ai/tasks")
    public static class Tasks {
        private final TaskService tasks;
        private final SessionService sessions;
        private final AnalyticsService analytics;
        private final SseHub hub;
        public Tasks(TaskService tasks, SessionService sessions, AnalyticsService analytics, SseHub hub) {
            this.tasks = tasks; this.sessions = sessions; this.analytics = analytics; this.hub = hub;
        }

        @PostMapping
        public ResponseEntity<Map<String, Object>> create(@AuthenticationPrincipal AuthUser u, @Valid @RequestBody TaskReq r) {
            Map<String, Object> out = switch (r.type()) {
                case "TURN" -> sessions.submitTurn(u, r.sessionId(), r.text(), (r.choiceId() == null || r.choiceId().isBlank()) ? null : r.choiceId());
                case "REPORT" -> {
                    if (!u.isAdmin()) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "리포트는 관리자만 요청할 수 있어요.");
                    var s = sessions.authorized(r.sessionId(), u);
                    if (!"completed".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "끝난 세션만 리포트를 만들 수 있어요.");
                    yield Map.of("taskId", sessions.requestReport(s, u.subject()).id);
                }
                case "ANALYTICS" -> analytics.request(u, r.sessionId()); // {taskId, reused}: a working task is handed out again
                default -> throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "알 수 없는 작업 종류예요.");
            };
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(out);
        }

        @GetMapping("/{id}") public Map<String, Object> get(@AuthenticationPrincipal AuthUser u, @PathVariable String id) {
            AiTask t = tasks.get(id);
            tasks.authorize(t, u);
            return view(t, u);
        }

        /** Run traces (span names, prompt versions) are for the company; a candidate gets the task without them. */
        private Map<String, Object> view(AiTask t, AuthUser u) {
            Map<String, Object> m = sessions.taskMap(t);
            if (!u.isAdmin()) m.remove("trace");
            return m;
        }

        @GetMapping(value = "/{id}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
        public SseEmitter stream(@AuthenticationPrincipal AuthUser u, @PathVariable String id) {
            AiTask t = tasks.get(id);
            tasks.authorize(t, u);
            return hub.subscribe(id, tasks.replay(id), t.finished());
        }

        @PostMapping("/{id}/approval")
        public ResponseEntity<Map<String, Object>> approval(@AuthenticationPrincipal AuthUser u, @PathVariable String id, @Valid @RequestBody ApprovalReq r) {
            AiTask t = tasks.approve(id, u, r.approved(), r.comment());
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(Map.of("taskId", t.id, "status", t.status));
        }

        @GetMapping public List<Map<String, Object>> mine(@AuthenticationPrincipal AuthUser u, @RequestParam(defaultValue = "true") boolean mine) {
            return tasks.mine(u).stream().map(t -> view(t, u)).toList();
        }
    }

    @RestController
    @RequestMapping("/api/admin")
    public static class Admin {
        private final SessionService sessions;
        private final AuthService auth;
        private final InviteRepository invites;
        private final InboxService inbox;
        private final AccountService accounts;
        private final AnalyticsService analytics;
        public Admin(SessionService sessions, AuthService auth, InviteRepository invites, InboxService inbox, AccountService accounts, AnalyticsService analytics) {
            this.sessions = sessions; this.auth = auth; this.invites = invites; this.inbox = inbox; this.accounts = accounts; this.analytics = analytics;
        }

        /** Issue checklist: what the agent asked a person to decide (shown first after login). */
        @GetMapping("/inbox") public Map<String, Object> inbox(@AuthenticationPrincipal AuthUser u) { return inbox.inbox(u); }
        /** The badge poll: {count} only (the full list is fetched by the checklist page). */
        @GetMapping("/inbox/count") public Map<String, Object> inboxCount(@AuthenticationPrincipal AuthUser u) { return Map.of("count", inbox.count(u)); }
        @GetMapping("/accounts") public List<Map<String, Object>> accounts(@AuthenticationPrincipal AuthUser u) { return accounts.companyAccounts(u); }
        @PostMapping("/accounts/{id}/decision")
        public Map<String, Object> decide(@AuthenticationPrincipal AuthUser u, @PathVariable Long id, @Valid @RequestBody DecisionReq r) {
            return accounts.manualDecision(u, id, r.approved(), r.comment());
        }

        /** Dashboard rows and session detail: Spring data + the stored analytics snapshot, never a call to the agent. */
        @GetMapping("/sessions") public List<Map<String, Object>> list(@AuthenticationPrincipal AuthUser u) { return sessions.adminRows(u); }
        @GetMapping("/sessions/{id}") public Map<String, Object> get(@AuthenticationPrincipal AuthUser u, @PathVariable String id) { return sessions.adminView(u, id); }
        /** Non-fresh snapshots among the listed sessions (≤ 20) -> an ANALYTICS task each (new or reused): [{sessionId, taskId}]. */
        @PostMapping("/analytics/refresh")
        public ResponseEntity<List<Map<String, Object>>> refreshAnalytics(@AuthenticationPrincipal AuthUser u, @Valid @RequestBody AnalyticsRefreshReq r) {
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(analytics.refresh(u, r.sessionIds()));
        }
        /** REPORT_FAILED "넘기기" (retry is POST /api/ai/tasks {type: REPORT}). */
        @PostMapping("/sessions/{id}/report/dismiss") public Map<String, Object> dismissReport(@AuthenticationPrincipal AuthUser u, @PathVariable String id) {
            return sessions.dismissReport(u, id);
        }

        @PostMapping("/invites") public ResponseEntity<Map<String, Object>> invite(@AuthenticationPrincipal AuthUser u, @Valid @RequestBody InviteReq r) {
            Invite i = sessions.createInvite(auth.companyOf(u), r.alias(), r.email());
            return ResponseEntity.status(HttpStatus.CREATED).body(inviteMap(i));
        }

        @GetMapping("/invites") public List<Map<String, Object>> invites(@AuthenticationPrincipal AuthUser u) {
            return invites.findByCompanyIdOrderByCreatedAtDesc(u.companyId()).stream().map(Admin::inviteMap).toList();
        }

        private static Map<String, Object> inviteMap(Invite i) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("token", i.token); m.put("alias", i.alias); m.put("email", i.email); m.put("reusable", i.reusable);
            m.put("expiresAt", i.expiresAt); m.put("usedAt", i.usedAt); m.put("path", "/join/" + i.token);
            return m;
        }
    }

    /** Internal API: only on the internal connector + X-Internal-Key. Called by business-mcp and the agent's event publisher. */
    @RestController
    @RequestMapping("/internal")
    public static class Internal {
        private final SessionService sessions;
        private final TaskService tasks;
        private final AccountService accounts;
        private final ArtifactService artifacts;
        private final AnalyticsService analytics;
        public Internal(SessionService sessions, TaskService tasks, AccountService accounts, ArtifactService artifacts, AnalyticsService analytics) {
            this.sessions = sessions; this.tasks = tasks; this.accounts = accounts; this.artifacts = artifacts; this.analytics = analytics;
        }

        @GetMapping("/accounts/{id}") public Map<String, Object> account(@PathVariable Long id) { return accounts.internalView(id); }
        @PostMapping("/accounts/{id}/decision") public Map<String, Object> decision(@PathVariable Long id, @RequestBody Map<String, Object> body) { return accounts.decide(id, body); }

        @GetMapping("/sessions/{id}/state") public Map<String, Object> state(@PathVariable String id) { return sessions.state(id); }
        @GetMapping("/conditions") public List<Map<String, Object>> conditions() { return sessions.conditions(); }
        @PostMapping("/sessions/{id}/init") public Map<String, Object> init(@PathVariable String id, @RequestBody Map<String, Object> body) { return sessions.init(id, body); }
        @PostMapping("/sessions/{id}/turn") public Map<String, Object> turn(@PathVariable String id, @RequestBody Map<String, Object> body) { return sessions.applyTurn(id, body); }
        @GetMapping("/sessions/{id}/artifacts") public List<Map<String, Object>> artifacts(@PathVariable String id) {
            sessions.load(id);
            return artifacts.summaries(id);
        }
        @GetMapping("/sessions/{id}/artifacts/{artifactId}") public Map<String, Object> artifact(@PathVariable String id, @PathVariable String artifactId) {
            sessions.load(id);
            return artifacts.internalOne(id, artifactId);
        }
        @GetMapping("/sessions/{id}/annotations") public List<Map<String, Object>> annotations(@PathVariable String id, @RequestParam(name = "since_idx", defaultValue = "0") int sinceIdx) {
            sessions.load(id);
            return artifacts.internalAnnotations(id, sinceIdx);
        }
        @PostMapping("/sessions/{id}/detections") public Map<String, Object> detection(@PathVariable String id, @RequestBody Map<String, Object> body) {
            Object idx = body.get("msg_idx");
            if (!(idx instanceof Number n)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "msg_idx가 필요해요.");
            sessions.saveDetection(id, n.intValue(), body.get("detection"));
            return Map.of("ok", true);
        }
        @PutMapping("/sessions/{id}/report") public Map<String, Object> report(@PathVariable String id, @RequestBody Map<String, Object> body) {
            sessions.saveReport(id, body.get("report"));
            return Map.of("ok", true);
        }
        /** business.save_analytics: body = the bundle; stored only if its source.state_rev is not older than the stored one. */
        @PutMapping("/sessions/{id}/analytics") public Map<String, Object> analytics(@PathVariable String id, @RequestBody Map<String, Object> bundle) {
            return Map.of("stored", analytics.store(id, bundle));
        }
        @PostMapping("/tasks/{id}/events") public Map<String, Object> events(@PathVariable String id, @RequestBody List<Map<String, Object>> batch) {
            tasks.onEvents(id, batch);
            return Map.of("ok", true, "count", batch.size());
        }
    }
}
