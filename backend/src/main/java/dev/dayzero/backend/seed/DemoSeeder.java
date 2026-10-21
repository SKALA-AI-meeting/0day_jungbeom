package dev.dayzero.backend.seed;

import dev.dayzero.backend.config.AppProperties;
import dev.dayzero.backend.domain.AdminUser;
import dev.dayzero.backend.domain.Company;
import dev.dayzero.backend.domain.Invite;
import dev.dayzero.backend.repo.AdminUserRepository;
import dev.dayzero.backend.repo.CompanyRepository;
import dev.dayzero.backend.repo.InviteRepository;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * Demo data for local runs (SEED_DEMO=true). Test credentials only — documented in README.
 * admin: demo@dayzero.dev / dayzero-demo-pass, reusable invite token: demo
 */
@Component
public class DemoSeeder implements ApplicationRunner {
    public static final String EMAIL = "demo@dayzero.dev";
    public static final String PASSWORD = "dayzero-demo-pass";
    public static final String INVITE = "demo";

    private final AppProperties props;
    private final CompanyRepository companies;
    private final AdminUserRepository users;
    private final InviteRepository invites;
    private final PasswordEncoder encoder;

    public DemoSeeder(AppProperties props, CompanyRepository companies, AdminUserRepository users, InviteRepository invites, PasswordEncoder encoder) {
        this.props = props; this.companies = companies; this.users = users; this.invites = invites; this.encoder = encoder;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!props.seedDemo() || users.findByEmail(EMAIL).isPresent()) return;
        Company c = new Company();
        c.name = "데모 기업";
        companies.save(c);
        AdminUser u = new AdminUser();
        u.company = c; u.email = EMAIL; u.passwordHash = encoder.encode(PASSWORD);
        users.save(u);
        Invite i = new Invite();
        i.company = c; i.token = INVITE; i.reusable = true;
        invites.save(i);
    }
}
