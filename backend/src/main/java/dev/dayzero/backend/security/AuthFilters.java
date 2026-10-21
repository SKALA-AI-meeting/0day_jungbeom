package dev.dayzero.backend.security;

import dev.dayzero.backend.config.AppProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/** Filters shared by SecurityConfig: connector separation, internal key, bearer JWT. */
public final class AuthFilters {
    private AuthFilters() {}

    /** /internal/** only on the internal connector; /api/** never on it. */
    public static class PortGuard extends OncePerRequestFilter {
        private final int internalPort;
        public PortGuard(AppProperties p) { this.internalPort = p.internalPort(); }

        @Override
        protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
            boolean internalPath = req.getRequestURI().startsWith("/internal/");
            boolean onInternal = req.getLocalPort() == internalPort;
            if (internalPath != onInternal && !req.getRequestURI().startsWith("/actuator")) {
                res.sendError(404);
                return;
            }
            chain.doFilter(req, res);
        }
    }

    public static class InternalKey extends OncePerRequestFilter {
        private final byte[] key;
        public InternalKey(AppProperties p) { this.key = p.internalKey().getBytes(StandardCharsets.UTF_8); }

        @Override
        protected boolean shouldNotFilter(HttpServletRequest req) { return !req.getRequestURI().startsWith("/internal/"); }

        @Override
        protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
            String h = req.getHeader("X-Internal-Key");
            if (h != null && MessageDigest.isEqual(key, h.getBytes(StandardCharsets.UTF_8))) {
                var auth = new UsernamePasswordAuthenticationToken(new AuthUser("internal", "INTERNAL", null, null), null,
                        List.of(new SimpleGrantedAuthority("ROLE_INTERNAL")));
                SecurityContextHolder.getContext().setAuthentication(auth);
            }
            chain.doFilter(req, res);
        }
    }

    public static class Bearer extends OncePerRequestFilter {
        private final JwtService jwt;
        public Bearer(JwtService jwt) { this.jwt = jwt; }

        @Override
        protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
            String h = req.getHeader("Authorization");
            if (h != null && h.startsWith("Bearer ")) {
                try {
                    AuthUser u = jwt.parse(h.substring(7));
                    var auth = new UsernamePasswordAuthenticationToken(u, null, List.of(new SimpleGrantedAuthority("ROLE_" + u.role())));
                    SecurityContextHolder.getContext().setAuthentication(auth);
                } catch (Exception ignored) {
                    // invalid / expired token -> stays anonymous -> 401 on protected routes
                }
            }
            chain.doFilter(req, res);
        }
    }
}
