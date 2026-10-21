package dev.dayzero.backend.security;

/**
 * Authenticated principal.
 * ADMIN carries companyId. CANDIDATE carries companyId + accountId (sessions are checked against the account).
 */
public record AuthUser(String subject, String role, Long companyId, Long accountId) {
    public boolean isAdmin() { return "ADMIN".equals(role); }
    public boolean isCandidate() { return "CANDIDATE".equals(role); }
}
