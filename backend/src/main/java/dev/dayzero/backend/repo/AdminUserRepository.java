package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.AdminUser;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AdminUserRepository extends JpaRepository<AdminUser, Long> {
    java.util.Optional<AdminUser> findByEmail(String email);
}
