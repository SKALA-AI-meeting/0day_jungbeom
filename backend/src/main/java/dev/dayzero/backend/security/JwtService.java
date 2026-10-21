package dev.dayzero.backend.security;

import dev.dayzero.backend.config.AppProperties;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Service;

@Service
public class JwtService {
    private final SecretKey key;
    private final long ttlMinutes;

    public JwtService(AppProperties props) {
        this.key = Keys.hmacShaKeyFor(props.jwtSecret().getBytes(StandardCharsets.UTF_8));
        this.ttlMinutes = props.jwtTtlMinutes();
    }

    public String issue(AuthUser u) {
        Instant now = Instant.now();
        var b = Jwts.builder().subject(u.subject()).claim("role", u.role())
                .issuedAt(Date.from(now)).expiration(Date.from(now.plus(ttlMinutes, ChronoUnit.MINUTES)));
        if (u.companyId() != null) b.claim("cid", u.companyId());
        if (u.accountId() != null) b.claim("aid", u.accountId());
        return b.signWith(key).compact();
    }

    public AuthUser parse(String token) {
        Claims c = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
        Number cid = c.get("cid", Number.class);
        Number aid = c.get("aid", Number.class);
        return new AuthUser(c.getSubject(), c.get("role", String.class), cid == null ? null : cid.longValue(), aid == null ? null : aid.longValue());
    }
}
