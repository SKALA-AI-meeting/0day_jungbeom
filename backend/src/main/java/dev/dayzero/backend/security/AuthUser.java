package dev.dayzero.backend.security;

/** Authenticated principal. ADMIN carries companyId; CANDIDATE is scoped to exactly one sessionId. */
public record AuthUser(String subject, String role, Long companyId, String sessionId) {
    public boolean isAdmin() { return "ADMIN".equals(role); }
    public boolean isCandidate() { return "CANDIDATE".equals(role); }
}
