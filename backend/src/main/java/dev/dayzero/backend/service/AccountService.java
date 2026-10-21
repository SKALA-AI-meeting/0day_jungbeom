package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.Account;
import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.domain.Invite;
import dev.dayzero.backend.repo.AccountRepository;
import dev.dayzero.backend.repo.AiTaskRepository;
import dev.dayzero.backend.repo.InviteRepository;
import dev.dayzero.backend.security.AuthUser;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Candidate accounts. Signup stores the account as PENDING_REVIEW and asks the agent to screen it
 * (ACCOUNT_REVIEW). The agent approves clean accounts itself and sends ambiguous ones to an admin;
 * the decision comes back through the internal API (business-mcp decide_account).
 */
@Service
public class AccountService {
    public static final Set<String> JOBS = Set.of("pm", "dev", "design", "sales", "data");
    public static final Set<String> INDUSTRIES = Set.of("fintech", "health", "commerce", "saas", "mobility");
    private static final Map<String, String> BASIS = Map.of("auto_clean", "approved", "auto_schema", "rejected", "admin_approved", "approved", "admin_rejected", "rejected");

    private final AccountRepository accounts;
    private final InviteRepository invites;
    private final AiTaskRepository taskRepo;
    private final TaskService tasks;
    private final PasswordEncoder encoder;
    private final Json json;

    public AccountService(AccountRepository accounts, InviteRepository invites, AiTaskRepository taskRepo, TaskService tasks, PasswordEncoder encoder, Json json) {
        this.accounts = accounts; this.invites = invites; this.taskRepo = taskRepo; this.tasks = tasks; this.encoder = encoder; this.json = json;
    }

    public record SignupData(String inviteToken, String email, String password, String nickname, String desiredJob,
                             String industry, Integer experienceYears, String bio, Boolean consent) {}

    @Transactional
    public Map<String, Object> signup(SignupData d) {
        Invite inv = invites.findByToken(d.inviteToken()).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "초대 링크를 찾을 수 없어요."));
        if (inv.expiresAt != null && inv.expiresAt.isBefore(OffsetDateTime.now())) throw new ResponseStatusException(HttpStatus.GONE, "링크가 만료되었습니다. 채용 담당자에게 문의해 주세요.");
        if (!JOBS.contains(d.desiredJob())) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "희망 직무를 목록에서 골라 주세요.");
        if (d.industry() != null && !d.industry().isBlank() && !INDUSTRIES.contains(d.industry())) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "관심 산업을 목록에서 골라 주세요.");
        if (!Boolean.TRUE.equals(d.consent())) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "평가 안내에 동의해야 가입할 수 있어요.");
        String email = d.email().strip().toLowerCase();
        if (accounts.findByEmail(email).isPresent()) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 가입된 이메일이에요. 로그인해 주세요.");
        Account a = new Account();
        a.company = inv.company;
        a.invite = inv;
        a.email = email;
        a.passwordHash = encoder.encode(d.password());
        a.nickname = d.nickname().strip();
        a.desiredJob = d.desiredJob();
        a.industry = (d.industry() == null || d.industry().isBlank()) ? null : d.industry();
        a.experienceYears = d.experienceYears();
        a.bio = d.bio() == null ? null : d.bio().strip();
        a.consent = true;
        accounts.save(a);
        AiTask review = requestReview(a);
        return Map.of("account", view(a), "reviewTaskId", review.id);
    }

    @Transactional
    public AiTask requestReview(Account a) {
        a.status = "PENDING_REVIEW";
        accounts.save(a);
        return tasks.create("ACCOUNT_REVIEW", null, a.company.id, a.id, "system", Map.of("account_id", a.id));
    }

    public Account login(String email, String password) {
        return accounts.findByEmail(email.strip().toLowerCase()).filter(a -> encoder.matches(password, a.passwordHash))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "이메일 또는 비밀번호가 맞지 않아요."));
    }

    public Account load(Long id) {
        return accounts.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "계정을 찾을 수 없어요."));
    }

    public Account mine(AuthUser u) {
        if (!u.isCandidate() || u.accountId() == null) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "지원자 계정으로 로그인해 주세요.");
        return load(u.accountId());
    }

    /** What the candidate sees about their own account (agent flags stay with the admin). */
    public Map<String, Object> view(Account a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", a.id); m.put("email", a.email); m.put("nickname", a.nickname); m.put("desiredJob", a.desiredJob);
        m.put("industry", a.industry); m.put("experienceYears", a.experienceYears); m.put("bio", a.bio);
        m.put("status", a.status); m.put("company", a.company.name); m.put("createdAt", a.createdAt); m.put("reviewedAt", a.reviewedAt);
        if ("REJECTED".equals(a.status)) {
            Map<String, Object> r = json.map(a.reviewJson);
            m.put("rejectReason", r == null ? null : r.getOrDefault("candidate_message", "담당자 확인 결과 이번 평가에 참여할 수 없어요."));
        }
        taskRepo.findByAccountIdAndTypeOrderByCreatedAtDesc(a.id, "ACCOUNT_REVIEW").stream().findFirst()
                .ifPresent(t -> { m.put("reviewTaskId", t.id); m.put("reviewTaskStatus", t.status); });
        return m;
    }

    /** Admin-facing view: includes the agent's review (checks, flags, recommendation). */
    public Map<String, Object> adminView(Account a) {
        Map<String, Object> m = view(a);
        m.put("review", json.any(a.reviewJson));
        m.put("reviewedBy", a.reviewedBy);
        return m;
    }

    public List<Map<String, Object>> companyAccounts(AuthUser u) {
        return accounts.findByCompanyIdOrderByCreatedAtDesc(u.companyId()).stream().map(this::adminView).toList();
    }

    // ------------------------------------------------------------------ internal API (business-mcp)
    public Map<String, Object> internalView(Long id) {
        Account a = load(id);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", a.id); m.put("company", a.company.name); m.put("email", a.email); m.put("nickname", a.nickname);
        m.put("desired_job", a.desiredJob); m.put("industry", a.industry); m.put("experience_years", a.experienceYears);
        m.put("bio", a.bio); m.put("consent", a.consent); m.put("status", a.status);
        m.put("invite_alias", a.invite == null ? null : a.invite.alias);
        m.put("created_at", a.createdAt.toInstant().toEpochMilli() / 1000.0);
        return m;
    }

    /** Agent decision. Business rules: only a pending account changes, and the basis must match the decision. */
    @Transactional
    public Map<String, Object> decide(Long id, Map<String, Object> body) {
        Account a = load(id);
        String decision = String.valueOf(body.get("decision"));
        String basis = String.valueOf(body.get("basis"));
        if (!BASIS.containsKey(basis) || !BASIS.get(basis).equals(decision))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "결정(" + decision + ")과 근거(" + basis + ")가 맞지 않아요.");
        if (!Set.of("PENDING_REVIEW", "REVIEW_ERROR").contains(a.status))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 결정된 계정이에요 (" + a.status + ").");
        applyDecision(a, decision, basis, body.get("review"), body.get("reason"));
        return Map.of("status", a.status);
    }

    private void applyDecision(Account a, String decision, String basis, Object review, Object reason) {
        a.status = "approved".equals(decision) ? "ACTIVE" : "REJECTED";
        Map<String, Object> r = new LinkedHashMap<>();
        if (review instanceof Map<?, ?> rv) rv.forEach((k, v) -> r.put(String.valueOf(k), v));
        r.put("decision", decision);
        r.put("basis", basis);
        if (reason != null) r.put("reason", reason);
        a.reviewJson = json.write(r);
        a.reviewedBy = basis;
        a.reviewedAt = OffsetDateTime.now();
        accounts.save(a);
    }

    /** Manual decision for an account whose agent review failed (REVIEW_ERROR) — closes the loop without the agent. */
    @Transactional
    public Map<String, Object> manualDecision(AuthUser u, Long id, boolean approved, String comment) {
        Account a = load(id);
        if (!Objects.equals(a.company.id, u.companyId())) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "다른 회사의 계정이에요.");
        if (!"REVIEW_ERROR".equals(a.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "에이전트 검토가 실패한 계정만 직접 결정할 수 있어요.");
        Map<String, Object> review = Objects.requireNonNullElseGet(json.map(a.reviewJson), LinkedHashMap::new);
        review.put("manual_by", u.subject());
        review.put("comment", comment == null ? "" : comment);
        applyDecision(a, approved ? "approved" : "rejected", approved ? "admin_approved" : "admin_rejected", review, "관리자 직접 결정");
        return adminView(a);
    }

    /** Loop closure: a review task that ends without a decision hands the account to an admin. */
    @EventListener
    @Transactional
    public void onTaskFinished(TaskFinishedEvent e) {
        AiTask t = e.task();
        if (!"ACCOUNT_REVIEW".equals(t.type) || t.accountId == null) return;
        accounts.findById(t.accountId).ifPresent(a -> {
            if ("PENDING_REVIEW".equals(a.status) && !"DONE".equals(e.status())) {
                a.status = "REVIEW_ERROR";
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("error", t.error == null ? "에이전트 검토가 끝나지 않았어요." : t.error);
                r.put("task_id", t.id);
                a.reviewJson = json.write(r);
                accounts.save(a);
            }
        });
    }
}
