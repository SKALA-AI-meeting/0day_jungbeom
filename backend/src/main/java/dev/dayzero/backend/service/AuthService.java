package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.AdminUser;
import dev.dayzero.backend.domain.Company;
import dev.dayzero.backend.repo.AdminUserRepository;
import dev.dayzero.backend.repo.CompanyRepository;
import dev.dayzero.backend.security.AuthUser;
import dev.dayzero.backend.security.JwtService;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {
    private final AdminUserRepository users;
    private final CompanyRepository companies;
    private final PasswordEncoder encoder;
    private final JwtService jwt;

    public AuthService(AdminUserRepository users, CompanyRepository companies, PasswordEncoder encoder, JwtService jwt) {
        this.users = users; this.companies = companies; this.encoder = encoder; this.jwt = jwt;
    }

    @Transactional
    public Map<String, Object> signup(String companyName, String email, String password) {
        if (users.findByEmail(email.toLowerCase()).isPresent()) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 가입된 이메일이에요.");
        Company c = new Company();
        c.name = companyName.strip();
        companies.save(c);
        AdminUser u = new AdminUser();
        u.company = c; u.email = email.toLowerCase(); u.passwordHash = encoder.encode(password);
        users.save(u);
        return tokenFor(u);
    }

    public Map<String, Object> login(String email, String password) {
        AdminUser u = users.findByEmail(email.toLowerCase()).filter(x -> encoder.matches(password, x.passwordHash))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "이메일 또는 비밀번호가 맞지 않아요."));
        return tokenFor(u);
    }

    public String candidateToken(dev.dayzero.backend.domain.Account a) {
        return jwt.issue(new AuthUser("account:" + a.id, "CANDIDATE", a.company.id, a.id));
    }

    public Company companyOf(AuthUser u) {
        return companies.findById(u.companyId()).orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "기업 정보를 찾을 수 없어요."));
    }

    private Map<String, Object> tokenFor(AdminUser u) {
        String token = jwt.issue(new AuthUser("admin:" + u.id, "ADMIN", u.company.id, null));
        return Map.of("token", token, "email", u.email, "company", u.company.name, "role", "ADMIN");
    }
}
