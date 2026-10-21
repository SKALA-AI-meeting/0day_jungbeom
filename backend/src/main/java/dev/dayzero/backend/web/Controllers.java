package dev.dayzero.backend.web;

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
    public record StartReq(@Size(max = 20) String alias, @NotBlank String scenarioId) {}
    public record NotesReq(@Size(max = 10000) String text) {}
    public record TaskReq(@NotBlank String type, String sessionId, @Size(max = 1500) String text, @Size(max = 10) String choiceId) {}
    public record ApprovalReq(boolean approved, @Size(max = 500) String comment) {}
    public record InviteReq(@Size(max = 20) String alias, @Email String email) {}

    @RestController
    @RequestMapping("/api/auth")
    public static class Auth {
        private final AuthService auth;
        public Auth(AuthService auth) { this.auth = auth; }

        @PostMapping("/signup") public Map<String, Object> signup(@Valid @RequestBody SignupReq r) { return auth.signup(r.companyName(), r.email(), r.password()); }
        @PostMapping("/login") public Map<String, Object> login(@Valid @RequestBody LoginReq r) { return auth.login(r.email(), r.password()); }
        @GetMapping("/me") public Map<String, Object> me(@AuthenticationPrincipal AuthUser u) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("role", u.role()); m.put("subject", u.subject());
            if (u.isAdmin()) m.put("company", auth.companyOf(u).name);
            return m;
        }
    }

    @RestController
    @RequestMapping("/api")
    public static class Public {
        private final AgentClient agent;
        private final SessionService sessions;
        private final AuthService auth;
        public Public(AgentClient agent, SessionService sessions, AuthService auth) { this.agent = agent; this.sessions = sessions; this.auth = auth; }

        @GetMapping("/meta") public Map<String, Object> meta() { return agent.meta(); }

        @GetMapping("/scenarios/{id}") public Map<String, Object> scenario(@PathVariable String id) {
            Map<String, Object> s = agent.scenario(id);
            if (s == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "알 수 없는 시나리오예요.");
            return s;
        }

        @GetMapping("/invites/{token}") public Map<String, Object> invite(@PathVariable String token) { return sessions.inviteInfo(token); }

        /** Starts a session from an invite and returns a candidate token scoped to that session. */
        @PostMapping("/invites/{token}/sessions")
        public ResponseEntity<Map<String, Object>> start(@PathVariable String token, @Valid @RequestBody StartReq r) {
            if (r.alias() == null || r.alias().isBlank()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "별칭을 입력해 주세요.");
            Map<String, Object> out = new LinkedHashMap<>(sessions.startFromInvite(token, r.alias(), r.scenarioId()));
            out.put("token", auth.candidateToken((String) out.get("sessionId")));
            return ResponseEntity.status(HttpStatus.CREATED).body(out);
        }
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
    }

    /** The AI task contract (PDF table 5-8): create 202, get, stream, approval, mine. */
    @RestController
    @RequestMapping("/api/ai/tasks")
    public static class Tasks {
        private final TaskService tasks;
        private final SessionService sessions;
        private final SseHub hub;
        public Tasks(TaskService tasks, SessionService sessions, SseHub hub) { this.tasks = tasks; this.sessions = sessions; this.hub = hub; }

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
                default -> throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "알 수 없는 작업 종류예요.");
            };
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(out);
        }

        @GetMapping("/{id}") public Map<String, Object> get(@AuthenticationPrincipal AuthUser u, @PathVariable String id) {
            AiTask t = tasks.get(id);
            tasks.authorize(t, u);
            return sessions.taskMap(t);
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
            return tasks.mine(u).stream().map(sessions::taskMap).toList();
        }
    }

    @RestController
    @RequestMapping("/api/admin")
    public static class Admin {
        private final SessionService sessions;
        private final AuthService auth;
        private final InviteRepository invites;
        public Admin(SessionService sessions, AuthService auth, InviteRepository invites) { this.sessions = sessions; this.auth = auth; this.invites = invites; }

        @GetMapping("/sessions") public List<Map<String, Object>> list(@AuthenticationPrincipal AuthUser u) { return sessions.adminRows(u); }
        @GetMapping("/sessions/{id}") public Map<String, Object> get(@AuthenticationPrincipal AuthUser u, @PathVariable String id) { return sessions.adminView(u, id); }

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
            m.put("expiresAt", i.expiresAt); m.put("usedAt", i.usedAt); m.put("path", "/i/" + i.token);
            return m;
        }
    }

    /** Internal API: only on the internal connector + X-Internal-Key. Called by business-mcp and the agent's event publisher. */
    @RestController
    @RequestMapping("/internal")
    public static class Internal {
        private final SessionService sessions;
        private final TaskService tasks;
        public Internal(SessionService sessions, TaskService tasks) { this.sessions = sessions; this.tasks = tasks; }

        @GetMapping("/sessions/{id}/state") public Map<String, Object> state(@PathVariable String id) { return sessions.state(id); }
        @GetMapping("/conditions") public List<Map<String, Object>> conditions() { return sessions.conditions(); }
        @PostMapping("/sessions/{id}/init") public Map<String, Object> init(@PathVariable String id, @RequestBody Map<String, Object> body) { return sessions.init(id, body); }
        @PostMapping("/sessions/{id}/turn") public Map<String, Object> turn(@PathVariable String id, @RequestBody Map<String, Object> body) { return sessions.applyTurn(id, body); }
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
        @PostMapping("/tasks/{id}/events") public Map<String, Object> events(@PathVariable String id, @RequestBody List<Map<String, Object>> batch) {
            tasks.onEvents(id, batch);
            return Map.of("ok", true, "count", batch.size());
        }
    }
}
