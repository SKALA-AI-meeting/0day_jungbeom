package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.Account;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository extends JpaRepository<Account, Long> {
    Optional<Account> findByEmail(String email);
    List<Account> findByCompanyIdOrderByCreatedAtDesc(Long companyId);
    List<Account> findByCompanyIdAndStatus(Long companyId, String status);
}
